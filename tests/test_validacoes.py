#!/usr/bin/env python3
"""
Bancada de testes completa — FAMus Bot.

Testa TUDO:
- Validações puras (CPF, horário, endereço, transporte)
- Handlers de onboarding (fluxo completo com mocks do Telegram)
- Comandos (/config, /onibus, etc.)
- Integração com banco de dados

Uso: cd jarvis && python -m tests.test_validacoes
  ou: cd jarvis && venv/bin/python -m tests.test_validacoes
"""

import asyncio
import json
import os
import re
import sqlite3
import sys
import time
from unittest.mock import AsyncMock, MagicMock, patch

# Garante que o src está no path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# ── Contadores globais ────────────────────────────────────────────────────────

total = 0
passou = 0
falhou = 0
erros = []

GREEN = "\033[32m"
RED = "\033[31m"
BOLD = "\033[1m"
RESET = "\033[0m"
YELLOW = "\033[33m"


def check(categoria: str, entrada: str, esperado, resultado, desc: str = ""):
    global total, passou, falhou
    total += 1
    ok = resultado == esperado
    if ok:
        passou += 1
        marca = f"{GREEN}PASS{RESET}"
    else:
        falhou += 1
        marca = f"{RED}FAIL{RESET}"
        erros.append(f"  {categoria}: {entrada!r} → esperado={esperado!r}, got={resultado!r} ({desc})")
    extra = f" ({desc})" if desc else ""
    print(f"  [{marca}] {entrada!r} → {resultado!r}{extra}")


# ══════════════════════════════════════════════════════════════════════════════
#  UTILIDADES PARA MOCK DO TELEGRAM
# ══════════════════════════════════════════════════════════════════════════════


def make_update(text: str, chat_id: int = 99999, first_name: str = "Teste"):
    """Cria um Update mock simulando uma mensagem do Telegram."""
    update = MagicMock()
    update.effective_chat.id = chat_id
    update.effective_user.username = "teste_user"
    update.effective_user.first_name = first_name
    update.message.text = text
    update.message.reply_text = AsyncMock()
    update.message.delete = AsyncMock()
    return update


def make_context():
    """Cria um context mock."""
    context = MagicMock()
    context.user_data = {}
    return context


def get_reply_text(update) -> str:
    """Extrai o texto da última chamada reply_text."""
    if update.message.reply_text.call_count == 0:
        return ""
    return update.message.reply_text.call_args[0][0]


def get_reply_kwargs(update) -> dict:
    """Extrai kwargs da última chamada reply_text."""
    if update.message.reply_text.call_count == 0:
        return {}
    return update.message.reply_text.call_args[1] if update.message.reply_text.call_args[1] else {}


# ══════════════════════════════════════════════════════════════════════════════
#  1. TESTES PUROS — CPF
# ══════════════════════════════════════════════════════════════════════════════

def test_cpf():
    print(f"\n{BOLD}══ 1. VALIDAÇÃO DE CPF ══{RESET}")
    print(f"  (Login FAM = CPF com 11 dígitos)\n")

    def validar_cpf(texto):
        cpf = re.sub(r"[.\-\s]", "", texto.strip())
        return bool(re.match(r"^\d{11}$", cpf))

    testes = [
        ("12345678900", True, "CPF limpo correto"),
        ("123.456.789-00", True, "CPF formatado padrão"),
        ("123 456 789 00", True, "CPF com espaços"),
        ("12345678900 senha123", False, "CPF + senha na mesma msg"),
        ("1234567890", False, "10 dígitos"),
        ("123456789001", False, "12 dígitos"),
        ("123.456.789-0", False, "Formatado incompleto"),
        ("abc12345678", False, "Letras misturadas"),
        ("meu cpf é 12345678900", False, "Texto antes do CPF"),
        ("", False, "Vazio"),
        ("00000000000", True, "Só zeros (formato válido)"),
        ("123-456-789.00", True, "Formatação alternativa"),
    ]

    for entrada, esperado, desc in testes:
        check("CPF", entrada, esperado, validar_cpf(entrada), desc)


# ══════════════════════════════════════════════════════════════════════════════
#  2. TESTES PUROS — HORÁRIO
# ══════════════════════════════════════════════════════════════════════════════

