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
from fam_scraper import FAMScraper
from onibus import registrar_handlers as registrar_onibus
from storage import Storage
from telegram_bot import TelegramNotifier

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/home/pedro/faculdade/jarvis/logs/monitor.log'),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

load_dotenv()

TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
FAM_LOGIN = os.getenv('FAM_LOGIN')
FAM_SENHA = os.getenv('FAM_SENHA')

storage = Storage()


# ── Scraping FAM ─────────────────────────────────────────────────────────────


def _scrape_atividades():
    """Executa scraping do portal FAM (blocking — roda via run_in_executor)."""
    scraper = FAMScraper(FAM_LOGIN, FAM_SENHA, headless=True)
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
    msg = await update.message.reply_text("🔄 Consultando portal FAM...")

    loop = asyncio.get_event_loop()
    atividades = await loop.run_in_executor(None, _scrape_atividades)

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


# ── Main ─────────────────────────────────────────────────────────────────────


def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Handlers de ônibus e aulas
    registrar_onibus(app)
    registrar_aulas(app)

    # Handler de atividades FAM
    app.add_handler(CommandHandler("atividades", cmd_atividades))

    logger.info("Bot rodando...")
    app.run_polling()


if __name__ == "__main__":
    main()
