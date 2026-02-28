"""
Fluxo de onboarding — ConversationHandler para cadastro de novos usuários.
"""

import asyncio
import logging
import re

import requests
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

# Estados do fluxo de onboarding
# Ordem: nome → casa → trabalho → horário entrada → horário saída → transporte → turno → login FAM → senha → termos → confirmação
# O estado TERMOS (aceite LGPD) é obrigatório — sem ele o cadastro não prossegue.
# Se o usuário não aceitar, o registro parcial é removido do banco.
NOME, CASA, TRABALHO, HORARIO_ENTRADA, HORARIO_SAIDA, TRANSPORTE, TURNO, FAM_LOGIN, FAM_SENHA, TERMOS, CONFIRMA = range(11)


# ── Entry point ──────────────────────────────────────────────────────────────


async def iniciar_cadastro(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point: /start para usuários NÃO cadastrados."""
    chat_id = update.effective_chat.id
    user_tg = update.effective_user
    db.registrar_lead(chat_id, username=getattr(user_tg, 'username', None), primeiro_nome=getattr(user_tg, 'first_name', None))
    db.log_evento(chat_id, "cmd_start")

    if db.is_registered(chat_id):
        # Já cadastrado → mostra menu principal
        from onibus import menu_keyboard
        user = db.get_user(chat_id)
        nome = user["nome"] if user else ""
        plano_info = db.get_plano(chat_id)
        plano = (plano_info or {}).get("plano", "free")
        if plano in ("pro", "trial") and not db.is_pro(chat_id):
            plano_label = "Free (expirado)"
        else:
            plano_label = {"pro": "Pro", "trial": "Trial", "free": "Free"}.get(plano, "Free")

        from telegram import ReplyKeyboardRemove
        await update.message.reply_text(
            f"🤖 Fala {nome}! Plano: *{plano_label}*\n\n"
            "🎓 /aula — grade de aulas\n"
            "📚 /notas — boletim\n"
            "🚌 /onibus — ônibus ⭐\n"
            "📋 /faltas — faltas ⭐\n"
            "🎯 /simular — simulação ⭐\n"
            "💳 /assinar — plano Pro\n"
            "📖 /help — todos os comandos\n\n"
            "_Ou me manda uma mensagem que eu respondo com IA!_",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove(),
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


# ── Helpers ──────────────────────────────────────────────────────────────────


def _normalizar_endereco(texto: str) -> str:
    """Expande abreviações comuns de endereços brasileiros."""
    abreviacoes = [
        (r"\bJd\.?", "Jardim"),
        (r"\bAv\.?", "Avenida"),
        (r"\bR\.?(?=\s)", "Rua"),
        (r"\bPç\.?", "Praça"),
        (r"\bAl\.(?=\s)", "Alameda"),
        (r"\bVl\.?", "Vila"),
        (r"\bSta\.?", "Santa"),
        (r"\bSto\.?", "Santo"),
        (r"\bPe\.?", "Padre"),
        (r"\bDr\.?", "Doutor"),
        (r"\bProf\.?", "Professor"),
        (r"\bEng\.?", "Engenheiro"),
    ]
    resultado = texto
    for padrao, expansao in abreviacoes:
        resultado = re.sub(padrao, expansao, resultado, flags=re.IGNORECASE)
    # Normaliza "Americana-SP", "Americana, SP", "Americana SP" → "Americana, São Paulo"
    resultado = re.sub(r"[,\s-]\s*SP\b", ", São Paulo", resultado, flags=re.IGNORECASE)
    return resultado.strip()


def _nominatim_search(query: str) -> dict | None:
    """Faz uma busca no Nominatim. Retorna primeiro resultado ou None."""
    resp = requests.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": query, "format": "json", "limit": 1, "countrycodes": "br"},
        headers={"User-Agent": "FAMusBot/1.0"},
        timeout=5,
    )
    results = resp.json()
    return results[0] if results else None


def _resultado_em_sp(resultado: dict) -> bool:
    """Checa se o resultado do Nominatim está em São Paulo (evita falsos positivos)."""
    display = resultado.get("display_name", "")
    return "São Paulo" in display


def _validar_endereco(texto: str) -> str | None:
    """Valida endereço via Nominatim com fallbacks progressivos.

    Tenta: 1) texto normalizado + SP, 2) sem números, 3) só cidade.
    Aceita se qualquer tentativa retornar resultado em SP.
    Retorna display_name ou None. Em caso de erro de rede, aceita como está.
    """
    # Rejeita inputs muito curtos ou só números
    limpo = re.sub(r"[\d\s.,\-]", "", texto)
    if len(limpo) < 3:
        return None

    try:
        normalizado = _normalizar_endereco(texto)

        # Tentativa 1: texto normalizado completo
        resultado = _nominatim_search(f"{normalizado}, São Paulo, Brasil")
        if resultado and _resultado_em_sp(resultado):
            return resultado.get("display_name")

        # Tentativa 2: sem números de casa (Nominatim é ruim com números BR)
        sem_numeros = re.sub(r"\b\d+\b", "", normalizado).strip()
        sem_numeros = re.sub(r"\s{2,}", " ", sem_numeros)
        if sem_numeros != normalizado:
            resultado = _nominatim_search(f"{sem_numeros}, São Paulo, Brasil")
            if resultado and _resultado_em_sp(resultado):
                return resultado.get("display_name")

        # Tentativa 3: extrai possível nome de cidade e valida
        # Separa por vírgula, traço ou espaço duplo
        partes = re.split(r"[,\-]", texto)
        # Se não tinha separador, tenta extrair cidades conhecidas pelo contexto
        if len(partes) == 1:
            partes = re.split(r"\s{2,}", texto)
        for parte in reversed(partes):
            parte = parte.strip()
            # Remove números e espaços extras
            parte_limpa = re.sub(r"\b\d+\b", "", parte).strip()
            if len(parte_limpa) >= 4:
                parte_norm = _normalizar_endereco(parte_limpa)
                resultado = _nominatim_search(f"{parte_norm}, São Paulo, Brasil")
                if resultado and resultado.get("addresstype") in ("municipality", "city", "town", "suburb") and _resultado_em_sp(resultado):
                    return resultado.get("display_name")

        return None
    except Exception:
        return texto  # fallback: aceita como está


# ── Estados ──────────────────────────────────────────────────────────────────


async def receber_nome(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    nome = update.message.text.strip()
    context.user_data["nome"] = nome
    db.create_user(update.effective_chat.id, nome)

    await update.message.reply_text(
        f"Beleza, *{nome}*! 🤙\n\n"
        "Agora me diz: *qual o endereço da sua casa?*\n"
        "_Uso isso pra estimar onde você está e calcular rotas_\n\n"
        "(rua, número, bairro — ex: Jd. da Balsa, Americana-SP)",
        parse_mode="Markdown",
    )
    return CASA


async def receber_casa(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    texto = update.message.text.strip()
    resultado = _validar_endereco(texto)
    if resultado is None:
        await update.message.reply_text(
            "Não encontrei esse endereço. Tenta ser mais específico "
            "(bairro, cidade — ex: Jd. da Balsa, Americana-SP):",
            parse_mode="Markdown",
        )
        return CASA

    context.user_data["endereco_casa"] = texto

    await update.message.reply_text(
        "Show! E o *endereço do trabalho?*\n"
        "_Pra montar rotas casa→trabalho e trabalho→faculdade_\n\n"
        "(manda 'pular' se não trabalha)",
        parse_mode="Markdown",
    )
    return TRABALHO


async def receber_trabalho(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    texto = update.message.text.strip()

    if texto.lower() in ("pular", "pula", "não trabalho", "nao trabalho", "-"):
        context.user_data["endereco_trabalho"] = None
        context.user_data["horario_entrada_trabalho"] = None
        context.user_data["horario_saida_trabalho"] = None
        await update.message.reply_text(
            "Suave! *Como você vai pra FAM?*\n"
            "_Pra saber se posso te ajudar com horários de ônibus_",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(
                [["Ônibus SOU", "EMTU / Intermunicipal"], ["Carro / Carona", "Outro"]],
                one_time_keyboard=True, resize_keyboard=True,
            ),
        )
        return TRANSPORTE

    resultado = _validar_endereco(texto)
    if resultado is None:
        await update.message.reply_text(
            "Não encontrei esse endereço. Tenta ser mais específico "
            "(bairro, cidade — ex: Vila Sta. Catarina, Americana-SP):",
            parse_mode="Markdown",
        )
        return TRABALHO

    context.user_data["endereco_trabalho"] = texto

    await update.message.reply_text(
        "E *que horas você entra no trabalho?*\n"
        "_Pra saber qual ônibus pegar de manhã_\n\n"
        "(formato HH:MM — ex: 08:00)",
        parse_mode="Markdown",
    )
    return HORARIO_ENTRADA


async def receber_horario_entrada(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    texto = update.message.text.strip()
    if not re.match(r"^\d{1,2}:\d{2}$", texto):
        await update.message.reply_text(
            "Formato inválido. Manda no formato *HH:MM* (ex: 08:00):",
            parse_mode="Markdown",
        )
        return HORARIO_ENTRADA

    context.user_data["horario_entrada_trabalho"] = texto

    await update.message.reply_text(
        "E *que horas você sai do trabalho?*\n"
        "_Pra saber qual ônibus pegar pra faculdade_\n\n"
        "(formato HH:MM — ex: 18:00)",
        parse_mode="Markdown",
    )
    return HORARIO_SAIDA


async def receber_horario_saida(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    texto = update.message.text.strip()
    if not re.match(r"^\d{1,2}:\d{2}$", texto):
        await update.message.reply_text(
            "Formato inválido. Manda no formato *HH:MM* (ex: 18:00):",
            parse_mode="Markdown",
        )
        return HORARIO_SAIDA

    context.user_data["horario_saida_trabalho"] = texto

    await update.message.reply_text(
        "Beleza! *Como você vai pra FAM?*\n"
        "_Pra saber se posso te ajudar com horários de ônibus_",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(
            [["Ônibus SOU", "EMTU / Intermunicipal"], ["Carro / Carona", "Outro"]],
            one_time_keyboard=True, resize_keyboard=True,
        ),
    )
    return TRANSPORTE


async def receber_transporte(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    texto = update.message.text.strip().lower()
    mapa = {
        "ônibus sou": "sou",
        "onibus sou": "sou",
        "sou": "sou",
        "emtu / intermunicipal": "emtu",
        "emtu": "emtu",
        "intermunicipal": "emtu",
        "carro / carona": "carro",
        "carro": "carro",
        "carona": "carro",
        "outro": "outro",
    }
    transporte = mapa.get(texto, "outro")
    context.user_data["transporte"] = transporte

    await update.message.reply_text(
        "Beleza! *Qual seu turno na FAM?*\n"
        "_Preciso disso pra mostrar os horários corretos das suas aulas_",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(
            [["Matutino", "Vespertino", "Noturno"]], one_time_keyboard=True, resize_keyboard=True
        ),
    )
    return TURNO


async def receber_turno(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    texto = update.message.text.strip().lower()
    if texto not in ("matutino", "vespertino", "noturno"):
        await update.message.reply_text(
            "Por favor, escolha: *Matutino*, *Vespertino* ou *Noturno*",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(
                [["Matutino", "Vespertino", "Noturno"]], one_time_keyboard=True, resize_keyboard=True
            ),
        )
        return TURNO

    context.user_data["turno"] = texto

    await update.message.reply_text(
        "Agora preciso do seu *login do portal FAM* (CPF)\n"
        "🔑 _Pra acessar suas notas, faltas e grade automaticamente_",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )
    return FAM_LOGIN


async def receber_fam_login(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    texto = update.message.text.strip()
    cpf = re.sub(r"[.\-\s]", "", texto)
    if not re.match(r"^\d{11}$", cpf):
        await update.message.reply_text(
            "Ops! O login do portal FAM é seu *CPF* (11 dígitos).\n"
            "Ex: 12345678900 ou 123.456.789-00\n\n"
            "Tenta de novo:",
            parse_mode="Markdown",
        )
        return FAM_LOGIN

    context.user_data["fam_login"] = cpf

    await update.message.reply_text(
        "Qual sua *senha do portal FAM*?\n"
        "🔒 _Será criptografada e a mensagem apagada. Só o bot acessa._",
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

    await update.message.reply_text(
        "📜 *Termos de Uso — FAMus Bot*\n\n"
        "Ao continuar, você autoriza que o FAMus Bot:\n\n"
        "1. Acesse o portal acadêmico da FAM *em seu nome*, "
        "usando as credenciais que você forneceu\n"
        "2. Consulte periodicamente suas notas, faltas e grade "
        "para enviar notificações automáticas\n"
        "3. Armazene seus dados de forma *criptografada* "
        "exclusivamente para o funcionamento do serviço\n\n"
        "Seus dados *nunca* serão compartilhados com terceiros. "
        "Você pode apagar tudo a qualquer momento com /resetar.\n\n"
        "Você aceita os termos? (*Aceito* / *Não aceito*)",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(
            [["Aceito", "Não aceito"]], one_time_keyboard=True, resize_keyboard=True
        ),
    )
    return TERMOS


async def receber_termos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Aceite dos termos de uso — LGPD compliance.

    O usuário DEVE aceitar para prosseguir. Sem aceite, o cadastro parcial
    é removido do banco e o fluxo encerra. Isso nos protege juridicamente
    pois o usuário consente explicitamente com o acesso ao portal FAM.
    """
    resposta = update.message.text.strip().lower()

    if resposta not in ("aceito", "aceitar", "sim", "s", "yes", "y"):
        await update.message.reply_text(
            "Sem problemas! Sem o aceite não consigo prosseguir.\n"
            "Mande /start se mudar de ideia. 👋",
            reply_markup=ReplyKeyboardRemove(),
        )
        chat_id = update.effective_chat.id
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

    # Monta resumo
    d = context.user_data
    trabalho = d.get("endereco_trabalho") or "—"
    h_entrada = d.get("horario_entrada_trabalho") or "—"
    h_saida = d.get("horario_saida_trabalho") or "—"
    turno = (d.get("turno") or "noturno").capitalize()
    transporte_labels = {"sou": "Ônibus SOU", "emtu": "EMTU / Intermunicipal", "carro": "Carro / Carona", "outro": "Outro"}
    transporte = transporte_labels.get(d.get("transporte", "sou"), "Outro")

    resumo = (
        "📋 *Resumo do cadastro:*\n\n"
        f"👤 Nome: {d['nome']}\n"
        f"🏠 Casa: {d['endereco_casa']}\n"
        f"💼 Trabalho: {trabalho}\n"
        f"🕐 Entrada no trabalho: {h_entrada}\n"
        f"🕐 Saída do trabalho: {h_saida}\n"
        f"🚌 Transporte: {transporte}\n"
        f"🎓 Turno FAM: {turno}\n"
        f"🎓 Faculdade: FAM - Jd. Luciene, Americana-SP\n"
        f"🔑 Login FAM: {d['fam_login']}\n"
        f"🔒 Senha FAM: \\*\\*\\*\\*\n\n"
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


def _scrape_onboarding(fam_login: str, fam_senha: str, turno: str = "noturno"):
    """Blocking: faz login + extrai grade, notas, info e histórico numa única sessão.

    Retorna (login_ok, grade, notas, info, historico).
    login_ok=False indica credenciais incorretas (diferente de erro de rede/scrape).
    """
    scraper = FAMScraper(fam_login, fam_senha, headless=True)
    try:
        if not scraper.fazer_login():
            logger.error("Falha no login ao extrair dados (cadastro)")
            return False, None, None, None, None
        grade = scraper.extrair_grade(turno=turno)
        notas, info = scraper.extrair_notas()
        historico = scraper.extrair_historico()
        return True, grade, notas, info, historico
    except Exception as e:
        logger.error("Erro ao extrair dados no cadastro: %s", e, exc_info=True)
        return True, None, None, None, None  # login pode ter funcionado, erro no scrape
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
        # Limpa registro parcial (mas preserva row se tem plano ativo)
        try:
            import sqlite3
            con = sqlite3.connect(db.DB_PATH)
            con.execute(
                "DELETE FROM usuarios WHERE chat_id = ? AND onboarding_completo = 0 "
                "AND (plano IS NULL OR plano = 'free')",
                (chat_id,),
            )
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
    turno = d.get("turno") or "noturno"

    db.update_user(
        chat_id,
        endereco_casa=d["endereco_casa"],
        endereco_trabalho=d.get("endereco_trabalho"),
        horario_entrada_trabalho=d.get("horario_entrada_trabalho"),
        horario_saida_trabalho=d.get("horario_saida_trabalho"),
        transporte=d.get("transporte", "sou"),
        turno=turno,
        onboarding_completo=1,
    )
    db.set_credentials(chat_id, fam_login, fam_senha)
    db.log_evento(chat_id, "onboarding_completo")

    await update.message.reply_text(
        f"✅ Cadastro completo, *{nome}*!\n\n"
        "🔄 Importando seus dados do portal FAM (grade, notas, faltas)...",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )

    # Scrape de grade + notas + info + histórico numa única sessão
    loop = asyncio.get_event_loop()
    login_ok, grade, notas, info, historico = await loop.run_in_executor(
        None, _scrape_onboarding, fam_login, fam_senha, turno
    )

    if not login_ok:
        await update.message.reply_text(
            "❌ *Não consegui fazer login no portal FAM.*\n\n"
            "Possíveis causas:\n"
            "- CPF ou senha incorretos\n"
            "- Portal FAM fora do ar\n\n"
            "Seu cadastro foi salvo, mas sem dados acadêmicos.\n"
            "Use /notas ou /grade pra tentar importar depois, "
            "ou /resetar e /start pra corrigir login/senha.",
            parse_mode="Markdown",
        )

        trial_msg = ""
        if db.ativar_trial(chat_id):
            trial_msg = "\n🎁 Você ganhou 7 dias de Pro grátis!\n"

        await update.message.reply_text(
            trial_msg +
            "\nComandos disponíveis:\n"
            "/notas — importar boletim\n"
            "/grade — importar grade\n"
            "/config — ver dados cadastrados\n"
            "/resetar — recomeçar cadastro",
        )

        context.user_data.clear()
        return ConversationHandler.END

    resultados = []

    if grade and any(grade.get(str(d)) for d in range(6)):
        db.set_grade(chat_id, grade)
        resultados.append("✅ Grade importada")
    else:
        resultados.append("⚠️ Grade não encontrada")

    if notas:
        db.set_notas(chat_id, notas)
        resultados.append(f"✅ Notas importadas ({len(notas)} disciplinas)")
    else:
        resultados.append("⚠️ Notas não encontradas")

    if info:
        db.set_info_aluno(chat_id, info)
        extras = []
        if info.get("curso"):
            extras.append(info["curso"])
        if info.get("semestre"):
            extras.append(f"{info['semestre']}º semestre")
        if info.get("sala"):
            extras.append(info["sala"])
        if extras:
            resultados.append(f"✅ Info: {', '.join(extras)}")

    if historico:
        db.set_historico(chat_id, historico)
        reprovados = [h for h in historico if "reprovado" in h.get("situacao", "").lower()]
        if reprovados:
            resultados.append(f"✅ Histórico importado ({len(reprovados)} DP{'s' if len(reprovados) > 1 else ''})")
        else:
            resultados.append("✅ Histórico importado (nenhuma DP)")
    else:
        resultados.append("⚠️ Histórico não encontrado")

    # Ativa trial de 7 dias
    trial_msg = ""
    if db.ativar_trial(chat_id):
        trial_msg = "\n🎁 Você ganhou 7 dias de Pro grátis! Aproveite todas as funcionalidades.\n"

    await update.message.reply_text(
        "\n".join(resultados) + "\n"
        + trial_msg + "\n"
        "Comandos disponíveis:\n"
        "/aula — grade de aulas\n"
        "/onibus — horários de ônibus\n"
        "/atividades — portal FAM\n"
        "/notas — boletim\n"
        "/faltas — faltas por disciplina\n"
        "/simular — quanto preciso pra passar\n"
        "/dp — matérias reprovadas\n"
        "/assinar — plano Pro\n"
        "/plano — ver seu plano",
    )

    context.user_data.clear()
    return ConversationHandler.END


# ── Cancelar ─────────────────────────────────────────────────────────────────


async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    chat_id = update.effective_chat.id
    # Limpa registro parcial (preserva row se tem plano ativo)
    try:
        import sqlite3
        con = sqlite3.connect(db.DB_PATH)
        con.execute(
            "DELETE FROM usuarios WHERE chat_id = ? AND onboarding_completo = 0 "
            "AND (plano IS NULL OR plano = 'free')",
            (chat_id,),
        )
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

    turno = (user.get("turno") or "noturno").capitalize()
    h_entrada = user.get("horario_entrada_trabalho") or "—"
    transporte_labels = {"sou": "Ônibus SOU", "emtu": "EMTU / Intermunicipal", "carro": "Carro / Carona", "outro": "Outro"}
    transporte = transporte_labels.get(user.get("transporte", "sou"), "Outro")

    texto = (
        "⚙️ *Seus dados:*\n\n"
        f"👤 Nome: {user['nome']}\n"
        f"🏠 Casa: {user['endereco_casa'] or '—'}\n"
        f"💼 Trabalho: {user['endereco_trabalho'] or '—'}\n"
        f"🕐 Entrada: {h_entrada}\n"
        f"🕐 Saída: {user['horario_saida_trabalho'] or '—'}\n"
        f"🚌 Transporte: {transporte}\n"
        f"🎓 Turno: {turno}\n"
        f"🎓 Faculdade: {user['endereco_faculdade']}\n"
        f"🔑 Login FAM: {login}\n"
        f"🔒 Senha FAM: \\*\\*\\*\\*\n\n"
        "Para recadastrar, apague seu perfil com /resetar e depois /start."
    )
    await update.message.reply_text(texto, parse_mode="Markdown")


async def cmd_resetar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Pede confirmação antes de apagar dados. Plano é preservado."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    chat_id = update.effective_chat.id
    user = db.get_user(chat_id)

    if not user:
        await update.message.reply_text("Você não tem cadastro. Use /start para começar!")
        return

    plano_info = db.get_plano(chat_id)
    plano = (plano_info or {}).get("plano", "free")

    aviso_plano = ""
    if plano in ("pro", "trial"):
        plano_label = "Pro" if plano == "pro" else "Trial"
        aviso_plano = f"\n_Seu plano {plano_label} será mantido._\n"

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Sim, resetar cadastro", callback_data="resetar_confirmar"),
         InlineKeyboardButton("Cancelar", callback_data="resetar_cancelar")],
    ])

    await update.message.reply_text(
        "⚠️ *Tem certeza que quer resetar seu cadastro?*\n"
        + aviso_plano +
        "\nIsso vai remover:\n"
        "- Nome, endereços e horários\n"
        "- Credenciais do portal FAM\n"
        "- Notas, grade e histórico importados\n\n"
        "Seu plano e pagamentos *serão mantidos*.\n"
        "Após resetar, use /start pra recadastrar.",
        parse_mode="Markdown",
        reply_markup=kb,
    )


