"""Tests for app.core.crypto — direct-Fernet at-rest encryption."""

from __future__ import annotations

import base64

import pytest
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core import crypto
from app.core.config import settings
from app.core.crypto import decrypt_from_storage, encrypt_for_storage


@pytest.fixture(autouse=True)
def _reset_cache() -> None:
    crypto.invalidate_caches()
    yield
    crypto.invalidate_caches()


def test_encrypt_is_non_deterministic():
    """Same plaintext yields different ciphertext each call (Fernet adds an IV)."""
    plaintext = "supersecret"
    c1 = encrypt_for_storage(plaintext)
    c2 = encrypt_for_storage(plaintext)
    assert c1 != c2
    assert decrypt_from_storage(c1) == plaintext
    assert decrypt_from_storage(c2) == plaintext


@pytest.mark.parametrize(
    "plaintext",
    [
        "",
        "ascii-only-12345",
        "with spaces and punctuation!?@#$%",
        "unicode: éàü\U0001f600",
        "x" * 4096,
    ],
)
def test_round_trip_arbitrary_utf8(plaintext: str):
    assert decrypt_from_storage(encrypt_for_storage(plaintext)) == plaintext


def test_tampered_ciphertext_raises_invalid_token():
    token = encrypt_for_storage("hello")
    tampered = token[:-2] + ("A" if token[-2] != "A" else "B") + token[-1]
    with pytest.raises(InvalidToken):
        decrypt_from_storage(tampered)


def test_kek_uses_env_when_set(monkeypatch):
    """With WEBHOOK_KEK set, the KEK is the env Fernet key, not derived."""
    env_kek = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "WEBHOOK_KEK", env_kek)
    crypto.invalidate_caches()

    ciphertext = encrypt_for_storage("payload")

    # The env Fernet decrypts the ciphertext directly.
    assert Fernet(env_kek.encode()).decrypt(ciphertext.encode()).decode() == "payload"

    # And the SECRET_KEY-derived KEK can NOT decrypt it.
    hkdf = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=crypto._KEK_CONTEXT)
    derived = hkdf.derive(settings.SECRET_KEY.encode("utf-8"))
    derived_kek = Fernet(base64.urlsafe_b64encode(derived))
    with pytest.raises(InvalidToken):
        derived_kek.decrypt(ciphertext.encode())


def test_kek_derived_from_secret_key_when_env_unset(monkeypatch):
    """With WEBHOOK_KEK unset, the KEK is derived from SECRET_KEY via HKDF."""
    monkeypatch.setattr(settings, "WEBHOOK_KEK", None)
    crypto.invalidate_caches()

    ciphertext = encrypt_for_storage("payload")

    # The hand-derived KEK must decrypt the ciphertext.
    hkdf = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=crypto._KEK_CONTEXT)
    derived = hkdf.derive(settings.SECRET_KEY.encode("utf-8"))
    derived_kek = Fernet(base64.urlsafe_b64encode(derived))
    assert derived_kek.decrypt(ciphertext.encode()).decode() == "payload"


def test_previous_kek_still_decrypts(monkeypatch):
    """Ciphertext encrypted under WEBHOOK_KEK_PREVIOUS still decrypts after rotation."""
    old_kek = Fernet.generate_key().decode()
    new_kek = Fernet.generate_key().decode()

    # 1. Encrypt under the old KEK.
    monkeypatch.setattr(settings, "WEBHOOK_KEK", old_kek)
    monkeypatch.setattr(settings, "WEBHOOK_KEK_PREVIOUS", None)
    crypto.invalidate_caches()
    legacy_ct = encrypt_for_storage("from-the-old-key")

    # 2. Rotate: new KEK becomes primary, old KEK is set as PREVIOUS for the transition.
    monkeypatch.setattr(settings, "WEBHOOK_KEK", new_kek)
    monkeypatch.setattr(settings, "WEBHOOK_KEK_PREVIOUS", old_kek)
    crypto.invalidate_caches()

    # Old ciphertext still decrypts via the second key in the MultiFernet chain.
    assert decrypt_from_storage(legacy_ct) == "from-the-old-key"

    # New ciphertext uses the new key.
    new_ct = encrypt_for_storage("from-the-new-key")
    assert decrypt_from_storage(new_ct) == "from-the-new-key"

    # The old KEK alone cannot decrypt the new ciphertext.
    with pytest.raises(InvalidToken):
        Fernet(old_kek.encode()).decrypt(new_ct.encode())