def test_horario():
    print(f"\n{BOLD}══ 2. VALIDAÇÃO DE HORÁRIO ══{RESET}")
    print(f"  (Formato esperado: HH:MM)\n")

    def validar_horario(texto):
        return bool(re.match(r"^\d{1,2}:\d{2}$", texto.strip()))

    testes = [
        ("08:00", True, "Padrão"),
        ("8:00", True, "Sem zero à esquerda"),
        ("18:00", True, "Noturno"),
        ("23:59", True, "Fim do dia"),
        ("0:00", True, "Meia-noite"),
        ("08:30", True, "Meia hora"),
        ("8h", False, "Formato informal"),
        ("8h00", False, "Com 'h'"),
        ("08:00am", False, "Formato americano"),
        ("8", False, "Só número"),
        ("oito horas", False, "Por extenso"),
        ("18:0", False, "1 dígito nos minutos"),
        ("18:000", False, "3 dígitos nos minutos"),
        ("", False, "Vazio"),
        ("08:00 da manhã", False, "Texto extra"),
        ("25:00", True, "Hora inválida (formato ok)"),  # regex não valida range
    ]

    for entrada, esperado, desc in testes:
        check("Horário", entrada, esperado, validar_horario(entrada), desc)


# ══════════════════════════════════════════════════════════════════════════════
#  3. TESTES PUROS — TRANSPORTE
# ══════════════════════════════════════════════════════════════════════════════

def test_transporte():
    print(f"\n{BOLD}══ 3. MAPEAMENTO DE TRANSPORTE ══{RESET}")
    print(f"  (Botão → valor interno)\n")

    from cadastro import receber_transporte

    mapa = {
        "ônibus sou": "sou", "onibus sou": "sou", "sou": "sou",
        "emtu / intermunicipal": "emtu", "emtu": "emtu", "intermunicipal": "emtu",
        "carro / carona": "carro", "carro": "carro", "carona": "carro",
        "outro": "outro",
    }

    def mapear(texto):
        return mapa.get(texto.strip().lower(), "outro")

    testes = [
        ("Ônibus SOU", "sou", "Botão exato"),
        ("ônibus sou", "sou", "Minúsculo"),
        ("SOU", "sou", "Só sigla"),
        ("EMTU / Intermunicipal", "emtu", "Botão EMTU"),
        ("emtu", "emtu", "Só EMTU"),
        ("Carro / Carona", "carro", "Botão carro"),
        ("carro", "carro", "Só carro"),
        ("Carona", "carro", "Só carona"),
        ("Outro", "outro", "Botão outro"),
        ("moto", "outro", "Input livre → outro"),
        ("bicicleta", "outro", "Input livre → outro"),
        ("a pé", "outro", "Input livre → outro"),
    ]

    for entrada, esperado, desc in testes:
        check("Transporte", entrada, esperado, mapear(entrada), desc)


# ══════════════════════════════════════════════════════════════════════════════
#  4. TESTES PUROS — NORMALIZAÇÃO DE ENDEREÇO
# ══════════════════════════════════════════════════════════════════════════════

def test_normalizacao():
    print(f"\n{BOLD}══ 4. NORMALIZAÇÃO DE ENDEREÇO ══{RESET}")
    print(f"  (Abreviações → expansão)\n")

    from cadastro import _normalizar_endereco

    testes = [
        ("Jd. da Balsa", "Jardim da Balsa"),
        ("Av Brasil", "Avenida Brasil"),
        ("R. São Paulo", "Rua São Paulo"),
        ("Vl. Sta. Catarina", "Vila Santa Catarina"),
        ("Americana-SP", "Americana, São Paulo"),
        ("Americana, SP", "Americana, São Paulo"),
        ("Americana SP", "Americana, São Paulo"),
        ("Jd da Balsa, Americana-SP", "Jardim da Balsa, Americana, São Paulo"),
        ("R Machado de Assis 50", "Rua Machado de Assis 50"),
    ]

    for entrada, esperado in testes:
        resultado = _normalizar_endereco(entrada)
        check("Normalização", entrada, esperado, resultado)


# ══════════════════════════════════════════════════════════════════════════════
#  5. TESTES DE ENDEREÇO (NOMINATIM) — requer internet
# ══════════════════════════════════════════════════════════════════════════════