async def callback_resetar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Callback dos botões de confirmação do /resetar."""
    query = update.callback_query
    await query.answer()
    chat_id = query.from_user.id

    if query.data == "resetar_cancelar":
        await query.edit_message_text("Cancelado. Seus dados continuam salvos.")
        return

    # resetar_confirmar — limpa cadastro mas preserva plano/pagamentos
    import sqlite3
    con = sqlite3.connect(db.DB_PATH)
    con.execute(
        """UPDATE usuarios SET
            nome = '', endereco_casa = NULL, endereco_trabalho = NULL,
            horario_entrada_trabalho = NULL, horario_saida_trabalho = NULL,
            transporte = 'sou', turno = NULL,
            fam_login = NULL, fam_senha = NULL,
            grade = NULL, notas = NULL, info_aluno = NULL, historico = NULL,
            onboarding_completo = 0
        WHERE chat_id = ?""",
        (chat_id,),
    )
    con.commit()
    con.close()

    await query.edit_message_text(
        "🗑 Cadastro resetado. Seu plano foi mantido.\n"
        "Use /start para se cadastrar novamente."
    )


# ── Fallback para mensagens não-texto ─────────────────────────────────────────


async def _fallback_nao_texto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Responde quando o usuário envia sticker, foto, áudio, etc. durante o onboarding."""
    await update.message.reply_text(
        "Preciso que você mande uma *mensagem de texto* pra continuar o cadastro.\n"
        "Mande /cancelar se quiser sair.",
        parse_mode="Markdown",
    )


# ── ConversationHandler montado ──────────────────────────────────────────────


cadastro_handler = ConversationHandler(
    entry_points=[CommandHandler("start", iniciar_cadastro)],
    states={
        NOME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_nome)],
        CASA: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_casa)],
        TRABALHO: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_trabalho)],
        HORARIO_ENTRADA: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_horario_entrada)],
        HORARIO_SAIDA: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_horario_saida)],
        TRANSPORTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_transporte)],
        TURNO: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_turno)],
        FAM_LOGIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_fam_login)],
        FAM_SENHA: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_fam_senha)],
        TERMOS: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_termos)],
        CONFIRMA: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirmar)],
    },
    fallbacks=[
        CommandHandler("cancelar", cancelar),
        MessageHandler(~filters.TEXT, _fallback_nao_texto),
    ],
    per_user=True,
    per_chat=True,
)
