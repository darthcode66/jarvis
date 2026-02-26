"""
Famus — responde mensagens em linguagem natural usando pattern matching.
Sem API, sem custo. Detecta intenção por palavras-chave.
"""

import random
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import ContextTypes

import db
from aulas import DIAS_NOME, _formatar_dia, _menu_aula, _aulas_semana, _load_grade
from onibus import (
    HORARIOS,
    menu_keyboard,
    proximos_onibus,
    resumo_trajetos,
)

TZ = ZoneInfo("America/Sao_Paulo")


def _normalizar(texto: str) -> str:
    """Lowercase, remove acentos simples."""
    texto = texto.lower().strip()
    trocas = {
        "á": "a", "à": "a", "ã": "a", "â": "a",
        "é": "e", "ê": "e",
        "í": "i",
        "ó": "o", "ô": "o", "õ": "o",
        "ú": "u", "ü": "u",
        "ç": "c",
    }
    for de, para in trocas.items():
        texto = texto.replace(de, para)
    return texto


def _tem(texto: str, *palavras) -> bool:
    """Retorna True se TODAS as palavras aparecem no texto."""
    return all(p in texto for p in palavras)


def _tem_alguma(texto: str, *palavras) -> bool:
    """Retorna True se ALGUMA das palavras aparece no texto."""
    return any(p in texto for p in palavras)


def _saudacao(nome: str = "") -> str:
    hora = datetime.now(TZ).hour
    sufixo = f", {nome}" if nome else ""
    if hora < 12:
        return random.choice([f"Bom dia{sufixo}!", f"Dia{sufixo}!"])
    elif hora < 18:
        return random.choice([f"Boa tarde{sufixo}!", f"Tarde{sufixo}!"])
    else:
        return random.choice([f"Boa noite{sufixo}!", f"Noite{sufixo}!"])


# ── Detecção de intenção ─────────────────────────────────────────────────────


def detectar_intencao(texto_original: str):
    """
    Retorna (intencao, dados) ou None se não entendeu.
    intencao: str identificando o que o usuário quer
    dados: dict com parâmetros extraídos
    """
    t = _normalizar(texto_original)

    # Saudações
    saudacoes = ("oi", "ola", "e ai", "eai", "fala", "hey", "hi", "hello", "bom dia", "boa tarde", "boa noite", "salve")
    if t in saudacoes or t.split()[0] in saudacoes:
        return ("saudacao", {})

    # Agradecimento
    if _tem_alguma(t, "obrigad", "valeu", "thanks", "tmj", "vlw"):
        return ("agradecimento", {})

    # Ônibus — checar ANTES de aulas (evita "faculdade" ser confundido com aula)
    if _tem_alguma(t, "onibus", "bus", "buzao", "busao", "transporte", "linha", "pegar", "rota") or \
       (_tem_alguma(t, "ir", "vou", "indo", "chegar", "voltar", "bora") and
        _tem_alguma(t, "casa", "trabalho", "faculdade", "fac", "fam")):
        # Detecta origem e destino
        tem_casa = _tem_alguma(t, "casa")
        tem_trabalho = _tem_alguma(t, "trabalho")
        tem_fac = _tem_alguma(t, "fac", "faculdade", "fam")

        # Detecta "sair de X pra ir pra Y" — "sair" indica ORIGEM
        sair = _tem_alguma(t, "sair", "saindo", "saio")

        if sair and tem_trabalho and tem_casa:
            return ("onibus", {"rota": "trabalho_casa"})
        if sair and tem_trabalho and tem_fac:
            return ("onibus", {"rota": "trabalho_faculdade"})
        if sair and tem_fac and tem_casa:
            return ("onibus", {"rota": "faculdade_casa"})
        if sair and tem_casa and tem_trabalho:
            return ("onibus", {"rota": "casa_trabalho"})
        if sair and tem_casa and tem_fac:
            return ("onibus", {"rota": "casa_faculdade"})

        # "ir pro trabalho" / "chegar no trabalho" → destino trabalho
        if _tem_alguma(t, "ir", "chegar", "vou", "indo", "voltar"):
            if tem_trabalho and tem_casa:
                pos_ir = max(t.rfind("ir"), t.rfind("vou"), t.rfind("indo"), t.rfind("chegar"), t.rfind("voltar"))
                if pos_ir >= 0:
                    depois = t[pos_ir:]
                    if "casa" in depois:
                        return ("onibus", {"rota": "trabalho_casa"})
                    if "trabalho" in depois:
                        return ("onibus", {"rota": "casa_trabalho"})
                return ("onibus", {"rota": "trabalho_casa"})
            if tem_trabalho:
                if tem_fac:
                    return ("onibus", {"rota": "trabalho_faculdade"})
                return ("onibus", {"rota": "casa_trabalho"})
            if tem_fac:
                if tem_trabalho:
                    return ("onibus", {"rota": "trabalho_faculdade"})
                return ("onibus", {"rota": "casa_faculdade"})
            if tem_casa:
                return ("onibus", {"rota": "trabalho_casa"})

        # "casa trabalho", "trabalho fac", etc
        if tem_casa and tem_trabalho:
            if t.index("casa") < t.index("trabalho"):
                return ("onibus", {"rota": "casa_trabalho"})
            return ("onibus", {"rota": "trabalho_casa"})
        if tem_trabalho and tem_fac:
            return ("onibus", {"rota": "trabalho_faculdade"})
        if tem_fac and tem_casa:
            if "fac" in t:
                pos_fac = t.index("fac")
            else:
                pos_fac = t.index("faculdade")
            pos_casa = t.index("casa")
            if pos_fac < pos_casa:
                return ("onibus", {"rota": "faculdade_casa"})
            return ("onibus", {"rota": "casa_faculdade"})
        if tem_casa:
            return ("onibus", {"rota": "trabalho_casa"})
        if tem_trabalho:
            return ("onibus", {"rota": "casa_trabalho"})
        if tem_fac:
            return ("onibus", {"rota": "trabalho_faculdade"})

        return ("onibus", {"rota": None})

    # Aulas
    if _tem_alguma(t, "aula", "materia", "disciplina", "professor", "prof", "grade"):
        if _tem_alguma(t, "amanha"):
            return ("aula", {"quando": "amanha"})
        if _tem_alguma(t, "semana", "toda"):
            return ("aula", {"quando": "semana"})
        dias_map = {"segunda": 0, "terca": 1, "quarta": 2, "quinta": 3, "sexta": 4, "sabado": 5}
        for nome_dia, num in dias_map.items():
            if nome_dia in t:
                return ("aula", {"quando": "dia", "dia": num})
        return ("aula", {"quando": "hoje"})

    # Atividades FAM
    if _tem_alguma(t, "atividade", "portal", "fam", "tarefa"):
        return ("atividades", {})

    # Ajuda
    if _tem_alguma(t, "ajuda", "help", "comando", "o que voce faz", "o que vc faz"):
        return ("ajuda", {})

    return None


