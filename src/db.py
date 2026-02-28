"""
Módulo de banco de dados SQLite — CRUD de usuários multi-tenant.
"""

import json
import logging
import os
import sqlite3
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from crypto import encrypt, decrypt

TZ = ZoneInfo("America/Sao_Paulo")

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "famus.db")

# Grade padrão do Pedro (usada na seed)
_PEDRO_GRADE = {
    "0": [
        {"materia": "Prog. Orientada a Objetos", "prof": "Evandro Santaclara", "inicio": "19:00", "fim": "22:30"},
    ],
    "1": [
        {"materia": "Engenharia de Software", "prof": "Lucas Parizotto", "inicio": "19:00", "fim": "20:40"},
        {"materia": "Ativ. Extensão IV", "prof": "Marcio Veleda", "inicio": "20:50", "fim": "22:30"},
        {"materia": "Tópicos Integradores I", "prof": "Murilo Fujita", "inicio": "20:50", "fim": "22:30"},
    ],
    "2": [
        {"materia": "Física Geral e Experimental", "prof": "Henrique Gimenes", "inicio": "19:00", "fim": "22:30"},
    ],
    "3": [],
    "4": [
        {"materia": "Redes de Computadores", "prof": "Marcio Taglietta", "inicio": "19:00", "fim": "22:30"},
    ],
    "5": [
        {"materia": "Ativ. Complementar IV", "prof": "", "inicio": "", "fim": ""},
    ],
}


