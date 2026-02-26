"""
Módulo de banco de dados SQLite — CRUD de usuários multi-tenant.
"""

import json
import logging
import os
import sqlite3

from crypto import encrypt, decrypt

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
    """Cria registro básico (onboarding ainda não completo)."""
    con = _conn()
    try:
        con.execute(
            "INSERT OR IGNORE INTO usuarios (chat_id, nome) VALUES (?, ?)",
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


def is_registered(chat_id: int) -> bool:
    """Verifica se o usuário completou o onboarding."""
    user = get_user(chat_id)
    return user is not None and bool(user["onboarding_completo"])
