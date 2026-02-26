"""
Bot Telegram — ônibus + consulta de atividades FAM sob demanda
"""

import asyncio
import logging
import os
import sys

from dotenv import load_dotenv
from telegram.ext import Application, CommandHandler, ContextTypes

from aulas import registrar_handlers as registrar_aulas
from cadastro import cadastro_handler, cmd_config, cmd_resetar
import db
from fam_scraper import FAMScraper
from onibus import registrar_handlers as registrar_onibus
from storage import Storage
from telegram_bot import TelegramNotifier

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(os.path.dirname(__file__), '..', 'logs', 'monitor.log')),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

load_dotenv()

TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

storage = Storage()


# ── Scraping FAM ─────────────────────────────────────────────────────────────


def _scrape_atividades(chat_id: int | None = None):
    """Executa scraping do portal FAM (blocking — roda via run_in_executor).
    Se chat_id fornecido, usa credenciais do banco. Senão, fallback pro .env.
    """
    fam_login = None
    fam_senha = None

    if chat_id:
        creds = db.get_credentials(chat_id)
        if creds:
            fam_login, fam_senha = creds

    # Fallback: .env
    if not fam_login:
        fam_login = os.getenv('FAM_LOGIN')
        fam_senha = os.getenv('FAM_SENHA')

    if not fam_login or not fam_senha:
        logger.error("Sem credenciais FAM para scraping")
        return None

    scraper = FAMScraper(fam_login, fam_senha, headless=True)
    try:
        if not scraper.fazer_login():
            logger.error("Falha no login do portal FAM")
            return None
        atividades = scraper.extrair_atividades()
        logger.info("Atividades extraídas: %d", len(atividades))
        return atividades
    except Exception as e:
        logger.error("Erro no scraping: %s", e, exc_info=True)
        return None
    finally:
        scraper.close()


def _formatar_atividade(at, idx):
    """Formata uma atividade para exibição compacta."""
    titulo = at.get('titulo', 'N/A')
    disciplina = at.get('disciplina', '')
    prazo = (at.get('prazo', '') or '').replace('\n', ' ').strip()
    situacao = (at.get('situacao', '') or '').replace('\n', ' ').strip()

    linhas = [f"*{idx}. {titulo}*"]
    if disciplina:
        linhas.append(f"   📚 {disciplina}")
    if prazo:
        linhas.append(f"   ⏰ {prazo}")
    if situacao:
        linhas.append(f"   📊 {situacao}")
    return "\n".join(linhas)


# ── Handler ──────────────────────────────────────────────────────────────────


async def cmd_atividades(update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /atividades — consulta atividades do portal FAM."""
    chat_id = update.effective_chat.id

    if not db.is_registered(chat_id):
        await update.message.reply_text("Primeiro faça seu cadastro com /start 👆")
        return

    msg = await update.message.reply_text("🔄 Consultando portal FAM...")

    loop = asyncio.get_event_loop()
    atividades = await loop.run_in_executor(None, _scrape_atividades, chat_id)

    if atividades is None:
        await msg.edit_text("❌ Falha ao acessar o portal FAM.")
        return

    if not atividades:
        await msg.edit_text("✅ Nenhuma atividade encontrada.")
        return

    # Detecta novas
    novas = storage.get_novas_atividades(atividades)
    storage.atualizar_last_check()

    partes = [f"📋 *{len(atividades)} atividades*"]
    if novas:
        partes[0] += f" ({len(novas)} novas)"
    partes.append("")

    for i, at in enumerate(atividades, 1):
        partes.append(_formatar_atividade(at, i))

    texto = "\n".join(partes)

    # Telegram limita mensagens a 4096 chars
    if len(texto) > 4096:
        texto = texto[:4090] + "\n..."

    await msg.edit_text(texto, parse_mode="Markdown")


# ── /grade — re-sync da grade ────────────────────────────────────────────


def _scrape_grade(chat_id: int):
    """Blocking: faz login + extrai grade do portal. Roda via run_in_executor."""
    creds = db.get_credentials(chat_id)
    if not creds:
        return None

    fam_login, fam_senha = creds
    scraper = FAMScraper(fam_login, fam_senha, headless=True)
    try:
        if not scraper.fazer_login():
            logger.error("Falha no login ao extrair grade (cmd /grade)")
            return None
        return scraper.extrair_grade()
    except Exception as e:
        logger.error("Erro ao extrair grade: %s", e, exc_info=True)
        return None
    finally:
        scraper.close()


async def cmd_grade(update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /grade — força re-sync da grade a partir do portal."""
    chat_id = update.effective_chat.id

    if not db.is_registered(chat_id):
        await update.message.reply_text("Primeiro faça seu cadastro com /start 👆")
        return

    msg = await update.message.reply_text("🔄 Atualizando grade a partir do portal FAM...")

    loop = asyncio.get_event_loop()
    grade = await loop.run_in_executor(None, _scrape_grade, chat_id)

    if grade and any(grade.get(str(d)) for d in range(6)):
        db.set_grade(chat_id, grade)
        # Conta total de matérias
        total = sum(len(v) for v in grade.values())
        await msg.edit_text(
            f"✅ Grade atualizada! ({total} blocos de aula importados)\n"
            "Use /aula pra conferir."
        )
    else:
        await msg.edit_text(
            "❌ Não foi possível importar a grade.\n"
            "Verifique se suas credenciais estão corretas (/config)."
        )


# ── Main ─────────────────────────────────────────────────────────────────────


def main():
    # Inicializa banco de dados (cria tabelas + seed do Pedro)
    db.init_db()

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # IMPORTANTE: ConversationHandler de cadastro PRIMEIRO (tem prioridade no /start)
    app.add_handler(cadastro_handler)

    # Handlers de ônibus e aulas (inclui /start fallback para cadastrados)
    registrar_onibus(app)
    registrar_aulas(app)

    # Handler de atividades FAM e grade
    app.add_handler(CommandHandler("atividades", cmd_atividades))
    app.add_handler(CommandHandler("grade", cmd_grade))

    # Handlers de config/resetar
    app.add_handler(CommandHandler("config", cmd_config))
    app.add_handler(CommandHandler("resetar", cmd_resetar))

    logger.info("Bot rodando...")
    app.run_polling()


if __name__ == "__main__":
    main()
