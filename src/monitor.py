"""
Bot Telegram — ônibus + consulta de atividades FAM sob demanda
"""

import asyncio
import logging
import os
import sys
import time

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


# ── /notas — consulta boletim ─────────────────────────────────────────────


def _scrape_notas(chat_id: int):
    """Blocking: faz login + extrai notas e info do aluno.

    Retorna (notas_list, info_dict) ou (None, None).
    """
    creds = db.get_credentials(chat_id)
    if not creds:
        return None, None

    fam_login, fam_senha = creds
    scraper = FAMScraper(fam_login, fam_senha, headless=True)
    try:
        if not scraper.fazer_login():
            logger.error("Falha no login ao extrair notas (cmd /notas)")
            return None, None
        return scraper.extrair_notas()
    except Exception as e:
        logger.error("Erro ao extrair notas: %s", e, exc_info=True)
        return None, None
    finally:
        scraper.close()


def _fmt_nota(valor) -> str:
    """Formata valor de nota para exibição."""
    if valor is None:
        return "—"
    return f"{valor:.1f}"


def _emoji_media(ms) -> str:
    """Emoji baseado na média semestral."""
    if ms is None:
        return "📘"
    if ms >= 6.0:
        return "✅"
    if ms > 0:
        return "⚠️"
    return "📘"