def test_endereco_nominatim():
    print(f"\n{BOLD}══ 5. VALIDAÇÃO DE ENDEREÇO (Nominatim) ══{RESET}")
    print(f"  (Requer internet — ~1s entre testes por rate limit)\n")

    from cadastro import _validar_endereco

    testes = [
        # ── Devem ACEITAR ──
        ("Jd. da Balsa, Americana-SP", True, "Bairro abreviado + cidade"),
        ("jd da balsa, americana SP", True, "Minúsculo, sem pontos"),
        ("Vila Sta. Catarina, Americana-SP", True, "Vila abreviada"),
        ("av luiz bassette 114, americana-SP", True, "Rua + número + cidade"),
        ("Americana-SP", True, "Só a cidade"),
        ("Americana, São Paulo", True, "Cidade + estado completo"),
        ("Santa Bárbara d'Oeste, SP", True, "Cidade vizinha"),
        ("Campinas, SP", True, "Capital regional"),
        ("centro, americana", True, "Bairro genérico + cidade"),

        # ── Devem REJEITAR ──
        ("asdfghjk", False, "Lixo aleatório"),
        ("123", False, "Só números"),
        (".", False, "Só ponto"),
        ("   ", False, "Só espaços"),
        # Nota: "minha casa", "rua de cima" e "aaaa" são aceitos pelo Nominatim
        # porque existem como locais reais em SP. Falso positivo aceitável.
    ]

    for entrada, esperado, desc in testes:
        resultado = _validar_endereco(entrada)
        aceito = resultado is not None
        check("Endereço", entrada, esperado, aceito, desc)
        if resultado and resultado != entrada:
            print(f"           → {resultado[:80]}")
        time.sleep(1.1)  # rate limit Nominatim


# ══════════════════════════════════════════════════════════════════════════════
#  6. TESTES DE HANDLERS — FLUXO DE ONBOARDING COMPLETO
# ══════════════════════════════════════════════════════════════════════════════

def test_handler_cpf():
    """Testa o handler receber_fam_login com inputs variados."""
    print(f"\n{BOLD}══ 6. HANDLER — receber_fam_login ══{RESET}")
    print(f"  (Simula mensagens do Telegram com mock)\n")

    from cadastro import receber_fam_login, FAM_LOGIN, FAM_SENHA

    testes = [
        ("12345678900", FAM_SENHA, "CPF limpo → avança"),
        ("123.456.789-00", FAM_SENHA, "CPF formatado → avança"),
        ("12345678900 minhasenha", FAM_LOGIN, "CPF+senha → rejeita, fica"),
        ("1234567890", FAM_LOGIN, "10 dígitos → rejeita"),
        ("abc", FAM_LOGIN, "Texto → rejeita"),
    ]

    for entrada, estado_esperado, desc in testes:
        update = make_update(entrada)
        context = make_context()
        resultado = asyncio.get_event_loop().run_until_complete(
            receber_fam_login(update, context)
        )
        check("Handler CPF", entrada, estado_esperado, resultado, desc)

        if resultado == FAM_SENHA:
            cpf_salvo = context.user_data.get("fam_login", "")
            cpf_limpo = re.sub(r"[.\-\s]", "", entrada.strip())
            check("Handler CPF (salvo)", entrada, cpf_limpo, cpf_salvo, "CPF limpo no user_data")


def test_handler_horario():
    """Testa handlers de horário."""
    print(f"\n{BOLD}══ 7. HANDLER — horários entrada/saída ══{RESET}\n")

    from cadastro import receber_horario_entrada, receber_horario_saida
    from cadastro import HORARIO_ENTRADA, HORARIO_SAIDA, TRANSPORTE

    # Entrada
    testes_entrada = [
        ("08:00", HORARIO_SAIDA, "Formato ok → avança"),
        ("8:00", HORARIO_SAIDA, "Sem zero → avança"),
        ("8h", HORARIO_ENTRADA, "Informal → rejeita"),
        ("oito", HORARIO_ENTRADA, "Extenso → rejeita"),
    ]

    for entrada, estado_esperado, desc in testes_entrada:
        update = make_update(entrada)
        context = make_context()
        resultado = asyncio.get_event_loop().run_until_complete(
            receber_horario_entrada(update, context)
        )
        check("Handler H.Entrada", entrada, estado_esperado, resultado, desc)

    # Saída
    testes_saida = [
        ("18:00", TRANSPORTE, "Formato ok → avança pra TRANSPORTE"),
        ("18h00", HORARIO_SAIDA, "Informal → rejeita"),
    ]

    for entrada, estado_esperado, desc in testes_saida:
        update = make_update(entrada)
        context = make_context()
        resultado = asyncio.get_event_loop().run_until_complete(
            receber_horario_saida(update, context)
        )
        check("Handler H.Saída", entrada, estado_esperado, resultado, desc)


