"""
Grade horária FAM - dinâmica por usuário (carregada do banco).
Fallback: grade vazia se usuário não tem grade cadastrada.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

import db

TZ = ZoneInfo("America/Sao_Paulo")

DIAS_NOME = {
    0: "Segunda",
    1: "Terça",
    2: "Quarta",
    3: "Quinta",
    4: "Sexta",
    5: "Sábado",
    6: "Domingo",
}

SIGLA_DIA = {0: "SEG", 1: "TER", 2: "QUA", 3: "QUI", 4: "SEX", 5: "SAB"}

# Grade padrão (Pedro) — usada como fallback se usuário não tem grade no banco
GRADE_PADRAO = {
    0: [
        {"materia": "Prog. Orientada a Objetos", "prof": "Evandro Santaclara", "inicio": "19:00", "fim": "22:30"},
    ],
    1: [
        {"materia": "Engenharia de Software", "prof": "Lucas Parizotto", "inicio": "19:00", "fim": "20:40"},
        {"materia": "Ativ. Extensão IV", "prof": "Marcio Veleda", "inicio": "20:50", "fim": "22:30"},
        {"materia": "Tópicos Integradores I", "prof": "Murilo Fujita", "inicio": "20:50", "fim": "22:30"},
    ],
    2: [
        {"materia": "Física Geral e Experimental", "prof": "Henrique Gimenes", "inicio": "19:00", "fim": "22:30"},
    ],
    3: [],
    4: [
        {"materia": "Redes de Computadores", "prof": "Marcio Taglietta", "inicio": "19:00", "fim": "22:30"},
    ],
    5: [
        {"materia": "Ativ. Complementar IV", "prof": "", "inicio": "", "fim": ""},
    ],
}

# Alias para compatibilidade com imports antigos (gemini.py, famus.py)
GRADE = GRADE_PADRAO


def _load_grade(chat_id: int) -> dict:
    """Carrega grade do banco. Converte chaves string→int. Fallback: GRADE_PADRAO."""
    grade_raw = db.get_grade(chat_id)
    if not grade_raw:
        return GRADE_PADRAO
    # Chaves JSON são strings ("0","1"…), converter para int
    return {int(k): v for k, v in grade_raw.items()}


def _formatar_dia(dia: int, data: datetime | None = None, grade: dict | None = None) -> str:
    """Formata as aulas de um dia."""
    if grade is None:
        grade = GRADE_PADRAO
    aulas = grade.get(dia)
    nome = DIAS_NOME[dia]

    if data:
        header = f"📅 {nome}, {data.strftime('%d/%m')}"
    else:
        header = f"📅 {nome}"

    if not aulas:
        return f"{header}\n  😎 Sem aula"

    linhas = [header]
    for a in aulas:
        horario = f"{a['inicio']}-{a['fim']}" if a['inicio'] else "horário variável"
        linha = f"  📘 {a['materia']}\n      {horario}"
        if a['prof']:
            linha += f" · {a['prof']}"
        linhas.append(linha)

    return "\n".join(linhas)


def _aulas_hoje(grade: dict | None = None) -> str:
    agora = datetime.now(TZ)
    return _formatar_dia(agora.weekday(), agora, grade)


def _aulas_amanha(grade: dict | None = None) -> str:
    amanha = datetime.now(TZ) + timedelta(days=1)
    return _formatar_dia(amanha.weekday(), amanha, grade)


def _aulas_semana(grade: dict | None = None) -> str:
    if grade is None:
        grade = GRADE_PADRAO
    hoje = datetime.now(TZ)
    seg = hoje - timedelta(days=hoje.weekday())

    linhas = ["📅 Semana\n"]
    for i in range(6):  # seg a sab
        data = seg + timedelta(days=i)
        dia = data.weekday()
        aulas = grade.get(dia)

        nome = SIGLA_DIA.get(dia, "")
        if not aulas:
            continue

        for a in aulas:
            horario = f"{a['inicio']}-{a['fim']}" if a['inicio'] else "variável"
            linhas.append(f"{nome} · {a['materia']}  {horario}")

    return "\n".join(linhas)


def _menu_aula() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("📅 Hoje", callback_data="aula_hoje"),
            InlineKeyboardButton("📅 Amanhã", callback_data="aula_amanha"),
            InlineKeyboardButton("📅 Semana", callback_data="aula_semana"),
        ]]
    )


# ── Handlers ─────────────────────────────────────────────────────────────────


async def cmd_aula(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    grade = _load_grade(chat_id)
    await update.message.reply_text(_aulas_hoje(grade), reply_markup=_menu_aula())


async def callback_aula(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    chat_id = query.message.chat_id
    grade = _load_grade(chat_id)

    opcao = query.data
    if opcao == "aula_hoje":
        texto = _aulas_hoje(grade)
    elif opcao == "aula_amanha":
        texto = _aulas_amanha(grade)
    elif opcao == "aula_semana":
        texto = _aulas_semana(grade)
    else:
        return

    try:
        await query.edit_message_text(texto, reply_markup=_menu_aula())
    except BadRequest:
        pass


def registrar_handlers(app: Application) -> None:
    """Registra handlers de aulas na Application."""
    app.add_handler(CommandHandler("aula", cmd_aula))
    app.add_handler(CallbackQueryHandler(callback_aula, pattern="^aula_"))
