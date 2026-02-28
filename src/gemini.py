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

import db
from aulas import DIAS_NOME, _load_grade
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


def _build_locais(user: dict) -> dict:
    """Monta dict de locais com base nos dados do usuário."""
    locais = {
        "casa": {"nome": "Casa", "bairro": user.get("endereco_casa") or "endereço não informado"},
        "faculdade": {"nome": "Faculdade (FAM)", "bairro": user.get("endereco_faculdade") or "FAM - Jd. Luciene, Americana-SP"},
    }
    if user.get("endereco_trabalho"):
        locais["trabalho"] = {"nome": "Trabalho", "bairro": user["endereco_trabalho"]}
    return locais


def _local_estimado(user: dict, grade: dict) -> str:
    """Estima onde o usuário está baseado no horário e dia da semana."""
    agora = datetime.now(TZ)
    hora = agora.hour + agora.minute / 60
    dia = agora.weekday()

    tem_trabalho = bool(user.get("endereco_trabalho"))

    if dia >= 5:
        return "casa"

    if tem_trabalho:
        # Horário de entrada no trabalho
        entrada_str = user.get("horario_entrada_trabalho") or "08:00"
        try:
            parts_e = entrada_str.split(":")
            entrada_hora = int(parts_e[0]) + int(parts_e[1]) / 60
        except (ValueError, IndexError):
            entrada_hora = 8.0

        # Horário de saída do trabalho
        saida_str = user.get("horario_saida_trabalho") or "18:00"
        try:
            parts = saida_str.split(":")
            saida_hora = int(parts[0]) + int(parts[1]) / 60
        except (ValueError, IndexError):
            saida_hora = 18.0

        if hora < entrada_hora:
            return "casa"
        if hora < saida_hora:
            return "trabalho"

        tem_aula = bool(grade.get(dia))
        if not tem_aula:
            if hora < saida_hora + 0.5:
                return "trabalho"
            return "casa"

        if hora < saida_hora + 1:
            return "trabalho"
        if hora < 23:
            return "faculdade"
        return "casa"
    else:
        # Sem trabalho
        tem_aula = bool(grade.get(dia))
        if tem_aula and hora >= 18 and hora < 23:
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