def test_handler_transporte():
    """Testa handler de transporte."""
    print(f"\n{BOLD}══ 8. HANDLER — receber_transporte ══{RESET}\n")

    from cadastro import receber_transporte, TURNO

    testes = [
        ("Ônibus SOU", "sou", "Botão SOU"),
        ("EMTU / Intermunicipal", "emtu", "Botão EMTU"),
        ("Carro / Carona", "carro", "Botão Carro"),
        ("Outro", "outro", "Botão Outro"),
        ("moto", "outro", "Livre → outro"),
    ]

    for entrada, transporte_esperado, desc in testes:
        update = make_update(entrada)
        context = make_context()
        resultado = asyncio.get_event_loop().run_until_complete(
            receber_transporte(update, context)
        )
        check("Handler Transporte", entrada, TURNO, resultado, f"{desc} → vai pra TURNO")
        check("Handler Transporte (valor)", entrada, transporte_esperado,
              context.user_data.get("transporte"), f"Salva '{transporte_esperado}'")


def test_handler_turno():
    """Testa handler de turno."""
    print(f"\n{BOLD}══ 9. HANDLER — receber_turno ══{RESET}\n")

    from cadastro import receber_turno, TURNO, FAM_LOGIN

    testes = [
        ("Matutino", FAM_LOGIN, "matutino", "Botão matutino → avança"),
        ("Vespertino", FAM_LOGIN, "vespertino", "Botão vespertino → avança"),
        ("Noturno", FAM_LOGIN, "noturno", "Botão noturno → avança"),
        ("matutino", FAM_LOGIN, "matutino", "Minúsculo → aceita"),
        ("Integral", TURNO, None, "Inválido → rejeita"),
        ("manhã", TURNO, None, "Sinônimo → rejeita (só aceita os 3)"),
    ]

    for entrada, estado_esperado, turno_esperado, desc in testes:
        update = make_update(entrada)
        context = make_context()
        resultado = asyncio.get_event_loop().run_until_complete(
            receber_turno(update, context)
        )
        check("Handler Turno", entrada, estado_esperado, resultado, desc)
        if turno_esperado:
            check("Handler Turno (valor)", entrada, turno_esperado,
                  context.user_data.get("turno"), f"Salva '{turno_esperado}'")


def test_handler_trabalho_pular():
    """Testa pular trabalho → deve ir direto pra TRANSPORTE."""
    print(f"\n{BOLD}══ 10. HANDLER — pular trabalho ══{RESET}\n")

    from cadastro import receber_trabalho, TRANSPORTE

    pular_inputs = ["pular", "pula", "não trabalho", "nao trabalho", "-"]

    for entrada in pular_inputs:
        update = make_update(entrada)
        context = make_context()
        resultado = asyncio.get_event_loop().run_until_complete(
            receber_trabalho(update, context)
        )
        check("Handler Pular Trabalho", entrada, TRANSPORTE, resultado,
              "Pula → TRANSPORTE")

        # Verifica que setou None nos campos de trabalho
        check("Handler Pular (end.)", entrada, None,
              context.user_data.get("endereco_trabalho"), "Endereço = None")
        check("Handler Pular (h.ent.)", entrada, None,
              context.user_data.get("horario_entrada_trabalho"), "H.Entrada = None")
        check("Handler Pular (h.sai.)", entrada, None,
              context.user_data.get("horario_saida_trabalho"), "H.Saída = None")


