"""
Bot Telegram — ônibus + consulta de atividades FAM sob demanda
"""

import asyncio
import base64
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from io import BytesIO
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from aulas import registrar_handlers as registrar_aulas
from cadastro import cadastro_handler, cmd_config, cmd_resetar, callback_resetar
import db
from fam_scraper import FAMScraper
from onibus import registrar_handlers as registrar_onibus
import pagamento
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

TZ = ZoneInfo("America/Sao_Paulo")

# Contador diário de mensagens IA para usuários Free (reset no restart)
# {chat_id: {"date": "YYYY-MM-DD", "count": int}}
_ia_counter: dict[int, dict] = {}
IA_LIMITE_FREE = 5

# Estado temporário para capturar email no fluxo cartão
# {chat_id: True} — marca que estamos esperando email
_aguardando_email: dict[int, bool] = {}

MSG_PRO = (
    "⭐ Recurso exclusivo Pro!\n"
    "Use /assinar pra desbloquear (R$ 9,90/mês)\n"
    "7 dias grátis no cadastro!"
)


async def _requer_pro(update) -> bool:
    """Retorna True se o usuário NÃO é Pro (bloqueia). Envia mensagem se Free."""
    chat_id = update.effective_chat.id
    if db.is_pro(chat_id):
        return False
    await update.message.reply_text(MSG_PRO)
    return True


def checar_limite_ia(chat_id: int) -> tuple[bool, int]:
    """Retorna (bloqueado, msgs_restantes). Free = 5/dia, Pro = ilimitado."""
    if db.is_pro(chat_id):
        return False, -1  # ilimitado

    hoje = datetime.now(TZ).strftime("%Y-%m-%d")
    counter = _ia_counter.get(chat_id)

    if not counter or counter["date"] != hoje:
        _ia_counter[chat_id] = {"date": hoje, "count": 0}
        counter = _ia_counter[chat_id]

    if counter["count"] >= IA_LIMITE_FREE:
        return True, 0

    return False, IA_LIMITE_FREE - counter["count"]


def incrementar_ia(chat_id: int) -> None:
    """Incrementa o contador de mensagens IA do dia."""
    hoje = datetime.now(TZ).strftime("%Y-%m-%d")
    counter = _ia_counter.get(chat_id)
    if not counter or counter["date"] != hoje:
        _ia_counter[chat_id] = {"date": hoje, "count": 1}
    else:
        counter["count"] += 1


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

    if await _requer_pro(update):
        return

    db.log_evento(chat_id, "cmd_atividades")
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

    # Free: 1x por semana
    if not db.is_pro(chat_id):
        ultimo = db.ultimo_evento(chat_id, "cmd_notas")
        if ultimo:
            try:
                from zoneinfo import ZoneInfo as _ZI
                dt_ultimo = datetime.fromisoformat(ultimo).replace(tzinfo=_ZI("UTC"))
                dias = (datetime.now(TZ) - dt_ultimo).days
                if dias < 7:
                    restam = 7 - dias
                    await update.message.reply_text(
                        f"📊 No plano Free, /notas pode ser usado 1x por semana.\n"
                        f"Próxima consulta disponível em {restam} dia{'s' if restam != 1 else ''}.\n\n"
                        "⭐ Use /assinar pra consultas ilimitadas (R$ 9,90/mês)"
                    )
                    return
            except (ValueError, TypeError):
                pass

    db.log_evento(chat_id, "cmd_notas")
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

    if await _requer_pro(update):
        return

    db.log_evento(chat_id, "cmd_faltas")
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


# ── /simular — simulação de quanto precisa tirar ──────────────────────────


