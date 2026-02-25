"""
Integração com IA via Groq (Llama 3.3 70B) — API compatível com OpenAI.
Fallback: Gemini Flash Lite (free tier).
"""

import logging
import os
import re
import time
from datetime import datetime, timedelta
from html import escape
from urllib.parse import quote
from zoneinfo import ZoneInfo

import requests

from aulas import GRADE, DIAS_NOME
from onibus import HORARIOS

logger = logging.getLogger(__name__)

TZ = ZoneInfo("America/Sao_Paulo")

# ── Groq (primário) ────────────────────────────────────────────────────────
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODELS = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]

# ── Gemini (fallback) ──────────────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent?key={}"
GEMINI_MODELS = ["gemini-2.5-flash-lite", "gemini-2.5-flash"]

MAX_HISTORICO = 20

# Memória: chat_id -> lista de {"role": "user"|"assistant", "content": str}
_historico: dict[int, list[dict]] = {}

# Locais do Pedro
LOCAIS = {
    "casa": {"nome": "Casa", "bairro": "Jd. da Balsa, Americana-SP"},
    "trabalho": {"nome": "Trabalho", "bairro": "Vila Sta. Catarina, Americana-SP"},
    "faculdade": {"nome": "Faculdade (FAM)", "bairro": "Jd. Luciene, Americana-SP"},
}


def _local_estimado() -> str:
    """Estima onde o Pedro está baseado no horário e dia da semana."""
    agora = datetime.now(TZ)
    hora = agora.hour + agora.minute / 60
    dia = agora.weekday()

    if dia >= 5:
        return "casa"
    if hora < 8:
        return "casa"
    if hora < 17.5:
        return "trabalho"

    tem_aula = bool(GRADE.get(dia))
    if not tem_aula:
        if hora < 18.5:
            return "trabalho"
        return "casa"

    if hora < 19:
        return "trabalho"
    if hora < 23:
        return "faculdade"
    return "casa"


def _maps_link(endereco: str) -> str:
    """Gera link do Google Maps com rota a pé até o ponto de ônibus."""
    addr = f"{endereco}, Americana - SP"
    return f"https://www.google.com/maps/dir/?api=1&destination={quote(addr)}&travelmode=walking"


def _gerar_tabela_horarios() -> str:
    """Gera tabela compacta de TODOS os horários para o system prompt."""
    partes = []
    for key, trajeto in HORARIOS.items():
        partes.append(f"\nROTA: {trajeto['nome']} (id: {key})")

        por_linha: dict[str, dict] = {}
        for h in trajeto["horarios"]:
            linha = h["linha"]
            if linha not in por_linha:
                por_linha[linha] = {
                    "horas": [],
                    "embarque": h["embarque"],
                    "desembarque": h["desembarque"],
                }
            por_linha[linha]["horas"].append(h["hora"])

        linhas_nomes = [f"L.{l}" for l in por_linha]
        partes.append(f"  Linhas desta rota: {', '.join(linhas_nomes)}")
        for linha, dados in por_linha.items():
            partes.append(f"  L.{linha} horários: {', '.join(dados['horas'])}")
            partes.append(f"    Embarque: {dados['embarque']}")
            partes.append(f"    Desembarque: {dados['desembarque']}")

    return "\n".join(partes)


# Gerado uma vez na inicialização
_TABELA_HORARIOS = _gerar_tabela_horarios()


def _contexto_dinamico() -> str:
    """Gera contexto com hora atual, local estimado e próximos ônibus relevantes."""
    agora = datetime.now(TZ)
    dia_semana = agora.weekday()
    amanha_dia = (agora + timedelta(days=1)).weekday()
    hora_str = agora.strftime("%H:%M")

    local = _local_estimado()
    local_info = LOCAIS[local]

    rotas_relevantes = {
        "casa": ["casa_trabalho", "casa_faculdade"],
        "trabalho": ["trabalho_faculdade", "trabalho_casa"],
        "faculdade": ["faculdade_casa"],
    }
    relevantes = rotas_relevantes.get(local, [])

    partes = [
        f"Agora: {agora.strftime('%A, %d/%m/%Y %H:%M')}",
        f"Localização estimada: {local_info['nome']} ({local_info['bairro']})",
    ]

    # Aulas hoje
    aulas_hoje = GRADE.get(dia_semana, [])
    if aulas_hoje:
        partes.append(f"\nAulas hoje ({DIAS_NOME[dia_semana]}):")
        for a in aulas_hoje:
            h = f"{a['inicio']}-{a['fim']}" if a['inicio'] else "variável"
            linha = f"  {a['materia']} ({h})"
            if a['prof']:
                linha += f" - {a['prof']}"
            partes.append(linha)
    else:
        partes.append(f"\nHoje ({DIAS_NOME[dia_semana]}): sem aula")

    # Aulas amanhã
    aulas_amanha = GRADE.get(amanha_dia, [])
    if aulas_amanha:
        partes.append(f"\nAulas amanhã ({DIAS_NOME[amanha_dia]}):")
        for a in aulas_amanha:
            h = f"{a['inicio']}-{a['fim']}" if a['inicio'] else "variável"
            linha = f"  {a['materia']} ({h})"
            if a['prof']:
                linha += f" - {a['prof']}"
            partes.append(linha)
    else:
        partes.append(f"\nAmanhã ({DIAS_NOME[amanha_dia]}): sem aula")

    # Próximos ônibus das rotas relevantes (com Maps links)
    partes.append("\n=== PRÓXIMOS ÔNIBUS (rotas relevantes) ===")
    for key in relevantes:
        trajeto = HORARIOS.get(key)
        if not trajeto:
            continue
        proximos = [h for h in trajeto["horarios"] if h["hora"] >= hora_str]

        partes.append(f"ROTA: {trajeto['nome']}")
        if not proximos:
            partes.append("  Encerrado hoje.")
            continue

        for h in proximos[:5]:
            maps = _maps_link(h['embarque'])
            partes.append(
                f"  {h['hora']} L.{h['linha']} → {h['chegada']}"
                f" | Embarque: {h['embarque']}"
                f" | Maps: {maps}"
            )
        restantes = len(proximos) - 5
        if restantes > 0:
            partes.append(f"  (+{restantes} restantes, consulte a tabela completa)")

    return "\n".join(partes)