def _contexto_dinamico(user: dict, grade: dict) -> str:
    """Gera contexto com hora atual, local estimado e próximos ônibus relevantes."""
    agora = datetime.now(TZ)
    dia_semana = agora.weekday()
    amanha_dia = (agora + timedelta(days=1)).weekday()
    hora_str = agora.strftime("%H:%M")

    locais = _build_locais(user)
    local = _local_estimado(user, grade)
    local_info = locais.get(local, {"nome": local, "bairro": "desconhecido"})

    rotas_relevantes = {
        "casa": ["casa_trabalho", "casa_faculdade"],
        "trabalho": ["trabalho_faculdade", "trabalho_casa"],
        "faculdade": ["faculdade_casa"],
    }
    relevantes = rotas_relevantes.get(local, [])

    # Se não tem trabalho, remove rotas de trabalho
    if not user.get("endereco_trabalho"):
        relevantes = [r for r in relevantes if "trabalho" not in r]

    turno = (user.get("turno") or "noturno").capitalize()
    transporte = user.get("transporte") or "sou"
    transporte_labels = {"sou": "Ônibus SOU Americana", "emtu": "EMTU / Intermunicipal", "carro": "Carro / Carona", "outro": "Outro"}

    partes = [
        f"Agora: {agora.strftime('%A, %d/%m/%Y %H:%M')}",
        f"Turno: {turno}",
        f"Transporte: {transporte_labels.get(transporte, transporte)}",
        f"Localização estimada: {local_info['nome']} ({local_info['bairro']})",
    ]

    # Aulas hoje
    aulas_hoje = grade.get(dia_semana, [])
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
    aulas_amanha = grade.get(amanha_dia, [])
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

    # Info do aluno (curso, semestre, sala)
    info_aluno = db.get_info_aluno(user["chat_id"])
    if info_aluno:
        partes.append("\n=== DADOS ACADÊMICOS ===")
        if info_aluno.get("curso"):
            partes.append(f"  Curso: {info_aluno['curso']}")
        if info_aluno.get("semestre"):
            partes.append(f"  Semestre: {info_aluno['semestre']}º")
        if info_aluno.get("sala"):
            partes.append(f"  Sala/Localização: {info_aluno['sala']}")
        if info_aluno.get("turma_codigo"):
            partes.append(f"  Turma: {info_aluno['turma_codigo']}")

    # Notas e faltas (do cache no banco)
    notas = db.get_notas(user["chat_id"])
    eh_pro = db.is_pro(user["chat_id"])
    if notas:
        if eh_pro:
            from monitor import _calcular_simulacao
            partes.append("\n=== NOTAS, FALTAS E SIMULAÇÃO ===")
        else:
            partes.append("\n=== NOTAS E FALTAS ===")

        for n in notas:
            disc = n.get("disciplina", "?")
            n1 = n.get("n1")
            n2 = n.get("n2")
            n3 = n.get("n3")
            ms = n.get("media_semestral")
            mf = n.get("media_final")
            faltas = n.get("faltas", 0)
            max_f = n.get("max_faltas", 0)

            nota_parts = []
            if n1 is not None:
                nota_parts.append(f"N1={n1:.1f}")
            if n2 is not None:
                nota_parts.append(f"N2={n2:.1f}")
            if n3 is not None:
                nota_parts.append(f"N3={n3:.1f}")
            if ms is not None and not (ms == 0.0 and n1 is None and n2 is None and n3 is None):
                nota_parts.append(f"MS={ms:.1f}")
            if mf is not None:
                nota_parts.append(f"MF={mf:.1f}")
            notas_str = ", ".join(nota_parts) if nota_parts else "sem notas lançadas"

            faltas_str = f"faltas: {faltas}/{max_f}" if max_f else "sem controle de faltas"

            if eh_pro:
                sim = _calcular_simulacao(n)
                partes.append(f"  {disc}: {notas_str} | {faltas_str} | Simulação: {sim['texto']}")
            else:
                partes.append(f"  {disc}: {notas_str} | {faltas_str}")

    # Matérias reprovadas / DPs (do cache no banco)
    historico = db.get_historico(user["chat_id"])
    if historico:
        reprovados = [h for h in historico if "reprovado" in h.get("situacao", "").lower()]
        if reprovados:
            partes.append(f"\n=== DEPENDÊNCIAS (DPs) — {len(reprovados)} matérias ===")
            for h in reprovados:
                mf = h.get("media_final")
                mf_str = f" (MF: {mf:.1f})" if mf is not None else ""
                partes.append(f"  {h['disciplina']} — Reprovado no {h['semestre']}{mf_str}")
        else:
            partes.append("\n=== DEPENDÊNCIAS (DPs) === Nenhuma DP, histórico limpo.")

    # Próximos ônibus das rotas relevantes — só para SOU + Pro
    if transporte == "sou" and eh_pro:
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


def _build_grade_text(grade: dict) -> str:
    """Monta texto da grade semanal para o system prompt."""
    siglas = {0: "SEG", 1: "TER", 2: "QUA", 3: "QUI", 4: "SEX", 5: "SAB"}
    linhas = []
    for dia in range(6):
        aulas = grade.get(dia, [])
        sigla = siglas[dia]
        if not aulas:
            linhas.append(f"- {sigla}: Sem aula")
            continue
        partes_dia = []
        for a in aulas:
            horario = f"{a['inicio']}-{a['fim']}" if a['inicio'] else "horário variável"
            parte = f"{a['materia']} ({horario})"
            if a['prof']:
                parte += f" - Prof. {a['prof']}"
            partes_dia.append(parte)
        linhas.append(f"- {sigla}: {' | '.join(partes_dia)}")
    return "\n".join(linhas)