def _calcular_simulacao(nota: dict) -> dict:
    """Calcula situação e o que precisa pra passar.

    Fórmula FAM:
    - MS = média ponderada de N1, N2, N3 com pesos do portal
    - MS >= 6.0 + freq >= 75% → Aprovado direto
    - MS < 6.0 → AR necessária = 10.0 - MS. MF = (MS + AR) / 2, precisa MF >= 5.0
    - Se AR > 10 → impossível

    Retorna: {"status": str, "emoji": str, "texto": str}
    """
    disc = nota.get("disciplina", "N/A")
    faltas = nota.get("faltas", 0)
    max_f = nota.get("max_faltas", 0)
    ms = nota.get("media_semestral")
    mf = nota.get("media_final")
    n1 = nota.get("n1")
    n2 = nota.get("n2")
    n3 = nota.get("n3")
    peso1 = nota.get("peso1") or 1.0
    peso2 = nota.get("peso2") or 1.0
    peso3 = nota.get("peso3") or 1.0

    # Portal mostra MS=0.0 quando nenhuma nota foi lançada — tratar como None
    if ms == 0.0 and n1 is None and n2 is None and n3 is None:
        ms = None

    # Reprovado por falta
    if max_f > 0 and faltas >= max_f * 0.75:
        pct = faltas / max_f * 100
        return {
            "status": "reprovado_falta",
            "emoji": "🔴",
            "texto": f"Faltas: {faltas}/{max_f} ({pct:.0f}%) — Reprovado por falta",
        }

    # Já tem MF → fechou
    if mf is not None:
        if mf >= 5.0:
            return {"status": "aprovado", "emoji": "✅", "texto": f"Aprovado (MF: {mf:.1f})"}
        else:
            return {"status": "reprovado", "emoji": "🔴", "texto": f"Reprovado (MF: {mf:.1f})"}

    # Já tem MS
    if ms is not None:
        if ms >= 6.0:
            return {"status": "aprovado", "emoji": "✅", "texto": f"Aprovado direto (MS: {ms:.1f})"}
        else:
            ar_necessaria = 10.0 - ms
            if ar_necessaria > 10.0:
                return {"status": "impossivel", "emoji": "🔴", "texto": f"MS: {ms:.1f} — Impossível passar mesmo com AR"}
            return {
                "status": "precisa_ar",
                "emoji": "⚠️",
                "texto": f"MS: {ms:.1f} — Precisa de AR >= {ar_necessaria:.1f} pra MF >= 5.0",
            }

    # MS não existe ainda → calcula o que falta
    # Identifica quais notas já tem
    notas_existentes = []
    pesos_existentes = []
    notas_faltantes = []
    pesos_faltantes = []

    for val, peso, label in [(n1, peso1, "N1"), (n2, peso2, "N2"), (n3, peso3, "N3")]:
        if val is not None:
            notas_existentes.append((label, val, peso))
            pesos_existentes.append(peso)
        else:
            notas_faltantes.append((label, peso))
            pesos_faltantes.append(peso)

    if not notas_faltantes:
        # Todas as notas existem mas MS não foi calculada — calcula localmente
        soma_pesos = sum(p for _, _, p in notas_existentes)
        if soma_pesos > 0:
            ms_calc = sum(v * p for _, v, p in notas_existentes) / soma_pesos
        else:
            ms_calc = 0
        if ms_calc >= 6.0:
            return {"status": "aprovado", "emoji": "✅", "texto": f"Aprovado direto (MS estimada: {ms_calc:.1f})"}
        ar_necessaria = 10.0 - ms_calc
        if ar_necessaria > 10.0:
            return {"status": "impossivel", "emoji": "🔴", "texto": f"MS estimada: {ms_calc:.1f} — Impossível passar"}
        return {
            "status": "precisa_ar",
            "emoji": "⚠️",
            "texto": f"MS estimada: {ms_calc:.1f} — Precisa de AR >= {ar_necessaria:.1f}",
        }

    # Tem notas faltando → calcula nota mínima pra MS >= 6.0
    soma_pesos_total = sum(p for _, _, p in notas_existentes) + sum(p for _, p in notas_faltantes)
    contribuicao_existente = sum(v * p for _, v, p in notas_existentes)

    # MS >= 6.0 → contribuicao_existente + soma(nota_faltante * peso) >= 6.0 * soma_pesos_total
    pontos_faltam = 6.0 * soma_pesos_total - contribuicao_existente
    soma_pesos_falt = sum(p for _, p in notas_faltantes)

    existentes_str = ", ".join(f"{l}: {v:.1f}" for l, v, _ in notas_existentes)

    if soma_pesos_falt > 0:
        nota_minima = pontos_faltam / soma_pesos_falt
    else:
        nota_minima = 0

    if nota_minima <= 0:
        # Já garante aprovação direto com qualquer nota
        return {
            "status": "tranquilo",
            "emoji": "✅",
            "texto": f"{existentes_str} — Já garante MS >= 6.0 com qualquer nota",
        }

    faltantes_labels = " e ".join(l for l, _ in notas_faltantes)

    if nota_minima <= 10.0:
        linhas = [f"{existentes_str} — Precisa de no mínimo {nota_minima:.1f} na {faltantes_labels}"]

        # Calcula cenário AR se tirar menos
        # Qual a pior MS possível (notas faltantes = 0)?
        pior_ms = contribuicao_existente / soma_pesos_total if soma_pesos_total > 0 else 0
        ar_pior = 10.0 - pior_ms
        if ar_pior <= 10.0:
            linhas.append(f"Senão, AR >= {ar_pior:.1f} pra MF >= 5.0")
        return {"status": "precisa_nota", "emoji": "⚠️", "texto": "\n   ".join(linhas)}
    else:
        # Impossível passar direto, precisa de AR
        # Calcula a melhor MS possível (notas faltantes = 10)
        melhor_ms = (contribuicao_existente + 10.0 * soma_pesos_falt) / soma_pesos_total
        if melhor_ms >= 6.0:
            return {
                "status": "precisa_nota_alta",
                "emoji": "⚠️",
                "texto": f"{existentes_str} — Precisa de {nota_minima:.1f} na {faltantes_labels} (difícil, mira na AR)",
            }
        else:
            ar_necessaria = 10.0 - melhor_ms
            if ar_necessaria > 10.0:
                return {"status": "impossivel", "emoji": "🔴", "texto": f"{existentes_str} — Impossível passar"}
            return {
                "status": "precisa_ar",
                "emoji": "⚠️",
                "texto": f"{existentes_str} — Vai precisar de AR >= {ar_necessaria:.1f} (melhor MS possível: {melhor_ms:.1f})",
            }