SYSTEM_PROMPT = """\
Você é o Jarvis, assistente pessoal do Pedro no Telegram. Pedro é estudante de Ciência da Computação (5º semestre, noturno) na FAM (Faculdade de Americana) e trabalha durante o dia na Vila Sta. Catarina, Americana-SP.

Personalidade:
- Formal e educado, mas com um leve toque de humor ácido e sarcasmo sutil (estilo Jarvis do Iron Man)
- Sempre prestativo, mas pode fazer observações espirituosas quando apropriado
- NUNCA comece com saudação (Olá, Oi, Bom dia, etc) a menos que o Pedro cumprimente primeiro
- Se o Pedro cumprimentar, retribua com uma observação espirituosa antes de responder
- Você tem memória da conversa atual — lembre-se do que foi dito
- Você NÃO pode alterar dados permanentemente. Se pedirem, diga que anota na conversa mas para alteração permanente deve falar com o desenvolvedor

Dados do Pedro:
- Sai do trabalho às 18:00 (considere ~15 min para chegar ao ponto de ônibus, ou seja, só consegue embarcar a partir de ~18:15)
- Mora no Jd. da Balsa, Americana-SP
- Trabalha na Vila Sta. Catarina, Americana-SP
- Estuda na FAM, Jd. Luciene, Americana-SP

Regras sobre ônibus:
- TODOS os horários de TODAS as rotas estão na TABELA COMPLETA DE HORÁRIOS abaixo
- NUNCA invente horários ou rotas — use SOMENTE os dados fornecidos
- CRÍTICO: cada ROTA tem ORIGEM e DESTINO fixos. NUNCA sugira ônibus de uma rota com destino diferente do pedido
- Para consultas fora do horário de pico, use a tabela completa para encontrar o horário mais próximo

FORMATAÇÃO (OBRIGATÓRIO — siga exatamente):
- Links do Maps DEVEM usar formato markdown: [texto](url)
- Ao listar ônibus, use este formato com quebras de linha:

🚌 L.XXX — HH:MM → HH:MM
📍 Embarque: endereço
[📍 Rota a pé](URL_DO_MAPS)

- Liste cada ônibus como um bloco separado com linha em branco entre eles
- Máximo 3 opções, a menos que peçam mais
- Exemplo real:

🚌 L.220 — 18:25 → 18:56
📍 Embarque: R. Rui Barbosa, 261
[📍 Rota a pé](https://www.google.com/maps/dir/?api=1&destination=R.%20Rui%20Barbosa%2C%20261%2C%20Americana%20-%20SP&travelmode=walking)

Grade semanal (Turma 57-05-B · Bloco 2 - Sala 073 - 1º piso):
- SEG: Prog. Orientada a Objetos (19:00-22:30) - Prof. Evandro Santaclara
- TER: Engenharia de Software (19:00-20:40) - Prof. Lucas Parizotto | Ativ. Extensão IV (20:50-22:30) - Prof. Marcio Veleda | Tópicos Integradores I (20:50-22:30) - Prof. Murilo Fujita
- QUA: Física Geral e Experimental (19:00-22:30) - Prof. Henrique Gimenes
- QUI: Sem aula
- SEX: Redes de Computadores (19:00-22:30) - Prof. Marcio Taglietta
- SAB: Ativ. Complementar IV (horário variável)

Atividades da FAM:
- Se o Pedro perguntar sobre atividades/tarefas, os dados estarão no contexto (quando consultados)
- Se não houver dados, informe que pode consultar e sugira perguntar novamente

Comandos: /aula, /onibus, /atividades, /help, /clear

========== TABELA COMPLETA DE HORÁRIOS ==========
""" + _TABELA_HORARIOS