# ── Gerar respostas ──────────────────────────────────────────────────────────


async def responder(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Tenta responder a mensagem naturalmente.
    Retorna True se respondeu, False se não entendeu.
    """
    texto = update.message.text
    chat_id = update.effective_chat.id
    resultado = detectar_intencao(texto)

    if resultado is None:
        return False

    intencao, dados = resultado

    # Carrega nome do usuário
    user = db.get_user(chat_id)
    nome = user["nome"] if user else ""

    if intencao == "saudacao":
        saudacao = _saudacao(nome)
        frases = [
            f"{saudacao} Precisando de algo?",
            f"{saudacao} No que posso ajudar?",
            f"{saudacao} Manda aí!",
        ]
        await update.message.reply_text(random.choice(frases))
        return True

    if intencao == "agradecimento":
        frases = [
            "De nada! 👊",
            "Tmj! 🤙",
            "Qualquer coisa tô aqui!",
            "Nada! Precisando é só chamar.",
        ]
        await update.message.reply_text(random.choice(frases))
        return True

    if intencao == "aula":
        agora = datetime.now(TZ)
        quando = dados["quando"]
        grade = _load_grade(chat_id)

        if quando == "hoje":
            info = _formatar_dia(agora.weekday(), agora, grade)
            intro = random.choice(["Hoje tem isso:", "Suas aulas de hoje:"])
        elif quando == "amanha":
            amanha = agora + timedelta(days=1)
            info = _formatar_dia(amanha.weekday(), amanha, grade)
            intro = random.choice(["Amanhã:", "Pra amanhã:"])
        elif quando == "semana":
            info = _aulas_semana(grade)
            intro = "Sua semana:"
        elif quando == "dia":
            dia_num = dados["dia"]
            info = _formatar_dia(dia_num, grade=grade)
            intro = f"{DIAS_NOME[dia_num]}:"
        else:
            info = _formatar_dia(agora.weekday(), agora, grade)
            intro = "Hoje:"

        await update.message.reply_text(
            f"{intro}\n\n{info}", reply_markup=_menu_aula()
        )
        return True

    if intencao == "onibus":
        rota = dados.get("rota")
        if rota and rota in HORARIOS:
            info = proximos_onibus(rota)
            nomes = {
                "casa_trabalho": "Casa pro Trabalho",
                "trabalho_faculdade": "Trabalho pra Faculdade",
                "faculdade_casa": "Faculdade pra Casa",
                "casa_faculdade": "Casa pra Faculdade",
                "trabalho_casa": "Trabalho pra Casa",
            }
            intro = random.choice([
                f"Próximos ônibus {nomes.get(rota, '')}:",
                f"Achei esses {nomes.get(rota, '')}:",
            ])
            await update.message.reply_text(
                f"{intro}\n\n{info}", reply_markup=menu_keyboard(route=rota)
            )
        else:
            info = resumo_trajetos()
            await update.message.reply_text(
                f"Aqui o resumo de todas as rotas:\n\n{info}",
                reply_markup=menu_keyboard(),
            )
        return True

    if intencao == "atividades":
        await update.message.reply_text(
            "Pra consultar as atividades do portal FAM, usa o /atividades 👆"
        )
        return True

    if intencao == "ajuda":
        frases = [
            "Pode me perguntar sobre aulas ou ônibus de forma natural!",
            "Posso te ajudar com horários de ônibus e aulas.",
        ]
        exemplos = (
            "\n\nExemplos:\n"
            '• "que aula tem hoje?"\n'
            '• "ônibus pro trabalho"\n'
            '• "aula de amanhã"\n'
            '• "quero ir pra faculdade"\n'
            "\nOu usa /help pra ver todos os comandos."
        )
        await update.message.reply_text(random.choice(frases) + exemplos)
        return True

    return False