async def cmd_simular(update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /simular — simula quanto precisa tirar pra passar."""
    chat_id = update.effective_chat.id

    if not db.is_registered(chat_id):
        await update.message.reply_text("Primeiro faça seu cadastro com /start 👆")
        return

    if await _requer_pro(update):
        return

    db.log_evento(chat_id, "cmd_simular")
    notas = db.get_notas(chat_id)
    if not notas:
        await update.message.reply_text(
            "📭 Sem notas no cache. Use /notas primeiro pra importar do portal."
        )
        return

    linhas = ["🎯 *Simulação — Quanto preciso tirar*\n"]

    for nota in notas:
        resultado = _calcular_simulacao(nota)
        disc = nota.get("disciplina", "N/A")
        linhas.append(f"{resultado['emoji']} *{disc}*")
        linhas.append(f"   {resultado['texto']}")
        linhas.append("")

    texto = "\n".join(linhas)
    if len(texto) > 4096:
        texto = texto[:4090] + "\n..."

    await update.message.reply_text(texto, parse_mode="Markdown")


# ── /grade — re-sync da grade ────────────────────────────────────────────


def _scrape_grade(chat_id: int):
    """Blocking: faz login + extrai grade do portal. Roda via run_in_executor."""
    creds = db.get_credentials(chat_id)
    if not creds:
        return None

    user = db.get_user(chat_id)
    turno = (user.get("turno") if user else None) or "noturno"

    fam_login, fam_senha = creds
    scraper = FAMScraper(fam_login, fam_senha, headless=True)
    try:
        if not scraper.fazer_login():
            logger.error("Falha no login ao extrair grade (cmd /grade)")
            return None
        return scraper.extrair_grade(turno=turno)
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

    db.log_evento(chat_id, "cmd_grade")
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


# ── /dp — matérias reprovadas (dependências) ──────────────────────────────


def _scrape_historico(chat_id: int):
    """Blocking: faz login + extrai histórico do portal. Roda via run_in_executor."""
    creds = db.get_credentials(chat_id)
    if not creds:
        return None

    fam_login, fam_senha = creds
    scraper = FAMScraper(fam_login, fam_senha, headless=True)
    try:
        if not scraper.fazer_login():
            logger.error("Falha no login ao extrair histórico (cmd /dp)")
            return None
        return scraper.extrair_historico()
    except Exception as e:
        logger.error("Erro ao extrair histórico: %s", e, exc_info=True)
        return None
    finally:
        scraper.close()


async def cmd_dp(update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /dp — mostra matérias reprovadas (dependências)."""
    chat_id = update.effective_chat.id

    if not db.is_registered(chat_id):
        await update.message.reply_text("Primeiro faça seu cadastro com /start 👆")
        return

    if await _requer_pro(update):
        return

    db.log_evento(chat_id, "cmd_dp")
    msg = await update.message.reply_text("🔄 Consultando histórico no portal FAM...")

    loop = asyncio.get_event_loop()
    historico = await loop.run_in_executor(None, _scrape_historico, chat_id)

    if historico is None:
        await msg.edit_text(
            "❌ Não foi possível extrair o histórico.\n"
            "Verifique suas credenciais (/config)."
        )
        return

    # Salva no banco
    db.set_historico(chat_id, historico)

    # Filtra reprovados
    reprovados = [h for h in historico if "reprovado" in h.get("situacao", "").lower()]

    if not reprovados:
        await msg.edit_text("✅ Nenhuma DP! Tá limpo.", parse_mode="Markdown")
        return

    linhas = ["📚 *Matérias em DP*\n"]
    for h in reprovados:
        disc = h.get("disciplina", "N/A")
        sem = h.get("semestre", "?")
        mf = h.get("media_final")
        mf_str = f" (MF: {mf:.1f})" if mf is not None else ""
        linhas.append(f"🔴 *{disc}*")
        linhas.append(f"   Reprovado no {sem}{mf_str}")
        linhas.append("")

    linhas.append(f"Total: {len(reprovados)} dependência{'s' if len(reprovados) > 1 else ''}")
    texto = "\n".join(linhas)

    if len(texto) > 4096:
        texto = texto[:4090] + "\n..."

    await msg.edit_text(texto, parse_mode="Markdown")


# ── /suporte e /sugestoes ─────────────────────────────────────────────────

# Estado temporário: {chat_id: "suporte"|"sugestao"}
_aguardando_texto: dict[int, str] = {}


async def cmd_suporte(update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /suporte — envia mensagem pro suporte."""
    chat_id = update.effective_chat.id
    db.log_evento(chat_id, "cmd_suporte")
    _aguardando_texto[chat_id] = "suporte"

    await update.message.reply_text(
        "🆘 *Suporte*\n\n"
        "Descreva seu problema ou dúvida na próxima mensagem.\n"
        "Vou encaminhar pro desenvolvedor.",
        parse_mode="Markdown",
    )


async def cmd_sugestoes(update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /sugestoes — envia sugestão de funcionalidade."""
    chat_id = update.effective_chat.id
    db.log_evento(chat_id, "cmd_sugestoes")
    _aguardando_texto[chat_id] = "sugestao"

    await update.message.reply_text(
        "💡 *Sugestões*\n\n"
        "Manda sua ideia ou sugestão na próxima mensagem.\n"
        "Todas as sugestões são lidas pelo desenvolvedor!",
        parse_mode="Markdown",
    )


async def receber_texto_suporte_sugestao(update, context: ContextTypes.DEFAULT_TYPE):
    """Handler de texto: captura mensagem de suporte/sugestão."""
    chat_id = update.effective_chat.id
    tipo = _aguardando_texto.get(chat_id)

    if not tipo:
        return

    texto = update.message.text.strip()
    del _aguardando_texto[chat_id]

    user = db.get_user(chat_id)
    nome = user["nome"] if user else "Desconhecido"

    if tipo == "suporte":
        db.salvar_suporte(chat_id, texto)
        await update.message.reply_text("✅ Mensagem enviada pro suporte! Vamos responder em breve.")

        # Notifica admin
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=f"🆘 *Suporte*\n\nDe: {nome} (chat\\_id: `{chat_id}`)\n\n{texto}",
            parse_mode="Markdown",
        )
    else:
        db.salvar_sugestao(chat_id, texto)
        await update.message.reply_text("✅ Sugestão enviada! Valeu pela contribuição.")

        # Notifica admin
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=f"💡 *Sugestão*\n\nDe: {nome} (chat\\_id: `{chat_id}`)\n\n{texto}",
            parse_mode="Markdown",
        )