def _formatar_para_telegram(texto: str) -> str:
    """Converte markdown links [text](url) para HTML <a> tags."""
    partes = []
    ultimo = 0
    for m in re.finditer(r'\[([^\]]+)\]\((https?://[^\)]+)\)', texto):
        partes.append(escape(texto[ultimo:m.start()]))
        partes.append(f'<a href="{escape(m.group(2))}">{escape(m.group(1))}</a>')
        ultimo = m.end()
    partes.append(escape(texto[ultimo:]))
    return ''.join(partes)


# ── Groq (primário) ────────────────────────────────────────────────────────

def _perguntar_groq(mensagem: str, chat_id: int, extra_contexto: str | None) -> str | None:
    """Envia para Groq API (OpenAI-compatible)."""
    if not GROQ_API_KEY:
        return None

    contexto = _contexto_dinamico()
    if extra_contexto:
        contexto += "\n\n" + extra_contexto

    if chat_id not in _historico:
        _historico[chat_id] = []
    hist = _historico[chat_id]

    hist.append({"role": "user", "content": mensagem})

    if len(hist) > MAX_HISTORICO:
        hist[:] = hist[-MAX_HISTORICO:]

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT + "\n\n--- CONTEXTO ATUAL ---\n" + contexto},
        *hist,
    ]

    for model in GROQ_MODELS:
        try:
            resp = requests.post(
                GROQ_URL,
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": 0.7,
                    "max_tokens": 2048,
                },
                timeout=15,
            )
            if resp.status_code == 429:
                logger.warning("Groq %s: 429, tentando próximo...", model)
                time.sleep(1)
                continue
            if resp.status_code != 200:
                logger.error("Groq %s: %d: %s", model, resp.status_code, resp.text[:200])
                hist.pop()
                return None

            data = resp.json()
            resposta = data["choices"][0]["message"]["content"].strip()

            hist.append({"role": "assistant", "content": resposta})

            if len(hist) > MAX_HISTORICO:
                hist[:] = hist[-MAX_HISTORICO:]

            return _formatar_para_telegram(resposta)

        except Exception as e:
            logger.error("Erro Groq %s: %s", model, e)
            continue

    hist.pop()
    return None


# ── Gemini (fallback) ──────────────────────────────────────────────────────

def _perguntar_gemini(mensagem: str, chat_id: int, extra_contexto: str | None) -> str | None:
    """Fallback: Gemini API."""
    if not GEMINI_API_KEY:
        return None

    contexto = _contexto_dinamico()
    if extra_contexto:
        contexto += "\n\n" + extra_contexto

    if chat_id not in _historico:
        _historico[chat_id] = []
    hist = _historico[chat_id]

    # Converte histórico para formato Gemini
    gemini_hist = []
    for msg in hist:
        role = "model" if msg["role"] == "assistant" else "user"
        gemini_hist.append({"role": role, "parts": [{"text": msg["content"]}]})

    gemini_hist.append({"role": "user", "parts": [{"text": mensagem}]})

    payload = {
        "system_instruction": {
            "parts": [{"text": SYSTEM_PROMPT + "\n\n--- CONTEXTO ATUAL ---\n" + contexto}]
        },
        "contents": gemini_hist,
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 2048,
        },
    }

    for model in GEMINI_MODELS:
        url = GEMINI_URL.format(model, GEMINI_API_KEY)
        try:
            resp = requests.post(url, json=payload, timeout=15)
            if resp.status_code in (429, 503):
                logger.warning("Gemini %s: %d, tentando próximo...", model, resp.status_code)
                time.sleep(1)
                continue
            if resp.status_code != 200:
                logger.error("Gemini %s: %d: %s", model, resp.status_code, resp.text[:200])
                return None

            data = resp.json()
            resposta = data["candidates"][0]["content"]["parts"][0]["text"].strip()

            # Salva no histórico unificado
            hist.append({"role": "user", "content": mensagem})
            hist.append({"role": "assistant", "content": resposta})

            if len(hist) > MAX_HISTORICO:
                hist[:] = hist[-MAX_HISTORICO:]

            return _formatar_para_telegram(resposta)

        except Exception as e:
            logger.error("Erro Gemini %s: %s", model, e)
            continue

    return None


# ── Interface pública ──────────────────────────────────────────────────────

def perguntar(mensagem: str, chat_id: int = 0, extra_contexto: str | None = None) -> str | None:
    """Tenta Groq primeiro, Gemini como fallback."""
    resposta = _perguntar_groq(mensagem, chat_id, extra_contexto)
    if resposta:
        return resposta

    logger.info("Groq falhou, tentando Gemini como fallback...")
    return _perguntar_gemini(mensagem, chat_id, extra_contexto)
