"""
Fluxo de onboarding — ConversationHandler para cadastro de novos usuários.
"""

import asyncio
import logging

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import db
from fam_scraper import FAMScraper

logger = logging.getLogger(__name__)

# Estados do fluxo
NOME, CASA, TRABALHO, HORARIO_TRABALHO, FAM_LOGIN, FAM_SENHA, CONFIRMA = range(7)


# ── Entry point ──────────────────────────────────────────────────────────────


async def iniciar_cadastro(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point: /start para usuários NÃO cadastrados."""
    chat_id = update.effective_chat.id

    if db.is_registered(chat_id):
        # Já cadastrado → mostra menu normal
        from onibus import menu_keyboard
        user = db.get_user(chat_id)
        nome = user["nome"] if user else ""
        await update.message.reply_text(
            f"🤖 Fala {nome}! Escolhe o trajeto:", reply_markup=menu_keyboard()
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "👋 Fala! Eu sou o *FAMus*, assistente da galera da FAM.\n\n"
        "Vou te fazer algumas perguntas rápidas pra configurar tudo certinho.\n"
        "A qualquer momento, mande /cancelar pra sair.\n\n"
        "Primeiro: *qual é o seu nome?*",
        parse_mode="Markdown",
    )
    return NOME


# ── Estados ──────────────────────────────────────────────────────────────────


async def receber_nome(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    nome = update.message.text.strip()
    context.user_data["nome"] = nome
    db.create_user(update.effective_chat.id, nome)

    await update.message.reply_text(
        f"Beleza, *{nome}*! 🤙\n\n"
        "Agora me diz: *qual o endereço da sua casa?*\n"
        "(rua, número, bairro — ex: Jd. da Balsa, Americana-SP)",
        parse_mode="Markdown",
    )
    return CASA


async def receber_casa(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["endereco_casa"] = update.message.text.strip()

    await update.message.reply_text(
        "Show! E o *endereço do trabalho?*\n"
        "(manda 'pular' se não trabalha)",
        parse_mode="Markdown",
    )
    return TRABALHO


async def receber_trabalho(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    texto = update.message.text.strip()

    if texto.lower() in ("pular", "pula", "não trabalho", "nao trabalho", "-"):
        context.user_data["endereco_trabalho"] = None
        context.user_data["horario_saida_trabalho"] = None
        await update.message.reply_text(
            "Suave! Agora preciso do seu *login do portal FAM* (CPF):",
            parse_mode="Markdown",
        )
        return FAM_LOGIN

    context.user_data["endereco_trabalho"] = texto

    await update.message.reply_text(
        "E *que horas você sai do trabalho?*\n"
        "(formato HH:MM — ex: 18:00)",
        parse_mode="Markdown",
    )
    return HORARIO_TRABALHO


async def receber_horario_trabalho(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["horario_saida_trabalho"] = update.message.text.strip()

    await update.message.reply_text(
        "Beleza! Agora preciso do seu *login do portal FAM* (CPF):",
        parse_mode="Markdown",
    )
    return FAM_LOGIN


async def receber_fam_login(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["fam_login"] = update.message.text.strip()

    await update.message.reply_text(
        "Qual sua *senha do portal FAM*?\n"
        "🔒 Ela será *criptografada* e a mensagem será apagada logo em seguida.",
        parse_mode="Markdown",
    )
    return FAM_SENHA


async def receber_fam_senha(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["fam_senha"] = update.message.text.strip()

    # Apaga a mensagem com a senha por segurança
    try:
        await update.message.delete()
    except Exception:
        logger.warning("Não foi possível apagar a mensagem com a senha.")

    # Monta resumo
    d = context.user_data
    trabalho = d.get("endereco_trabalho") or "—"
    horario = d.get("horario_saida_trabalho") or "—"

    resumo = (
        "📋 *Resumo do cadastro:*\n\n"
        f"👤 Nome: {d['nome']}\n"
        f"🏠 Casa: {d['endereco_casa']}\n"
        f"💼 Trabalho: {trabalho}\n"
        f"🕐 Saída do trabalho: {horario}\n"
        f"🎓 Faculdade: FAM - Jd. Luciene, Americana-SP\n"
        f"🔑 Login FAM: {d['fam_login']}\n"
        f"🔒 Senha FAM: ****\n\n"
        "Tudo certo? (*Sim* / *Não*)"
    )

    await update.message.reply_text(
        resumo,
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(
            [["Sim", "Não"]], one_time_keyboard=True, resize_keyboard=True
        ),
    )
    return CONFIRMA


def _scrape_grade(fam_login: str, fam_senha: str):
    """Blocking: faz login + extrai grade do portal. Roda via run_in_executor."""
    scraper = FAMScraper(fam_login, fam_senha, headless=True)
    try:
        if not scraper.fazer_login():
            logger.error("Falha no login ao extrair grade (cadastro)")
            return None
        return scraper.extrair_grade()
    except Exception as e:
        logger.error("Erro ao extrair grade no cadastro: %s", e, exc_info=True)
        return None
    finally:
        scraper.close()


async def confirmar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    resposta = update.message.text.strip().lower()
    chat_id = update.effective_chat.id

    if resposta not in ("sim", "s", "yes", "y"):
        await update.message.reply_text(
            "Cadastro cancelado. Mande /start pra recomeçar quando quiser!",
            reply_markup=ReplyKeyboardRemove(),
        )
        # Remove registro parcial
        try:
            import sqlite3
            con = sqlite3.connect(db.DB_PATH)
            con.execute("DELETE FROM usuarios WHERE chat_id = ? AND onboarding_completo = 0", (chat_id,))
            con.commit()
            con.close()
        except Exception:
            pass
        context.user_data.clear()
        return ConversationHandler.END

    # Salva tudo no banco
    d = context.user_data
    fam_login = d["fam_login"]
    fam_senha = d["fam_senha"]
    nome = d["nome"]

    db.update_user(
        chat_id,
        endereco_casa=d["endereco_casa"],
        endereco_trabalho=d.get("endereco_trabalho"),
        horario_saida_trabalho=d.get("horario_saida_trabalho"),
        onboarding_completo=1,
    )
    db.set_credentials(chat_id, fam_login, fam_senha)

    await update.message.reply_text(
        f"✅ Cadastro completo, *{nome}*!\n\n"
        "🔄 Importando sua grade de aulas do portal FAM...",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )

    # Scrape da grade em background
    loop = asyncio.get_event_loop()
    grade = await loop.run_in_executor(None, _scrape_grade, fam_login, fam_senha)

    if grade and any(grade.get(str(d)) for d in range(6)):
        db.set_grade(chat_id, grade)
        await update.message.reply_text(
            "✅ Grade importada com sucesso!\n\n"
            "Use /aula pra ver seus horários.\n"
            "Se a grade mudar, use /grade pra atualizar.",
        )
    else:
        await update.message.reply_text(
            "⚠️ Não consegui importar a grade agora.\n"
            "Use /grade mais tarde pra tentar de novo, ou peça ao admin.\n\n"
            "Enquanto isso, todos os outros comandos já funcionam:\n"
            "/aula — grade de aulas\n"
            "/onibus — horários de ônibus\n"
            "/atividades — portal FAM",
        )

    context.user_data.clear()
    return ConversationHandler.END


# ── Cancelar ─────────────────────────────────────────────────────────────────


async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    chat_id = update.effective_chat.id
    # Remove registro parcial
    try:
        import sqlite3
        con = sqlite3.connect(db.DB_PATH)
        con.execute("DELETE FROM usuarios WHERE chat_id = ? AND onboarding_completo = 0", (chat_id,))
        con.commit()
        con.close()
    except Exception:
        pass

    context.user_data.clear()
    await update.message.reply_text(
        "Cadastro cancelado. Mande /start quando quiser recomeçar! 👋",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ConversationHandler.END


# ── /config — editar dados ───────────────────────────────────────────────────


async def cmd_config(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mostra dados cadastrados e permite recadastrar."""
    chat_id = update.effective_chat.id
    user = db.get_user(chat_id)

    if not user:
        await update.message.reply_text("Você ainda não tem cadastro. Use /start para se cadastrar!")
        return

    creds = db.get_credentials(chat_id)
    login = creds[0] if creds else "—"

    texto = (
        "⚙️ *Seus dados:*\n\n"
        f"👤 Nome: {user['nome']}\n"
        f"🏠 Casa: {user['endereco_casa'] or '—'}\n"
        f"💼 Trabalho: {user['endereco_trabalho'] or '—'}\n"
        f"🕐 Saída: {user['horario_saida_trabalho'] or '—'}\n"
        f"🎓 Faculdade: {user['endereco_faculdade']}\n"
        f"🔑 Login FAM: {login}\n"
        f"🔒 Senha FAM: ****\n\n"
        "Para recadastrar, apague seu perfil com /resetar e depois /start."
    )
    await update.message.reply_text(texto, parse_mode="Markdown")


async def cmd_resetar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remove cadastro do usuário para permitir recadastro."""
    chat_id = update.effective_chat.id
    import sqlite3
    con = sqlite3.connect(db.DB_PATH)
    cur = con.execute("DELETE FROM usuarios WHERE chat_id = ?", (chat_id,))
    con.commit()
    con.close()

    if cur.rowcount:
        await update.message.reply_text("🗑 Cadastro removido. Use /start para se cadastrar novamente.")
    else:
        await update.message.reply_text("Você não tem cadastro. Use /start para começar!")


# ── ConversationHandler montado ──────────────────────────────────────────────


cadastro_handler = ConversationHandler(
    entry_points=[CommandHandler("start", iniciar_cadastro)],
    states={
        NOME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_nome)],
        CASA: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_casa)],
        TRABALHO: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_trabalho)],
        HORARIO_TRABALHO: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_horario_trabalho)],
        FAM_LOGIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_fam_login)],
        FAM_SENHA: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_fam_senha)],
        CONFIRMA: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirmar)],
    },
    fallbacks=[CommandHandler("cancelar", cancelar)],
    per_user=True,
    per_chat=True,
)
