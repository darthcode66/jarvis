"""
Grade horária FAM - Ciência da Computação (Noturno)
Turma 57-05-B · Bloco 2 - Sala 073 - 1º piso
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

# Grade: dia da semana (0=seg) -> lista de blocos de aula
GRADE = {
    0: [  # Segunda
        {"materia": "Prog. Orientada a Objetos", "prof": "Evandro Santaclara", "inicio": "19:00", "fim": "22:30"},
    ],
    1: [  # Terça
        {"materia": "Engenharia de Software", "prof": "Lucas Parizotto", "inicio": "19:00", "fim": "20:40"},
        {"materia": "Ativ. Extensão IV", "prof": "Marcio Veleda", "inicio": "20:50", "fim": "22:30"},
        {"materia": "Tópicos Integradores I", "prof": "Murilo Fujita", "inicio": "20:50", "fim": "22:30"},
    ],
    2: [  # Quarta
        {"materia": "Física Geral e Experimental", "prof": "Henrique Gimenes", "inicio": "19:00", "fim": "22:30"},
    ],
    3: [],  # Quinta - sem aula
    4: [  # Sexta
        {"materia": "Redes de Computadores", "prof": "Marcio Taglietta", "inicio": "19:00", "fim": "22:30"},
    ],
    5: [  # Sábado
        {"materia": "Ativ. Complementar IV", "prof": "", "inicio": "", "fim": ""},
    ],
}

SIGLA_DIA = {0: "SEG", 1: "TER", 2: "QUA", 3: "QUI", 4: "SEX", 5: "SAB"}


def _formatar_dia(dia: int, data: datetime | None = None) -> str:
    """Formata as aulas de um dia."""
    aulas = GRADE.get(dia)
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


def _aulas_hoje() -> str:
    agora = datetime.now(TZ)
    return _formatar_dia(agora.weekday(), agora)


def _aulas_amanha() -> str:
    amanha = datetime.now(TZ) + timedelta(days=1)
    return _formatar_dia(amanha.weekday(), amanha)


def _aulas_semana() -> str:
    hoje = datetime.now(TZ)
    # Acha a segunda-feira desta semana
    seg = hoje - timedelta(days=hoje.weekday())

    linhas = ["📅 Semana\n"]
    for i in range(6):  # seg a sab
        data = seg + timedelta(days=i)
        dia = data.weekday()
        aulas = GRADE.get(dia)

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
    await update.message.reply_text(_aulas_hoje(), reply_markup=_menu_aula())


async def callback_aula(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    opcao = query.data
    if opcao == "aula_hoje":
        texto = _aulas_hoje()
    elif opcao == "aula_amanha":
        texto = _aulas_amanha()
    elif opcao == "aula_semana":
        texto = _aulas_semana()
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
