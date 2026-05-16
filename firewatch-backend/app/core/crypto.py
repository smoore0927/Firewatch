"""At-rest encryption for sensitive values (webhook HMAC secrets)."""

import base64
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.config import settings

__all__ = ["encrypt_for_storage", "decrypt_from_storage", "InvalidToken", "invalidate_caches"]

_KEK_CONTEXT = b"firewatch.webhook.kek.v1"


def _kek_to_fernet(kek_str: str) -> Fernet:
    """Accept either a raw Fernet key (base64) or any string we HKDF-derive from."""
    try:
        return Fernet(kek_str.encode("utf-8"))
    except (ValueError, Exception):
        hkdf = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=_KEK_CONTEXT)
        derived = hkdf.derive(kek_str.encode("utf-8"))
        return Fernet(base64.urlsafe_b64encode(derived))


@lru_cache(maxsize=1)
def _multi() -> MultiFernet:
    """Returns a MultiFernet — current KEK first, previous KEK (if set) for transition."""
    if settings.WEBHOOK_KEK:
        primary = _kek_to_fernet(settings.WEBHOOK_KEK)
    else:
        # Dev fallback: derive from SECRET_KEY
        primary = _kek_to_fernet(settings.SECRET_KEY)

    keys = [primary]
    if settings.WEBHOOK_KEK_PREVIOUS:
        keys.append(_kek_to_fernet(settings.WEBHOOK_KEK_PREVIOUS))
    return MultiFernet(keys)


def encrypt_for_storage(plaintext: str) -> str:
    return _multi().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_from_storage(ciphertext: str) -> str:
    return _multi().decrypt(ciphertext.encode("utf-8")).decode("utf-8")


def invalidate_caches() -> None:
    _multi.cache_clear()