# ── /stats — analytics (admin only) ──────────────────────────────────────


ADMIN_CHAT_ID = int(os.getenv("TELEGRAM_CHAT_ID", "0"))


async def cmd_stats(update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /stats — mostra analytics do bot (só admin)."""
    chat_id = update.effective_chat.id

    if chat_id != ADMIN_CHAT_ID:
        await update.message.reply_text("🔒 Comando restrito ao administrador.")
        return

    stats = db.get_stats()

    linhas = [
        "📊 *Analytics do FAMus*\n",
        "*Funil:*",
        f"  👥 Leads totais: {stats['leads_total']}",
        f"  ⏳ Onboarding incompleto: {stats['onboarding_incompleto']}",
        f"  ✅ Cadastrados: {stats['usuarios_cadastrados']}",
        f"  🚫 Leads sem cadastro: {stats['leads_sem_cadastro']}",
        "",
        "*Atividade (7 dias):*",
        f"  📈 Eventos hoje: {stats['eventos_hoje']}",
        f"  📈 Eventos 7d: {stats['eventos_7d']}",
        f"  👤 Usuários ativos 7d: {stats['usuarios_ativos_7d']}",
    ]

    top = stats.get("top_comandos_7d", [])
    if top:
        linhas.append("")
        linhas.append("*Top comandos (7d):*")
        for tipo, cnt in top:
            linhas.append(f"  {tipo}: {cnt}")

    texto = "\n".join(linhas)
    await update.message.reply_text(texto, parse_mode="Markdown")



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
    """Blocking: faz scrape de notas + histórico de um usuário e compara com cache.

    Retorna (mudancas_notas, mudancas_faltas) ou None se erro/primeira vez.
    Atualiza o cache no banco independentemente.
    Aproveita a mesma sessão para atualizar o histórico (DPs).
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

        # Aproveita sessão pra atualizar histórico
        try:
            historico = scraper.extrair_historico()
            if historico:
                db.set_historico(chat_id, historico)
                logger.info("Job notas: histórico atualizado para chat_id=%d (%d disciplinas).",
                            chat_id, len(historico))
        except Exception as e:
            logger.warning("Job notas: erro ao extrair histórico chat_id=%d: %s", chat_id, e)
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

        # Notificações automáticas são exclusivas Pro
        if not db.is_pro(chat_id):
            logger.debug("Job notas: pulando chat_id=%d (plano Free).", chat_id)
            continue

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


# ── /assinar — assinatura Pro ─────────────────────────────────────────────


async def cmd_assinar(update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /assinar — mostra opções de pagamento Pro."""
    chat_id = update.effective_chat.id

    if not db.is_registered(chat_id):
        await update.message.reply_text("Primeiro faça seu cadastro com /start 👆")
        return

    db.log_evento(chat_id, "cmd_assinar")

    # Já é Pro?
    if db.is_pro(chat_id):
        info = db.get_plano(chat_id)
        expira = info.get("plano_expira", "")
        try:
            dt = datetime.fromisoformat(expira)
            expira_fmt = dt.strftime("%d/%m/%Y")
        except (ValueError, TypeError):
            expira_fmt = "indefinido"
        await update.message.reply_text(
            f"✅ Você já é Pro! Expira em {expira_fmt}.\n"
            "Use /plano pra ver detalhes."
        )
        return

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("💳 Pagar Avulso — R$ 9,90 (PIX/cartão)", callback_data="assinar_pix")],
        [InlineKeyboardButton("🔄 Assinatura Mensal — R$ 9,90/mês", callback_data="assinar_cartao")],
    ])

    await update.message.reply_text(
        "⭐ *Plano Pro — R$ 9,90/mês*\n\n"
        "Inclui:\n"
        "• Notificações automáticas de notas e faltas\n"
        "• IA ilimitada\n"
        "• /simular, /dp, /atividades\n\n"
        "Escolha a forma de pagamento:",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


async def callback_assinar_pix(update, context: ContextTypes.DEFAULT_TYPE):
    """Callback: cria preferência Checkout Pro e agenda polling em background."""
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id

    await query.edit_message_text("🔄 Gerando link de pagamento...")

    loop = asyncio.get_event_loop()
    pref = await loop.run_in_executor(None, pagamento.criar_preferencia, chat_id)

    if not pref:
        await query.edit_message_text(
            "❌ Erro ao gerar pagamento. Tente novamente com /assinar."
        )
        return

    preference_id = pref["preference_id"]
    init_point = pref["init_point"]

    # Salva no banco
    db.criar_pagamento(chat_id, "pix", preference_id, pagamento.VALOR_PRO)

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("💳 Pagar R$ 9,90", url=init_point)],
    ])

    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            "🔗 Clique no botão abaixo pra pagar.\n"
            "Você pode escolher PIX, cartão ou saldo MP.\n\n"
            "⏳ Verifico automaticamente por 10 minutos."
        ),
        reply_markup=keyboard,
    )

    # Agenda polling em background (não bloqueia o bot)
    context.job_queue.run_repeating(
        _job_poll_pagamento,
        interval=15,
        first=15,
        data={"chat_id": chat_id, "preference_id": preference_id, "tentativas": 0},
        name=f"poll_pag_{chat_id}",
    )


async def _job_poll_pagamento(context: ContextTypes.DEFAULT_TYPE):
    """Job de polling: checa se pagamento foi aprovado. Roda a cada 15s, max 10 min."""
    job = context.job
    data = job.data
    chat_id = data["chat_id"]
    preference_id = data["preference_id"]
    data["tentativas"] += 1

    # Max 40 tentativas (40 * 15s = 10 min)
    if data["tentativas"] > 40:
        job.schedule_removal()
        await context.bot.send_message(
            chat_id=chat_id,
            text="⏰ Não detectei o pagamento. Use /assinar pra tentar de novo.",
        )
        return

    loop = asyncio.get_event_loop()
    resultado = await loop.run_in_executor(None, pagamento.buscar_pagamento_por_referencia, chat_id)

    if resultado and resultado["status"] == "approved":
        job.schedule_removal()
        db.atualizar_pagamento(preference_id, "approved")
        expira = (datetime.now(TZ) + timedelta(days=30)).isoformat()
        db.set_plano(chat_id, "pro", expira)
        await context.bot.send_message(
            chat_id=chat_id,
            text="✅ Pagamento confirmado! Plano Pro ativado por 30 dias.",
        )
        logger.info("Pagamento aprovado: chat_id=%d pref=%s", chat_id, preference_id)


async def callback_assinar_cartao(update, context: ContextTypes.DEFAULT_TYPE):
    """Callback: pede email para criar assinatura recorrente."""
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id

    _aguardando_email[chat_id] = True

    await query.edit_message_text(
        "📧 Pra assinatura com cartão, preciso do seu *email*.\n"
        "(O Mercado Pago usa pra gerenciar a cobrança recorrente)\n\n"
        "Me manda seu email:",
        parse_mode="Markdown",
    )


async def receber_email_assinatura(update, context: ContextTypes.DEFAULT_TYPE):
    """Handler de texto: captura email quando estamos aguardando."""
    chat_id = update.effective_chat.id

    if not _aguardando_email.get(chat_id):
        return  # Não é pra nós

    email = update.message.text.strip()

    # Validação básica
    if "@" not in email or "." not in email:
        await update.message.reply_text("❌ Email inválido. Tenta de novo:")
        return

    del _aguardando_email[chat_id]

    await update.message.reply_text("🔄 Criando assinatura...")

    loop = asyncio.get_event_loop()
    sub = await loop.run_in_executor(None, pagamento.criar_assinatura, chat_id, email)

    if not sub:
        await update.message.reply_text(
            "❌ Erro ao criar assinatura. Tente novamente com /assinar."
        )
        return

    subscription_id = sub["subscription_id"]
    init_point = sub["init_point"]

    # Salva no banco
    db.criar_pagamento(chat_id, "subscription", subscription_id, pagamento.VALOR_PRO)

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("💳 Completar pagamento", url=init_point)],
    ])

    await update.message.reply_text(
        "🔗 Clique no botão abaixo pra completar a assinatura no Mercado Pago.\n"
        "Após confirmar, seu Pro será ativado automaticamente em alguns minutos.",
        reply_markup=keyboard,
    )
    logger.info("Assinatura criada: chat_id=%d subscription_id=%s", chat_id, subscription_id)


# ── /plano — status do plano ────────────────────────────────────────────


async def cmd_plano(update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /plano — mostra plano atual."""
    chat_id = update.effective_chat.id

    if not db.is_registered(chat_id):
        await update.message.reply_text("Primeiro faça seu cadastro com /start 👆")
        return

    db.log_evento(chat_id, "cmd_plano")
    info = db.get_plano(chat_id)

    if not info:
        await update.message.reply_text("Use /start pra se cadastrar primeiro.")
        return

    plano = info["plano"]
    expira = info["plano_expira"]

    if plano == "free":
        await update.message.reply_text(
            "📋 *Seu plano: Free*\n\n"
            "• Consulta manual de notas/grade\n"
            "• 5 mensagens IA por dia\n"
            "• Horários de ônibus\n\n"
            "Use /assinar pra ter Pro (R$ 9,90/mês)!",
            parse_mode="Markdown",
        )
        return

    try:
        dt = datetime.fromisoformat(expira)
        expira_fmt = dt.strftime("%d/%m/%Y às %H:%M")
    except (ValueError, TypeError):
        expira_fmt = "indefinido"

    plano_label = "Pro" if plano == "pro" else "Trial"

    linhas = [
        f"📋 *Seu plano: {plano_label}*\n",
        f"Expira em: {expira_fmt}\n",
        "Inclui:",
        "• Notificações automáticas",
        "• IA ilimitada",
        "• /simular, /dp, /atividades",
    ]

    botoes = []

    # Checa se tem subscription ativa
    pag = db.get_pagamento_por_chat(chat_id, "subscription")
    if pag and pag["status"] in ("pending", "approved"):
        linhas.append(f"\nAssinatura recorrente ativa")
        botoes.append([InlineKeyboardButton("❌ Cancelar assinatura", callback_data=f"cancelar_sub_{pag['mp_id']}")])

    # Sempre oferecer cancelar plano (downgrade pra Free)
    botoes.append([InlineKeyboardButton("🚫 Cancelar plano Pro", callback_data="cancelar_plano")])

    texto = "\n".join(linhas)
    await update.message.reply_text(texto, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(botoes))


async def callback_cancelar_sub(update, context: ContextTypes.DEFAULT_TYPE):
    """Callback: cancela assinatura recorrente no MP."""
    query = update.callback_query
    await query.answer()

    sub_id = query.data.replace("cancelar_sub_", "")
    loop = asyncio.get_event_loop()
    ok = await loop.run_in_executor(None, pagamento.cancelar_assinatura, sub_id)

    if ok:
        db.atualizar_pagamento(sub_id, "cancelled")
        await query.edit_message_text("✅ Assinatura cancelada. Seu Pro fica ativo até a data de expiração.")
    else:
        await query.edit_message_text("❌ Erro ao cancelar. Tente novamente ou entre em contato.")


async def callback_cancelar_plano(update, context: ContextTypes.DEFAULT_TYPE):
    """Callback: cancela renovação do Pro. Mantém acesso até expirar."""
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id

    # Cancela subscription no MP se existir (para de cobrar)
    pag = db.get_pagamento_por_chat(chat_id, "subscription")
    if pag and pag["status"] in ("pending", "approved"):
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, pagamento.cancelar_assinatura, pag["mp_id"])
        db.atualizar_pagamento(pag["mp_id"], "cancelled")

    # NÃO faz downgrade imediato — mantém Pro até expirar
    # O job de expiração vai fazer o downgrade quando plano_expira passar
    info = db.get_plano(chat_id)
    expira = (info or {}).get("plano_expira", "")
    try:
        dt = datetime.fromisoformat(expira)
        expira_fmt = dt.strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        expira_fmt = "a data de expiração"

    await query.edit_message_text(
        f"✅ Cancelamento confirmado.\n\n"
        f"Seu Pro continua ativo até *{expira_fmt}*.\n"
        "Após essa data, volta pro plano Free automaticamente.\n\n"
        "Use /assinar se mudar de ideia.",
        parse_mode="Markdown",
    )
    logger.info("Plano cancelado (mantém até expirar): chat_id=%d", chat_id)


# ── Job: verificar expiração e assinaturas ────────────────────────────────


async def job_verificar_expiracoes(context: ContextTypes.DEFAULT_TYPE):
    """Job periódico: verifica planos expirados e renova se tem subscription ativa."""
    logger.info("Job expiração: verificando planos expirados...")
    expirados = db.get_usuarios_pro_expirados()

    for user in expirados:
        chat_id = user["chat_id"]
        try:
            # Checa se tem subscription ativa no MP
            pag = db.get_pagamento_por_chat(chat_id, "subscription")
            if pag and pag["status"] in ("pending", "approved"):
                sub_id = pag["mp_id"]
                loop = asyncio.get_event_loop()
                status_info = await loop.run_in_executor(None, pagamento.checar_assinatura, sub_id)

                if status_info and status_info["status"] == "authorized":
                    # Renova por mais 30 dias
                    nova_expira = (datetime.now(TZ) + timedelta(days=30)).isoformat()
                    db.set_plano(chat_id, "pro", nova_expira)
                    db.atualizar_pagamento(sub_id, "approved")
                    logger.info("Job expiração: renovado chat_id=%d por +30d", chat_id)
                    continue

            # Sem subscription ativa → downgrade
            db.set_plano(chat_id, "free", None)
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    "⏰ Seu plano Pro expirou.\n"
                    "Use /assinar pra renovar (R$ 9,90/mês)."
                ),
            )
            logger.info("Job expiração: downgrade chat_id=%d para Free", chat_id)

        except Exception as e:
            logger.error("Job expiração: erro chat_id=%d: %s", chat_id, e, exc_info=True)

    logger.info("Job expiração: concluído. %d verificados.", len(expirados))