async def cmd_notas(update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /notas — consulta boletim/notas do portal FAM."""
    chat_id = update.effective_chat.id

    if not db.is_registered(chat_id):
        await update.message.reply_text("Primeiro faça seu cadastro com /start 👆")
        return

    msg = await update.message.reply_text("🔄 Consultando notas no portal FAM...")

    loop = asyncio.get_event_loop()
    notas, info = await loop.run_in_executor(None, _scrape_notas, chat_id)

    if notas is None:
        await msg.edit_text(
            "❌ Não foi possível extrair as notas.\n"
            "Verifique suas credenciais (/config)."
        )
        return

    if not notas:
        await msg.edit_text("📭 Nenhuma nota encontrada no portal.")
        return

    # Salva no banco (cache)
    db.set_notas(chat_id, notas)
    if info:
        db.set_info_aluno(chat_id, info)

    # Formata resposta
    linhas = [f"📊 *Boletim — {len(notas)} disciplinas*\n"]

    for n in notas:
        ms = n.get("media_semestral")
        mf = n.get("media_final")
        emoji = _emoji_media(mf if mf is not None else ms)
        disc = n.get("disciplina", "N/A")

        linhas.append(f"{emoji} *{disc}*")
        linhas.append(
            f"   N1: {_fmt_nota(n.get('n1'))}  |  "
            f"N2: {_fmt_nota(n.get('n2'))}  |  "
            f"N3: {_fmt_nota(n.get('n3'))}"
        )
        linhas.append(
            f"   MS: {_fmt_nota(ms)}  |  MF: {_fmt_nota(mf)}"
        )
        faltas = n.get("faltas", 0)
        max_f = n.get("max_faltas", 0)
        if max_f:
            linhas.append(f"   Faltas: {faltas}/{max_f}")
        linhas.append("")

    texto = "\n".join(linhas)

    # Telegram limita mensagens a 4096 chars
    if len(texto) > 4096:
        texto = texto[:4090] + "\n..."

    await msg.edit_text(texto, parse_mode="Markdown")


# ── /faltas — consulta rápida de faltas ──────────────────────────────────


async def cmd_faltas(update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /faltas — mostra faltas por disciplina (usa cache ou faz scrape)."""
    chat_id = update.effective_chat.id

    if not db.is_registered(chat_id):
        await update.message.reply_text("Primeiro faça seu cadastro com /start 👆")
        return

    # Tenta usar cache do banco
    notas = db.get_notas(chat_id)

    if not notas:
        msg = await update.message.reply_text("🔄 Consultando faltas no portal FAM...")
        loop = asyncio.get_event_loop()
        notas, info = await loop.run_in_executor(None, _scrape_notas, chat_id)

        if notas is None:
            await msg.edit_text(
                "❌ Não foi possível extrair as faltas.\n"
                "Verifique suas credenciais (/config)."
            )
            return

        if not notas:
            await msg.edit_text("📭 Nenhuma falta encontrada no portal.")
            return

        db.set_notas(chat_id, notas)
        if info:
            db.set_info_aluno(chat_id, info)
    else:
        msg = None

    # Filtra só disciplinas com max_faltas definido
    com_faltas = [n for n in notas if n.get("max_faltas", 0) > 0]

    if not com_faltas:
        texto = "📭 Nenhuma disciplina com controle de faltas."
    else:
        linhas = ["📋 *Faltas por disciplina*\n"]
        for n in com_faltas:
            faltas = n.get("faltas", 0)
            max_f = n.get("max_faltas", 0)
            pct = (faltas / max_f * 100) if max_f else 0
            if pct >= 75:
                emoji = "🔴"
            elif pct >= 50:
                emoji = "🟡"
            else:
                emoji = "🟢"
            linhas.append(f"{emoji} *{n['disciplina']}*")
            linhas.append(f"   {faltas}/{max_f} faltas ({pct:.0f}%)")
        texto = "\n".join(linhas)

    if msg:
        await msg.edit_text(texto, parse_mode="Markdown")
    else:
        await update.message.reply_text(texto, parse_mode="Markdown")


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


# ── Verificação periódica de notas e faltas ──────────────────────────────
#
# COMO FUNCIONA:
#   1. job_verificar_atualizacoes() é agendado no main() via JobQueue (APScheduler)
#      - Roda a cada 2 horas (interval=7200), primeiro check após 60s do boot
#   2. Para cada usuário registrado:
#      a. _check_notas_usuario() faz scrape do portal FAM (blocking, via executor)
#      b. Compara notas novas com o cache salvo no banco (db.get_notas)
#      c. Atualiza cache no banco SEMPRE (mesmo sem mudanças)
#      d. Retorna (mudancas_notas, mudancas_faltas) ou None
#   3. Se houver mudanças, envia notificações separadas (notas e faltas)
#   4. Sleep de 5s entre usuários para não sobrecarregar portal/VPS
#
# COMPORTAMENTO DE SEGURANÇA:
#   - Se o cache estiver vazio (primeiro scrape), popula sem notificar
#   - Se o scrape falhar, loga o erro e continua pro próximo usuário
#   - Nunca roda scrape em paralelo (sequencial por design)
#
# PARA DESATIVAR EM EMERGÊNCIA:
#   Comentar as 3 linhas do run_repeating no main() e reiniciar o serviço:
#     sudo systemctl restart famus
#
# PARA FORÇAR EXECUÇÃO MANUAL (debug):
#   Alterar first=5 no run_repeating e reiniciar — roda em 5 segundos
#


_CAMPOS_NOTA = ["n1", "n2", "n3", "media_semestral", "media_final"]
_LABEL_CAMPO = {
    "n1": "N1",
    "n2": "N2",
    "n3": "N3",
    "media_semestral": "Média Semestral",
    "media_final": "Média Final",
}


def _comparar_notas(antigas: list[dict], novas: list[dict]) -> tuple[list[dict], list[dict]]:
    """Compara notas antigas vs novas.

    Retorna (mudancas_notas, mudancas_faltas) separadamente.
    """
    velhas_por_disc = {n["disciplina"]: n for n in antigas}
    mudancas_notas = []
    mudancas_faltas = []

    for nova in novas:
        disc = nova["disciplina"]
        velha = velhas_por_disc.get(disc, {})

        # Notas
        diffs_notas = []
        for campo in _CAMPOS_NOTA:
            val_old = velha.get(campo)
            val_new = nova.get(campo)
            if val_new is not None and val_old != val_new:
                label = _LABEL_CAMPO[campo]
                if val_old is None:
                    diffs_notas.append(f"   Saiu {label}: {val_new:.1f}")
                else:
                    diffs_notas.append(f"   {label}: {val_old:.1f} → {val_new:.1f}")

        if diffs_notas:
            mudancas_notas.append({"disciplina": disc, "diffs": diffs_notas})

        # Faltas
        f_old = velha.get("faltas")
        f_new = nova.get("faltas")
        if f_new is not None and f_old is not None and f_old != f_new:
            max_f = nova.get("max_faltas", 0)
            pct = (f_new / max_f * 100) if max_f else 0
            diff_line = f"   {f_old} → {f_new}/{max_f} ({pct:.0f}%)"
            mudancas_faltas.append({"disciplina": disc, "diffs": [diff_line]})

    return mudancas_notas, mudancas_faltas


def _formatar_notificacao_nota(mudancas: list[dict]) -> str:
    """Formata mensagem de notificação de notas."""
    linhas = ["📢 *Atualização de notas!*\n"]
    for m in mudancas:
        linhas.append(f"📝 *{m['disciplina']}*")
        linhas.extend(m["diffs"])
        linhas.append("")
    return "\n".join(linhas)


def _formatar_notificacao_faltas(mudancas: list[dict]) -> str:
    """Formata mensagem de notificação de faltas."""
    linhas = ["📋 *Atualização de faltas!*\n"]
    for m in mudancas:
        linhas.append(f"📌 *{m['disciplina']}*")
        linhas.extend(m["diffs"])
        linhas.append("")
    return "\n".join(linhas)


def _check_notas_usuario(chat_id: int) -> tuple[list[dict], list[dict]] | None:
    """Blocking: faz scrape de notas de um usuário e compara com cache.

    Retorna (mudancas_notas, mudancas_faltas) ou None se erro/primeira vez.
    Atualiza o cache no banco independentemente.
    """
    creds = db.get_credentials(chat_id)
    if not creds:
        return None

    fam_login, fam_senha = creds
    scraper = FAMScraper(fam_login, fam_senha, headless=True)
    try:
        if not scraper.fazer_login():
            logger.warning("Job notas: falha login para chat_id=%d", chat_id)
            return None
        notas_novas, info = scraper.extrair_notas()
    except Exception as e:
        logger.error("Job notas: erro scrape chat_id=%d: %s", chat_id, e, exc_info=True)
        return None
    finally:
        scraper.close()

    if not notas_novas:
        return None

    # Compara com cache
    notas_antigas = db.get_notas(chat_id)

    # Atualiza cache sempre
    db.set_notas(chat_id, notas_novas)
    if info:
        db.set_info_aluno(chat_id, info)

    # Não notifica se cache estava vazio (primeira vez)
    if not notas_antigas:
        logger.info("Job notas: cache vazio para chat_id=%d, populando sem notificar.", chat_id)
        return None

    mudancas_notas, mudancas_faltas = _comparar_notas(notas_antigas, notas_novas)
    if not mudancas_notas and not mudancas_faltas:
        return None
    return mudancas_notas, mudancas_faltas


async def job_verificar_atualizacoes(context: ContextTypes.DEFAULT_TYPE):
    """Job periódico: verifica notas de todos os usuários registrados."""
    logger.info("Job notas: iniciando verificação periódica...")
    usuarios = db.get_all_registered_users()
    logger.info("Job notas: %d usuários registrados para verificar.", len(usuarios))

    for user in usuarios:
        chat_id = user["chat_id"]
        try:
            loop = asyncio.get_event_loop()
            resultado = await loop.run_in_executor(None, _check_notas_usuario, chat_id)

            if resultado:
                mudancas_notas, mudancas_faltas = resultado

                if mudancas_notas:
                    texto = _formatar_notificacao_nota(mudancas_notas)
                    await context.bot.send_message(
                        chat_id=chat_id, text=texto, parse_mode="Markdown"
                    )
                    logger.info("Job notas: notificação de notas para chat_id=%d (%d disciplinas).",
                                chat_id, len(mudancas_notas))

                if mudancas_faltas:
                    texto = _formatar_notificacao_faltas(mudancas_faltas)
                    await context.bot.send_message(
                        chat_id=chat_id, text=texto, parse_mode="Markdown"
                    )
                    logger.info("Job notas: notificação de faltas para chat_id=%d (%d disciplinas).",
                                chat_id, len(mudancas_faltas))
        except Exception as e:
            logger.error("Job notas: erro ao processar chat_id=%d: %s", chat_id, e, exc_info=True)

        # Sleep entre usuários para não sobrecarregar o portal
        await asyncio.sleep(5)

    logger.info("Job notas: verificação concluída.")


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

    # Handlers de atividades FAM, grade e notas
    app.add_handler(CommandHandler("atividades", cmd_atividades))
    app.add_handler(CommandHandler("grade", cmd_grade))
    app.add_handler(CommandHandler("notas", cmd_notas))
    app.add_handler(CommandHandler("faltas", cmd_faltas))

    # Handlers de config/resetar
    app.add_handler(CommandHandler("config", cmd_config))
    app.add_handler(CommandHandler("resetar", cmd_resetar))

    # Job periódico: verificar notas a cada 2 horas (primeiro check após 60s)
    app.job_queue.run_repeating(
        job_verificar_atualizacoes, interval=7200, first=60, name="verificar_atualizacoes"
    )
    logger.info("Job 'verificar_atualizacoes' agendado (intervalo=2h, first=60s)")

    logger.info("Bot rodando...")
    app.run_polling()


if __name__ == "__main__":
    main()