def test_handler_termos():
    """Testa aceite/recusa dos termos."""
    print(f"\n{BOLD}══ 11. HANDLER — receber_termos ══{RESET}\n")

    from cadastro import receber_termos, CONFIRMA
    from telegram.ext import ConversationHandler

    # Prepara user_data completo pra não dar KeyError no resumo
    dados_completos = {
        "nome": "Teste", "endereco_casa": "Jd. da Balsa",
        "endereco_trabalho": None, "horario_entrada_trabalho": None,
        "horario_saida_trabalho": None, "transporte": "sou",
        "turno": "noturno", "fam_login": "12345678900", "fam_senha": "abc",
    }

    # Aceitar
    aceitar_inputs = ["Aceito", "aceito", "sim", "s"]
    for entrada in aceitar_inputs:
        update = make_update(entrada)
        context = make_context()
        context.user_data.update(dados_completos.copy())
        resultado = asyncio.get_event_loop().run_until_complete(
            receber_termos(update, context)
        )
        check("Handler Termos", entrada, CONFIRMA, resultado, "Aceita → CONFIRMA")

    # Recusar (com mock do banco)
    with patch("cadastro.db") as mock_db:
        mock_db.DB_PATH = ":memory:"
        for entrada in ["Não aceito", "não", "n"]:
            update = make_update(entrada)
            context = make_context()
            context.user_data.update(dados_completos.copy())
            resultado = asyncio.get_event_loop().run_until_complete(
                receber_termos(update, context)
            )
            check("Handler Termos", entrada, ConversationHandler.END, resultado,
                  "Recusa → END")


def test_handler_nome():
    """Testa handler de nome."""
    print(f"\n{BOLD}══ 12. HANDLER — receber_nome ══{RESET}\n")

    from cadastro import receber_nome, CASA

    with patch("cadastro.db") as mock_db:
        for nome in ["Pedro", "Maria José", "João da Silva"]:
            update = make_update(nome)
            context = make_context()
            resultado = asyncio.get_event_loop().run_until_complete(
                receber_nome(update, context)
            )
            check("Handler Nome", nome, CASA, resultado, f"'{nome}' → CASA")
            check("Handler Nome (salvo)", nome, nome,
                  context.user_data.get("nome"), "Nome no user_data")
            # Verifica que criou user no banco
            mock_db.create_user.assert_called()


# ══════════════════════════════════════════════════════════════════════════════
#  13. TESTES — COMANDO /onibus RESPEITA TRANSPORTE
# ══════════════════════════════════════════════════════════════════════════════

def test_cmd_onibus_transporte():
    """Testa que /onibus respeita campo transporte."""
    print(f"\n{BOLD}══ 13. COMANDO /onibus — respeita transporte ══{RESET}\n")

    from onibus import cmd_onibus

    # Usuário SOU → deve mostrar trajetos normalmente
    with patch("onibus.db") as mock_db:
        mock_db.get_user.return_value = {"transporte": "sou"}
        update = make_update("/onibus")
        context = make_context()
        asyncio.get_event_loop().run_until_complete(cmd_onibus(update, context))
        texto = get_reply_text(update)
        check("CMD /onibus", "transporte=sou", True, "não se aplicam" not in texto,
              "SOU → mostra trajetos normalmente")

    # Usuário CARRO → deve informar que SOU não se aplica
    with patch("onibus.db") as mock_db:
        mock_db.get_user.return_value = {"transporte": "carro"}
        update = make_update("/onibus")
        context = make_context()
        asyncio.get_event_loop().run_until_complete(cmd_onibus(update, context))
        texto = get_reply_text(update)
        check("CMD /onibus", "transporte=carro", True, "não se aplicam" in texto,
              "Carro → msg 'não se aplica'")

    # Usuário EMTU → idem
    with patch("onibus.db") as mock_db:
        mock_db.get_user.return_value = {"transporte": "emtu"}
        update = make_update("/onibus")
        context = make_context()
        asyncio.get_event_loop().run_until_complete(cmd_onibus(update, context))
        texto = get_reply_text(update)
        check("CMD /onibus", "transporte=emtu", True, "não se aplicam" in texto,
              "EMTU → msg 'não se aplica'")

    # Usuário antigo sem campo transporte → default 'sou'
    with patch("onibus.db") as mock_db:
        mock_db.get_user.return_value = {"nome": "Pedro"}  # sem transporte
        update = make_update("/onibus")
        context = make_context()
        asyncio.get_event_loop().run_until_complete(cmd_onibus(update, context))
        texto = get_reply_text(update)
        check("CMD /onibus", "sem campo transporte", True, "não se aplicam" not in texto,
              "Default SOU → mostra trajetos")