def _conn() -> sqlite3.Connection:
    """Abre conexão com o banco."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Cria tabelas se não existirem + seed do Pedro."""
    con = _conn()
    try:
        con.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                chat_id             INTEGER PRIMARY KEY,
                nome                TEXT NOT NULL,
                endereco_casa       TEXT,
                endereco_trabalho   TEXT,
                endereco_faculdade  TEXT DEFAULT 'FAM - Jd. Luciene, Americana-SP',
                fam_login           TEXT,
                fam_senha           TEXT,
                horario_saida_trabalho TEXT DEFAULT '18:00',
                grade               TEXT,
                onboarding_completo INTEGER DEFAULT 0,
                created_at          TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        con.commit()

        # Migrações: adiciona colunas se não existem
        cols = [row[1] for row in con.execute("PRAGMA table_info(usuarios)").fetchall()]
        if "notas" not in cols:
            con.execute("ALTER TABLE usuarios ADD COLUMN notas TEXT")
            con.commit()
            logger.info("Coluna 'notas' adicionada à tabela usuarios.")
        if "info_aluno" not in cols:
            con.execute("ALTER TABLE usuarios ADD COLUMN info_aluno TEXT")
            con.commit()
            logger.info("Coluna 'info_aluno' adicionada à tabela usuarios.")
        if "historico" not in cols:
            con.execute("ALTER TABLE usuarios ADD COLUMN historico TEXT")
            con.commit()
            logger.info("Coluna 'historico' adicionada à tabela usuarios.")
        if "plano" not in cols:
            con.execute("ALTER TABLE usuarios ADD COLUMN plano TEXT DEFAULT 'free'")
            con.commit()
            logger.info("Coluna 'plano' adicionada à tabela usuarios.")
        if "plano_expira" not in cols:
            con.execute("ALTER TABLE usuarios ADD COLUMN plano_expira TEXT")
            con.commit()
            logger.info("Coluna 'plano_expira' adicionada à tabela usuarios.")
        if "trial_usado" not in cols:
            con.execute("ALTER TABLE usuarios ADD COLUMN trial_usado INTEGER DEFAULT 0")
            con.commit()
            logger.info("Coluna 'trial_usado' adicionada à tabela usuarios.")
        if "turno" not in cols:
            con.execute("ALTER TABLE usuarios ADD COLUMN turno TEXT DEFAULT 'noturno'")
            con.commit()
            logger.info("Coluna 'turno' adicionada à tabela usuarios.")
        if "horario_entrada_trabalho" not in cols:
            con.execute("ALTER TABLE usuarios ADD COLUMN horario_entrada_trabalho TEXT")
            con.commit()
            logger.info("Coluna 'horario_entrada_trabalho' adicionada à tabela usuarios.")
        if "transporte" not in cols:
            con.execute("ALTER TABLE usuarios ADD COLUMN transporte TEXT DEFAULT 'sou'")
            con.commit()
            logger.info("Coluna 'transporte' adicionada à tabela usuarios.")

        # Tabela de pagamentos
        con.execute("""
            CREATE TABLE IF NOT EXISTS pagamentos (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id     INTEGER NOT NULL,
                tipo        TEXT NOT NULL,
                mp_id       TEXT NOT NULL,
                status      TEXT DEFAULT 'pending',
                valor       REAL,
                criado_em   TEXT DEFAULT CURRENT_TIMESTAMP,
                aprovado_em TEXT
            )
        """)
        con.commit()

        # Tabela de sugestões
        con.execute("""
            CREATE TABLE IF NOT EXISTS sugestoes (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id     INTEGER NOT NULL,
                texto       TEXT NOT NULL,
                criado_em   TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        con.commit()

        # Tabela de tickets de suporte
        con.execute("""
            CREATE TABLE IF NOT EXISTS suporte (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id     INTEGER NOT NULL,
                texto       TEXT NOT NULL,
                criado_em   TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        con.commit()

        # Tabela de eventos / analytics
        con.execute("""
            CREATE TABLE IF NOT EXISTS eventos (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id     INTEGER NOT NULL,
                tipo        TEXT NOT NULL,
                timestamp   TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        con.commit()

        # Tabela de leads (quem interagiu mas pode não ter cadastrado)
        con.execute("""
            CREATE TABLE IF NOT EXISTS leads (
                chat_id         INTEGER PRIMARY KEY,
                username        TEXT,
                primeiro_nome   TEXT,
                primeiro_contato TEXT DEFAULT CURRENT_TIMESTAMP,
                ultimo_contato  TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        con.commit()

        # Seed: migra Pedro se TELEGRAM_CHAT_ID existe e banco está vazio
        chat_id_str = os.getenv("TELEGRAM_CHAT_ID", "")
        if chat_id_str:
            chat_id = int(chat_id_str)
            row = con.execute("SELECT 1 FROM usuarios WHERE chat_id = ?", (chat_id,)).fetchone()
            if row is None:
                fam_login = os.getenv("FAM_LOGIN", "")
                fam_senha = os.getenv("FAM_SENHA", "")

                enc_login = encrypt(fam_login) if fam_login else None
                enc_senha = encrypt(fam_senha) if fam_senha else None

                con.execute(
                    """INSERT INTO usuarios
                       (chat_id, nome, endereco_casa, endereco_trabalho, endereco_faculdade,
                        fam_login, fam_senha, horario_saida_trabalho, grade, onboarding_completo)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
                    (
                        chat_id,
                        "Pedro",
                        "Jd. da Balsa, Americana-SP",
                        "Vila Sta. Catarina, Americana-SP",
                        "FAM - Jd. Luciene, Americana-SP",
                        enc_login,
                        enc_senha,
                        "18:00",
                        json.dumps(_PEDRO_GRADE, ensure_ascii=False),
                    ),
                )
                con.commit()
                logger.info("Seed: usuário Pedro (chat_id=%d) migrado para o banco.", chat_id)
    finally:
        con.close()


# ── CRUD ─────────────────────────────────────────────────────────────────────


def get_user(chat_id: int) -> dict | None:
    """Retorna dict com dados do usuário ou None."""
    con = _conn()
    try:
        row = con.execute("SELECT * FROM usuarios WHERE chat_id = ?", (chat_id,)).fetchone()
        return dict(row) if row else None
    finally:
        con.close()


def create_user(chat_id: int, nome: str) -> None:
    """Cria registro básico ou atualiza nome se já existe (re-cadastro após reset)."""
    con = _conn()
    try:
        con.execute(
            "INSERT INTO usuarios (chat_id, nome) VALUES (?, ?) "
            "ON CONFLICT(chat_id) DO UPDATE SET nome = excluded.nome",
            (chat_id, nome),
        )
        con.commit()
    finally:
        con.close()


def update_user(chat_id: int, **fields) -> None:
    """Atualiza campos arbitrários do usuário."""
    if not fields:
        return
    cols = ", ".join(f"{k} = ?" for k in fields)
    vals = list(fields.values()) + [chat_id]
    con = _conn()
    try:
        con.execute(f"UPDATE usuarios SET {cols} WHERE chat_id = ?", vals)
        con.commit()
    finally:
        con.close()


def set_credentials(chat_id: int, login: str, senha: str) -> None:
    """Encripta e salva credenciais do portal FAM."""
    update_user(chat_id, fam_login=encrypt(login), fam_senha=encrypt(senha))


def get_credentials(chat_id: int) -> tuple[str, str] | None:
    """Retorna (login, senha) decriptados ou None."""
    user = get_user(chat_id)
    if not user or not user["fam_login"] or not user["fam_senha"]:
        return None
    return decrypt(user["fam_login"]), decrypt(user["fam_senha"])


def set_grade(chat_id: int, grade_dict: dict) -> None:
    """Serializa e salva grade no banco."""
    update_user(chat_id, grade=json.dumps(grade_dict, ensure_ascii=False))


def get_grade(chat_id: int) -> dict | None:
    """Retorna grade deserializada ou None."""
    user = get_user(chat_id)
    if not user or not user["grade"]:
        return None
    try:
        return json.loads(user["grade"])
    except json.JSONDecodeError:
        return None


def set_notas(chat_id: int, notas_list: list[dict]) -> None:
    """Serializa e salva notas no banco."""
    update_user(chat_id, notas=json.dumps(notas_list, ensure_ascii=False))


def get_notas(chat_id: int) -> list[dict] | None:
    """Retorna notas deserializadas ou None."""
    user = get_user(chat_id)
    if not user or not user["notas"]:
        return None
    try:
        return json.loads(user["notas"])
    except json.JSONDecodeError:
        return None


def set_info_aluno(chat_id: int, info: dict) -> None:
    """Serializa e salva info do aluno no banco."""
    update_user(chat_id, info_aluno=json.dumps(info, ensure_ascii=False))


def get_info_aluno(chat_id: int) -> dict | None:
    """Retorna info do aluno deserializada ou None."""
    user = get_user(chat_id)
    if not user or not user.get("info_aluno"):
        return None
    try:
        return json.loads(user["info_aluno"])
    except json.JSONDecodeError:
        return None


def set_historico(chat_id: int, historico_list: list[dict]) -> None:
    """Serializa e salva histórico no banco."""
    update_user(chat_id, historico=json.dumps(historico_list, ensure_ascii=False))


def get_historico(chat_id: int) -> list[dict] | None:
    """Retorna histórico deserializado ou None."""
    user = get_user(chat_id)
    if not user or not user.get("historico"):
        return None
    try:
        return json.loads(user["historico"])
    except json.JSONDecodeError:
        return None


def get_all_registered_users() -> list[dict]:
    """Retorna lista de dicts de todos os usuários com onboarding completo.

    Usado pelo job periódico (job_verificar_atualizacoes) para iterar
    sobre todos os usuários e checar notas/faltas novas.
    """
    con = _conn()
    try:
        rows = con.execute(
            "SELECT * FROM usuarios WHERE onboarding_completo = 1"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()


def is_registered(chat_id: int) -> bool:
    """Verifica se o usuário completou o onboarding."""
    user = get_user(chat_id)
    return user is not None and bool(user["onboarding_completo"])


# ── Eventos / Analytics ─────────────────────────────────────────────────────


def log_evento(chat_id: int, tipo: str) -> None:
    """Registra evento de interação (leve, sem conteúdo de mensagem)."""
    con = _conn()
    try:
        con.execute(
            "INSERT INTO eventos (chat_id, tipo) VALUES (?, ?)",
            (chat_id, tipo),
        )
        con.commit()
    except Exception as e:
        logger.warning("Erro ao logar evento: %s", e)
    finally:
        con.close()


def ultimo_evento(chat_id: int, tipo: str) -> str | None:
    """Retorna timestamp ISO do último evento desse tipo, ou None."""
    con = _conn()
    try:
        row = con.execute(
            "SELECT timestamp FROM eventos WHERE chat_id = ? AND tipo = ? ORDER BY id DESC LIMIT 1",
            (chat_id, tipo),
        ).fetchone()
        return row[0] if row else None
    finally:
        con.close()


def registrar_lead(chat_id: int, username: str | None = None, primeiro_nome: str | None = None) -> None:
    """Registra ou atualiza lead (qualquer pessoa que interagiu com o bot)."""
    con = _conn()
    try:
        con.execute(
            """INSERT INTO leads (chat_id, username, primeiro_nome)
               VALUES (?, ?, ?)
               ON CONFLICT(chat_id) DO UPDATE SET
                   ultimo_contato = CURRENT_TIMESTAMP,
                   username = COALESCE(excluded.username, leads.username),
                   primeiro_nome = COALESCE(excluded.primeiro_nome, leads.primeiro_nome)""",
            (chat_id, username, primeiro_nome),
        )
        con.commit()
    except Exception as e:
        logger.warning("Erro ao registrar lead: %s", e)
    finally:
        con.close()


# ── Plano / Pagamentos ─────────────────────────────────────────────────────


def set_plano(chat_id: int, plano: str, expira: str | None) -> None:
    """Define plano do usuário. expira = ISO datetime ou None."""
    update_user(chat_id, plano=plano, plano_expira=expira)


def get_plano(chat_id: int) -> dict | None:
    """Retorna {plano, plano_expira, trial_usado} ou None."""
    user = get_user(chat_id)
    if not user:
        return None
    return {
        "plano": user.get("plano") or "free",
        "plano_expira": user.get("plano_expira"),
        "trial_usado": user.get("trial_usado") or 0,
    }


def is_pro(chat_id: int) -> bool:
    """Checa se o usuário tem plano Pro ou Trial ativo (não expirado)."""
    info = get_plano(chat_id)
    if not info:
        return False
    plano = info["plano"]
    if plano not in ("pro", "trial"):
        return False
    expira = info["plano_expira"]
    if not expira:
        return plano in ("pro", "trial")
    try:
        dt_expira = datetime.fromisoformat(expira)
        if dt_expira.tzinfo is None:
            dt_expira = dt_expira.replace(tzinfo=TZ)
        return datetime.now(TZ) < dt_expira
    except (ValueError, TypeError):
        return False


def ativar_trial(chat_id: int) -> bool:
    """Ativa trial de 7 dias se ainda não usado. Retorna True se ativou."""
    info = get_plano(chat_id)
    if info and info["trial_usado"]:
        return False
    expira = (datetime.now(TZ) + timedelta(days=7)).isoformat()
    con = _conn()
    try:
        con.execute(
            "UPDATE usuarios SET plano = 'trial', plano_expira = ?, trial_usado = 1 WHERE chat_id = ?",
            (expira, chat_id),
        )
        con.commit()
        return True
    finally:
        con.close()


def criar_pagamento(chat_id: int, tipo: str, mp_id: str, valor: float) -> None:
    """Registra pagamento pendente na tabela pagamentos."""
    con = _conn()
    try:
        con.execute(
            "INSERT INTO pagamentos (chat_id, tipo, mp_id, valor) VALUES (?, ?, ?, ?)",
            (chat_id, tipo, mp_id, valor),
        )
        con.commit()
    finally:
        con.close()


def atualizar_pagamento(mp_id: str, status: str) -> None:
    """Atualiza status de um pagamento pelo ID do Mercado Pago."""
    con = _conn()
    try:
        aprovado_em = datetime.now(TZ).isoformat() if status == "approved" else None
        con.execute(
            "UPDATE pagamentos SET status = ?, aprovado_em = COALESCE(?, aprovado_em) WHERE mp_id = ?",
            (status, aprovado_em, mp_id),
        )
        con.commit()
    finally:
        con.close()


def get_pagamento_pendente(chat_id: int) -> dict | None:
    """Retorna o pagamento pendente mais recente do usuário ou None."""
    con = _conn()
    try:
        row = con.execute(
            "SELECT * FROM pagamentos WHERE chat_id = ? AND status = 'pending' ORDER BY id DESC LIMIT 1",
            (chat_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        con.close()


def get_usuarios_pro_expirados() -> list[dict]:
    """Retorna usuários Pro/Trial cujo plano_expira já passou."""
    con = _conn()
    try:
        agora = datetime.now(TZ).isoformat()
        rows = con.execute(
            "SELECT * FROM usuarios WHERE plano IN ('pro', 'trial') AND plano_expira IS NOT NULL AND plano_expira < ?",
            (agora,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()


def get_pagamento_por_chat(chat_id: int, tipo: str) -> dict | None:
    """Retorna pagamento mais recente de um tipo para o usuário."""
    con = _conn()
    try:
        row = con.execute(
            "SELECT * FROM pagamentos WHERE chat_id = ? AND tipo = ? ORDER BY id DESC LIMIT 1",
            (chat_id, tipo),
        ).fetchone()
        return dict(row) if row else None
    finally:
        con.close()


# ── Sugestões / Suporte ────────────────────────────────────────────────────


def salvar_sugestao(chat_id: int, texto: str) -> None:
    con = _conn()
    try:
        con.execute("INSERT INTO sugestoes (chat_id, texto) VALUES (?, ?)", (chat_id, texto))
        con.commit()
    finally:
        con.close()


def salvar_suporte(chat_id: int, texto: str) -> None:
    con = _conn()
    try:
        con.execute("INSERT INTO suporte (chat_id, texto) VALUES (?, ?)", (chat_id, texto))
        con.commit()
    finally:
        con.close()


def get_stats() -> dict:
    """Retorna estatísticas gerais do bot."""
    con = _conn()
    try:
        stats = {}

        # Leads totais
        stats["leads_total"] = con.execute("SELECT COUNT(*) FROM leads").fetchone()[0]

        # Usuários cadastrados
        stats["usuarios_cadastrados"] = con.execute(
            "SELECT COUNT(*) FROM usuarios WHERE onboarding_completo = 1"
        ).fetchone()[0]

        # Usuários que iniciaram mas não completaram
        stats["onboarding_incompleto"] = con.execute(
            "SELECT COUNT(*) FROM usuarios WHERE onboarding_completo = 0"
        ).fetchone()[0]

        # Eventos hoje
        stats["eventos_hoje"] = con.execute(
            "SELECT COUNT(*) FROM eventos WHERE DATE(timestamp) = DATE('now')"
        ).fetchone()[0]

        # Eventos últimos 7 dias
        stats["eventos_7d"] = con.execute(
            "SELECT COUNT(*) FROM eventos WHERE timestamp >= DATETIME('now', '-7 days')"
        ).fetchone()[0]

        # Top comandos (últimos 7 dias)
        rows = con.execute(
            """SELECT tipo, COUNT(*) as cnt FROM eventos
               WHERE timestamp >= DATETIME('now', '-7 days')
               GROUP BY tipo ORDER BY cnt DESC LIMIT 10"""
        ).fetchall()
        stats["top_comandos_7d"] = [(r[0], r[1]) for r in rows]

        # Usuários ativos (últimos 7 dias)
        stats["usuarios_ativos_7d"] = con.execute(
            "SELECT COUNT(DISTINCT chat_id) FROM eventos WHERE timestamp >= DATETIME('now', '-7 days')"
        ).fetchone()[0]

        # Leads que não cadastraram
        stats["leads_sem_cadastro"] = con.execute(
            """SELECT COUNT(*) FROM leads
               WHERE chat_id NOT IN (SELECT chat_id FROM usuarios WHERE onboarding_completo = 1)"""
        ).fetchone()[0]

        return stats
    finally:
        con.close()