# ── Job: verificar assinaturas pendentes ──────────────────────────────────


async def job_verificar_assinaturas(context: ContextTypes.DEFAULT_TYPE):
    """Job periódico: checa se assinaturas pendentes foram autorizadas."""
    logger.info("Job assinaturas: verificando pendentes...")
    con = db._conn()
    try:
        rows = con.execute(
            "SELECT * FROM pagamentos WHERE tipo = 'subscription' AND status = 'pending'"
        ).fetchall()
    finally:
        con.close()

    for row in rows:
        pag = dict(row)
        chat_id = pag["chat_id"]
        sub_id = pag["mp_id"]

        try:
            loop = asyncio.get_event_loop()
            status_info = await loop.run_in_executor(None, pagamento.checar_assinatura, sub_id)

            if status_info and status_info["status"] == "authorized":
                db.atualizar_pagamento(sub_id, "approved")
                expira = (datetime.now(TZ) + timedelta(days=30)).isoformat()
                db.set_plano(chat_id, "pro", expira)
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="✅ Assinatura confirmada! Plano Pro ativado por 30 dias.",
                )
                logger.info("Job assinaturas: ativado chat_id=%d sub_id=%s", chat_id, sub_id)
        except Exception as e:
            logger.error("Job assinaturas: erro sub_id=%s: %s", sub_id, e)

    logger.info("Job assinaturas: concluído.")


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
    app.add_handler(CommandHandler("simular", cmd_simular))
    app.add_handler(CommandHandler("dp", cmd_dp))

    # Handlers de config/resetar/stats
    app.add_handler(CommandHandler("config", cmd_config))
    app.add_handler(CommandHandler("resetar", cmd_resetar))
    app.add_handler(CallbackQueryHandler(callback_resetar, pattern="^resetar_"))
    app.add_handler(CommandHandler("stats", cmd_stats))

    # Handlers de suporte/sugestões
    app.add_handler(CommandHandler("suporte", cmd_suporte))
    app.add_handler(CommandHandler("sugestoes", cmd_sugestoes))

    # Handlers de pagamento
    app.add_handler(CommandHandler("assinar", cmd_assinar))
    app.add_handler(CommandHandler("plano", cmd_plano))
    app.add_handler(CallbackQueryHandler(callback_assinar_pix, pattern="^assinar_pix$"))
    app.add_handler(CallbackQueryHandler(callback_assinar_cartao, pattern="^assinar_cartao$"))
    app.add_handler(CallbackQueryHandler(callback_cancelar_sub, pattern="^cancelar_sub_"))
    app.add_handler(CallbackQueryHandler(callback_cancelar_plano, pattern="^cancelar_plano$"))

    # Handlers de texto especiais (group=1 — prioridade abaixo da IA)
    # Capturam email (assinatura) e texto (suporte/sugestão)
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, receber_email_assinatura),
        group=1,
    )
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, receber_texto_suporte_sugestao),
        group=2,
    )

    # Job periódico: verificar notas a cada 2 horas (primeiro check após 60s)
    app.job_queue.run_repeating(
        job_verificar_atualizacoes, interval=7200, first=60, name="verificar_atualizacoes"
    )
    logger.info("Job 'verificar_atualizacoes' agendado (intervalo=2h, first=60s)")

    # Job: verificar expiração de planos a cada 1 hora
    app.job_queue.run_repeating(
        job_verificar_expiracoes, interval=3600, first=120, name="verificar_expiracoes"
    )
    logger.info("Job 'verificar_expiracoes' agendado (intervalo=1h, first=120s)")

    # Job: verificar assinaturas pendentes a cada 5 minutos
    app.job_queue.run_repeating(
        job_verificar_assinaturas, interval=300, first=180, name="verificar_assinaturas"
    )
    logger.info("Job 'verificar_assinaturas' agendado (intervalo=5min, first=180s)")

    logger.info("Bot rodando...")
    app.run_polling()


if __name__ == "__main__":
    main()