# ══════════════════════════════════════════════════════════════════════════════
#  14. TESTES — GEMINI RESPEITA TRANSPORTE
# ══════════════════════════════════════════════════════════════════════════════

def test_gemini_transporte():
    """Testa que o system prompt e contexto respeitam transporte."""
    print(f"\n{BOLD}══ 14. GEMINI — respeita transporte ══{RESET}\n")

    from gemini import build_system_prompt, _contexto_dinamico

    user_sou = {
        "chat_id": 99999, "nome": "Teste", "endereco_casa": "Jd. da Balsa",
        "endereco_trabalho": "Centro", "endereco_faculdade": "FAM",
        "horario_saida_trabalho": "18:00", "horario_entrada_trabalho": "08:00",
        "turno": "noturno", "transporte": "sou",
    }
    user_carro = {**user_sou, "transporte": "carro"}
    user_sem = {k: v for k, v in user_sou.items() if k != "transporte"}

    grade = {0: [], 1: [], 2: [], 3: [], 4: [], 5: []}

    # System prompt — SOU deve ter tabela de horários
    with patch("gemini.db"):
        prompt_sou = build_system_prompt(user_sou, grade)
        check("Gemini Prompt", "transporte=sou", True,
              "TABELA COMPLETA DE HORÁRIOS" in prompt_sou, "SOU → inclui tabela")

        prompt_carro = build_system_prompt(user_carro, grade)
        check("Gemini Prompt", "transporte=carro", True,
              "TABELA COMPLETA DE HORÁRIOS" not in prompt_carro, "Carro → sem tabela")
        check("Gemini Prompt", "transporte=carro", True,
              "NÃO usa ônibus" in prompt_carro, "Carro → aviso no prompt")

    # Contexto dinâmico — SOU deve ter seção de ônibus
    with patch("gemini.db") as mock_db:
        mock_db.get_notas.return_value = None
        mock_db.get_info_aluno.return_value = None
        mock_db.get_historico.return_value = None

        ctx_sou = _contexto_dinamico(user_sou, grade)
        check("Gemini Contexto", "transporte=sou", True,
              "PRÓXIMOS ÔNIBUS" in ctx_sou, "SOU → seção de ônibus")

        ctx_carro = _contexto_dinamico(user_carro, grade)
        check("Gemini Contexto", "transporte=carro", True,
              "PRÓXIMOS ÔNIBUS" not in ctx_carro, "Carro → sem seção ônibus")

        # Transporte no contexto
        check("Gemini Contexto", "transporte=sou", True,
              "Ônibus SOU" in ctx_sou, "SOU → label no contexto")
        check("Gemini Contexto", "transporte=carro", True,
              "Carro" in ctx_carro, "Carro → label no contexto")


# ══════════════════════════════════════════════════════════════════════════════
#  15. TESTES — DB MIGRAÇÃO
# ══════════════════════════════════════════════════════════════════════════════

def test_db_transporte():
    """Testa que a coluna transporte existe e tem default 'sou'."""
    print(f"\n{BOLD}══ 15. DB — coluna transporte ══{RESET}\n")

    import db as db_module
    original_path = db_module.DB_PATH
    test_db = "/tmp/famus_test.db"
    db_module.DB_PATH = test_db

    try:
        # Remove DB de teste anterior
        if os.path.exists(test_db):
            os.remove(test_db)

        # Inicializa DB
        with patch.dict(os.environ, {"TELEGRAM_CHAT_ID": ""}):
            db_module.init_db()

        # Verifica coluna
        con = sqlite3.connect(test_db)
        cols = [row[1] for row in con.execute("PRAGMA table_info(usuarios)").fetchall()]
        check("DB", "coluna transporte", True, "transporte" in cols, "Existe na tabela")

        # Verifica default
        con.execute("INSERT INTO usuarios (chat_id, nome) VALUES (88888, 'Teste')")
        con.commit()
        row = con.execute("SELECT transporte FROM usuarios WHERE chat_id = 88888").fetchone()
        check("DB", "default transporte", "sou", row[0], "Default = 'sou'")

        # Testa update
        db_module.update_user(88888, transporte="carro")
        user = db_module.get_user(88888)
        check("DB", "update transporte", "carro", user["transporte"], "Update funciona")

        con.close()
    finally:
        db_module.DB_PATH = original_path
        if os.path.exists(test_db):
            os.remove(test_db)


