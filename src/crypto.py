"""
Módulo de criptografia — Fernet (symmetric encryption) para credenciais.
"""

import os
import logging

from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    """Retorna instância Fernet, criando a chave se necessário."""
    global _fernet
    if _fernet is not None:
        return _fernet

    key = os.getenv("FERNET_KEY", "")
    if not key:
        key = Fernet.generate_key().decode()
        logger.warning(
            "FERNET_KEY não encontrada no .env — gerada automaticamente: %s\n"
            "Adicione ao .env para persistir: FERNET_KEY=%s",
            key, key,
        )

    _fernet = Fernet(key.encode() if isinstance(key, str) else key)
    return _fernet


def encrypt(text: str) -> str:
    """Encripta texto e retorna token base64 como string."""
    f = _get_fernet()
    return f.encrypt(text.encode()).decode()


def decrypt(token: str) -> str:
    """Decripta token base64 e retorna texto original."""
    f = _get_fernet()
    return f.decrypt(token.encode()).decode()