def build_system_prompt(user: dict, grade: dict) -> str:
    """Constrói system prompt personalizado por usuário."""
    nome = user.get("nome", "usuário")
    casa = user.get("endereco_casa") or "não informado"
    trabalho = user.get("endereco_trabalho") or ""
    faculdade = user.get("endereco_faculdade") or "FAM - Jd. Luciene, Americana-SP"
    horario_saida = user.get("horario_saida_trabalho") or "18:00"

    grade_text = _build_grade_text(grade)

    turno = (user.get("turno") or "noturno").capitalize()
    horario_entrada = user.get("horario_entrada_trabalho") or ""

    transporte = user.get("transporte") or "sou"
    transporte_labels = {"sou": "Ônibus SOU Americana", "emtu": "EMTU / Intermunicipal", "carro": "Carro / Carona", "outro": "Outro"}

    dados_usuario = f"""Dados de {nome}:
- Mora em: {casa}"""
    if trabalho:
        dados_usuario += f"\n- Trabalha em: {trabalho}"
        if horario_entrada:
            dados_usuario += f"\n- Entra no trabalho às {horario_entrada}"
        dados_usuario += f"\n- Sai do trabalho às {horario_saida}"
        if transporte == "sou":
            dados_usuario += " (considere ~15 min para chegar ao ponto de ônibus)"
    dados_usuario += f"\n- Estuda na {faculdade}"
    dados_usuario += f"\n- Turno: {turno}"
    dados_usuario += f"\n- Transporte: {transporte_labels.get(transporte, transporte)}"

    eh_pro_user = db.is_pro(user["chat_id"])

    if transporte == "sou" and eh_pro_user:
        regras_onibus = (
            "Regras sobre ônibus:\n"
            "- TODOS os horários estão na TABELA COMPLETA DE HORÁRIOS abaixo\n"
            "- NUNCA invente horários ou rotas — use SOMENTE os dados fornecidos\n"
            "- CRÍTICO: cada ROTA tem ORIGEM e DESTINO fixos. NUNCA sugira ônibus de uma rota com destino diferente do pedido\n\n"
            "FORMATAÇÃO (OBRIGATÓRIO — siga À RISCA):\n"
            "- Links do Maps SEMPRE em markdown: [texto](url) — NUNCA cole URL crua\n"
            "- Ao mencionar ônibus, SEMPRE use este formato exato, com quebra de linha entre cada bloco:\n\n"
            "🚌 L.XXX — HH:MM → HH:MM\n"
            "📍 Embarque: endereço\n"
            "[📍 Rota a pé](URL_DO_MAPS)\n\n"
            "- NUNCA liste ônibus em texto corrido. SEMPRE use o formato de bloco acima\n"
            "- Máximo 3 opções de ônibus, a menos que peçam mais"
        )
        tabela_horarios = "\n\n========== TABELA COMPLETA DE HORÁRIOS ==========\n" + _TABELA_HORARIOS
    elif transporte == "sou" and not eh_pro_user:
        regras_onibus = (
            f"Horários de ônibus (/onibus) é recurso EXCLUSIVO Pro. "
            f"Se {nome} perguntar sobre ônibus, diga que é recurso Pro e sugira /assinar. "
            "NUNCA forneça horários, rotas ou pontos de ônibus."
        )
        tabela_horarios = ""
    else:
        regras_onibus = (
            f"{nome} NÃO usa ônibus SOU Americana "
            f"(transporte: {transporte_labels.get(transporte, transporte)}). "
            "Se perguntar sobre ônibus SOU, informe que o comando /onibus é específico para SOU Americana."
        )
        tabela_horarios = ""

    return f"""\
Você é o FAMus, assistente pessoal de {nome} no Telegram. {nome} é estudante na FAM (Faculdade de Americana).

Personalidade:
- Fala como um brother paulista: gírias como "mano", "suave", "trampo", "busão" aparecem naturalmente, mas com MODERAÇÃO — no máximo 1-2 por mensagem
- Respostas CURTAS e DIRETAS. Vai reto ao ponto. Sem enrolação, sem repetir o que o usuário já sabe
- Máximo 2-3 frases por resposta quando possível. Só escreva mais se for realmente necessário
- Humor sutil e sarcasmo leve — uma piada rápida quando cabe, mas nunca à custa da clareza
- NUNCA comece com saudação (Olá, Oi, Bom dia) a menos que {nome} cumprimente primeiro
- Se {nome} cumprimentar, retribua de forma espirituosa e breve
- Tem memória da conversa atual — lembre-se do que foi dito e do CONTEXTO COMPLETO da conversa, não só da última mensagem
- NÃO pode alterar dados permanentemente. Se pedirem, sugira falar com o desenvolvedor
- NUNCA repita a mesma informação duas vezes na mesma resposta
- Evite frases de preenchimento como "Se precisar de mais alguma coisa...", "Espero ter ajudado!", "Suave?", "né?"
- Quando não souber algo, diga direto que não sabe. Sem enrolar
- IMPORTANTE: fale APENAS em português brasileiro. NUNCA use palavras ou expressões em inglês (nada de "fair play", "brother", "nice", etc). Use equivalentes em português

{dados_usuario}

Dados acadêmicos:
- Notas e faltas de {nome} estão no CONTEXTO ATUAL abaixo (quando disponíveis)
- DPs (matérias reprovadas) também estão no contexto quando disponíveis
- Fórmula FAM: MS = média ponderada de N1, N2, N3. MS >= 6.0 = aprovado direto. MS < 6.0 = precisa de AR. MF = (MS + AR) / 2, precisa MF >= 5.0
- Se não houver dados no contexto, sugira usar /notas ou /dp
- SIMULAÇÃO de notas (quanto precisa pra passar) é recurso EXCLUSIVO Pro. Se tiver dados de simulação no contexto, use-os. Se NÃO tiver, NUNCA calcule por conta própria — diga que é recurso Pro e sugira /simular ou /assinar

{regras_onibus}

Grade semanal:
{grade_text}

Comandos disponíveis: /aula, /notas (1x/semana Free, ilimitado Pro), /onibus (Pro), /faltas (Pro), /grade, /atividades (Pro), /simular (Pro), /dp (Pro), /assinar, /plano, /config, /help, /clear, /resetar
""" + tabela_horarios


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

    user = db.get_user(chat_id)
    if not user:
        return None

    grade = _load_grade(chat_id)
    contexto = _contexto_dinamico(user, grade)
    if extra_contexto:
        contexto += "\n\n" + extra_contexto

    system_prompt = build_system_prompt(user, grade)

    if chat_id not in _historico:
        _historico[chat_id] = []
    hist = _historico[chat_id]

    hist.append({"role": "user", "content": mensagem})

    if len(hist) > MAX_HISTORICO:
        hist[:] = hist[-MAX_HISTORICO:]

    messages = [
        {"role": "system", "content": system_prompt + "\n\n--- CONTEXTO ATUAL ---\n" + contexto},
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

    user = db.get_user(chat_id)
    if not user:
        return None

    grade = _load_grade(chat_id)
    contexto = _contexto_dinamico(user, grade)
    if extra_contexto:
        contexto += "\n\n" + extra_contexto

    system_prompt = build_system_prompt(user, grade)

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
            "parts": [{"text": system_prompt + "\n\n--- CONTEXTO ATUAL ---\n" + contexto}]
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
    """Tenta Groq primeiro, Gemini como fallback. Respeita limite Free."""
    # Checa limite de IA para usuários Free
    if chat_id:
        from monitor import checar_limite_ia, incrementar_ia
        bloqueado, restantes = checar_limite_ia(chat_id)
        if bloqueado:
            return (
                "⭐ Você atingiu o limite de 5 mensagens IA por dia (plano Free).\n"
                "Use /assinar pra desbloquear IA ilimitada (R$ 9,90/mês)."
            )

    resposta = _perguntar_groq(mensagem, chat_id, extra_contexto)
    if resposta:
        if chat_id:
            incrementar_ia(chat_id)
        return resposta

    logger.info("Groq falhou, tentando Gemini como fallback...")
    resposta = _perguntar_gemini(mensagem, chat_id, extra_contexto)
    if resposta and chat_id:
        incrementar_ia(chat_id)
    return resposta