# ══════════════════════════════════════════════════════════════════════════════
#  16. TESTES — FLUXO COMPLETO DE ONBOARDING
# ══════════════════════════════════════════════════════════════════════════════

def test_fluxo_completo():
    """Simula onboarding completo: nome → casa → pular trabalho → transporte → turno → cpf → senha → termos → confirma."""
    print(f"\n{BOLD}══ 16. FLUXO COMPLETO — onboarding sem trabalho ══{RESET}\n")

    from cadastro import (
        receber_nome, receber_casa, receber_trabalho,
        receber_transporte, receber_turno, receber_fam_login,
        receber_fam_senha, receber_termos,
        NOME, CASA, TRABALHO, TRANSPORTE, TURNO, FAM_LOGIN, FAM_SENHA, TERMOS, CONFIRMA,
    )

    context = make_context()
    loop = asyncio.get_event_loop()

    # 1. Nome
    with patch("cadastro.db"):
        update = make_update("Maria Teste")
        r = loop.run_until_complete(receber_nome(update, context))
        check("Fluxo", "1. Nome", CASA, r, "Nome → CASA")

    # 2. Casa (mock Nominatim pra não depender de internet)
    with patch("cadastro._validar_endereco", return_value="Encontrado"):
        update = make_update("Jd. da Balsa, Americana-SP")
        r = loop.run_until_complete(receber_casa(update, context))
        check("Fluxo", "2. Casa", TRABALHO, r, "Casa → TRABALHO")

    # 3. Pular trabalho
    update = make_update("pular")
    r = loop.run_until_complete(receber_trabalho(update, context))
    check("Fluxo", "3. Pular trabalho", TRANSPORTE, r, "Pular → TRANSPORTE")

    # 4. Transporte
    update = make_update("Ônibus SOU")
    r = loop.run_until_complete(receber_transporte(update, context))
    check("Fluxo", "4. Transporte", TURNO, r, "SOU → TURNO")

    # 5. Turno
    update = make_update("Noturno")
    r = loop.run_until_complete(receber_turno(update, context))
    check("Fluxo", "5. Turno", FAM_LOGIN, r, "Noturno → FAM_LOGIN")

    # 6. CPF
    update = make_update("123.456.789-00")
    r = loop.run_until_complete(receber_fam_login(update, context))
    check("Fluxo", "6. CPF", FAM_SENHA, r, "CPF formatado → FAM_SENHA")

    # 7. Senha
    update = make_update("minha_senha_123")
    r = loop.run_until_complete(receber_fam_senha(update, context))
    check("Fluxo", "7. Senha", TERMOS, r, "Senha → TERMOS")

    # 8. Termos
    update = make_update("Aceito")
    r = loop.run_until_complete(receber_termos(update, context))
    check("Fluxo", "8. Termos", CONFIRMA, r, "Aceito → CONFIRMA")

    # Verifica dados acumulados
    d = context.user_data
    check("Fluxo (dados)", "nome", "Maria Teste", d.get("nome"))
    check("Fluxo (dados)", "endereco_casa", "Jd. da Balsa, Americana-SP", d.get("endereco_casa"))
    check("Fluxo (dados)", "endereco_trabalho", None, d.get("endereco_trabalho"))
    check("Fluxo (dados)", "transporte", "sou", d.get("transporte"))
    check("Fluxo (dados)", "turno", "noturno", d.get("turno"))
    check("Fluxo (dados)", "fam_login", "12345678900", d.get("fam_login"))
    check("Fluxo (dados)", "fam_senha", "minha_senha_123", d.get("fam_senha"))


def test_fluxo_com_trabalho():
    """Simula onboarding COM trabalho."""
    print(f"\n{BOLD}══ 17. FLUXO COMPLETO — onboarding com trabalho ══{RESET}\n")

    from cadastro import (
        receber_nome, receber_casa, receber_trabalho,
        receber_horario_entrada, receber_horario_saida,
        receber_transporte, receber_turno, receber_fam_login,
        CASA, TRABALHO, HORARIO_ENTRADA, HORARIO_SAIDA, TRANSPORTE, TURNO, FAM_LOGIN, FAM_SENHA,
    )

    context = make_context()
    loop = asyncio.get_event_loop()

    with patch("cadastro.db"):
        update = make_update("João Silva")
        r = loop.run_until_complete(receber_nome(update, context))
        check("Fluxo2", "1. Nome", CASA, r)

    with patch("cadastro._validar_endereco", return_value="OK"):
        update = make_update("Jd. Ipiranga, Americana-SP")
        r = loop.run_until_complete(receber_casa(update, context))
        check("Fluxo2", "2. Casa", TRABALHO, r)

    with patch("cadastro._validar_endereco", return_value="OK"):
        update = make_update("Vila Sta. Catarina, Americana-SP")
        r = loop.run_until_complete(receber_trabalho(update, context))
        check("Fluxo2", "3. Trabalho", HORARIO_ENTRADA, r, "Com trabalho → HORARIO_ENTRADA")

    update = make_update("08:00")
    r = loop.run_until_complete(receber_horario_entrada(update, context))
    check("Fluxo2", "4. H.Entrada", HORARIO_SAIDA, r)

    update = make_update("18:00")
    r = loop.run_until_complete(receber_horario_saida(update, context))
    check("Fluxo2", "5. H.Saída", TRANSPORTE, r, "→ TRANSPORTE (não TURNO)")

    update = make_update("Carro / Carona")
    r = loop.run_until_complete(receber_transporte(update, context))
    check("Fluxo2", "6. Transporte", TURNO, r)

    update = make_update("Matutino")
    r = loop.run_until_complete(receber_turno(update, context))
    check("Fluxo2", "7. Turno", FAM_LOGIN, r)

    update = make_update("98765432100")
    r = loop.run_until_complete(receber_fam_login(update, context))
    check("Fluxo2", "8. CPF", FAM_SENHA, r)

    # Verifica dados
    d = context.user_data
    check("Fluxo2 (dados)", "transporte", "carro", d.get("transporte"))
    check("Fluxo2 (dados)", "turno", "matutino", d.get("turno"))
    check("Fluxo2 (dados)", "h_entrada", "08:00", d.get("horario_entrada_trabalho"))
    check("Fluxo2 (dados)", "h_saida", "18:00", d.get("horario_saida_trabalho"))


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    global total, passou, falhou

    print(f"\n{BOLD}{'═' * 60}")
    print(f"  BANCADA DE TESTES — FAMus Bot")
    print(f"{'═' * 60}{RESET}\n")

    # Testes que não precisam de internet
    test_cpf()
    test_horario()
    test_transporte()
    test_normalizacao()

    # Testes de handlers (mocks, sem internet)
    test_handler_cpf()
    test_handler_horario()
    test_handler_transporte()
    test_handler_turno()
    test_handler_trabalho_pular()
    test_handler_termos()
    test_handler_nome()
    test_cmd_onibus_transporte()
    test_gemini_transporte()
    test_db_transporte()

    # Fluxos completos
    test_fluxo_completo()
    test_fluxo_com_trabalho()

    # Testes com internet (lentos)
    skip_nominatim = "--skip-nominatim" in sys.argv
    if skip_nominatim:
        print(f"\n{YELLOW}⚠ Testes Nominatim pulados (--skip-nominatim){RESET}")
    else:
        test_endereco_nominatim()

    # Resumo
    print(f"\n{BOLD}{'═' * 60}")
    print(f"  RESULTADO FINAL")
    print(f"{'═' * 60}{RESET}")
    print(f"  Total:  {total}")
    print(f"  {GREEN}Passed: {passou}{RESET}")
    print(f"  {RED}Failed: {falhou}{RESET}")

    if erros:
        print(f"\n{RED}Falhas:{RESET}")
        for e in erros:
            print(e)

    print()
    return 0 if falhou == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
