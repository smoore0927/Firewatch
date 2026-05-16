"""Tests for app.core.secrets — pluggable secrets provider."""

from __future__ import annotations

from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from app.core import secrets as secrets_module
from app.core.secrets import (
    EnvProvider,
    FileProvider,
    SecretsProvider,
    get_provider,
    resolve_secrets,
)


# Live-service tests for Vault / Azure Key Vault / AWS Secrets Manager are
# intentionally omitted — they require a running external service plus real
# credentials, which doesn't belong in unit tests. The provider classes are
# thin lazy-import wrappers; exercise them in integration/staging environments.


@pytest.fixture(autouse=True)
def _clear_provider_cache() -> None:
    """Reset the lru_cache on get_provider() between tests."""
    get_provider.cache_clear()
    yield
    get_provider.cache_clear()


# ---------------------------------------------------------------------------
# EnvProvider
# ---------------------------------------------------------------------------


def test_env_provider_returns_value_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FW_TEST_KEY", "the-value")
    assert EnvProvider().get("FW_TEST_KEY") == "the-value"


def test_env_provider_returns_none_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FW_TEST_UNSET", raising=False)
    assert EnvProvider().get("FW_TEST_UNSET") is None


# ---------------------------------------------------------------------------
# FileProvider
# ---------------------------------------------------------------------------


def test_file_provider_reads_exact_name(tmp_path: Path) -> None:
    (tmp_path / "SECRET_KEY").write_text("from-exact-name")
    assert FileProvider(base_path=str(tmp_path)).get("SECRET_KEY") == "from-exact-name"


def test_file_provider_falls_back_to_lowercase(tmp_path: Path) -> None:
    (tmp_path / "secret_key").write_text("from-lower")
    assert FileProvider(base_path=str(tmp_path)).get("SECRET_KEY") == "from-lower"


def test_file_provider_falls_back_to_hyphenated(tmp_path: Path) -> None:
    (tmp_path / "secret-key").write_text("from-hyphenated")
    assert FileProvider(base_path=str(tmp_path)).get("SECRET_KEY") == "from-hyphenated"


def test_file_provider_strips_trailing_whitespace(tmp_path: Path) -> None:
    (tmp_path / "SECRET_KEY").write_text("value-with-newline\n")
    assert FileProvider(base_path=str(tmp_path)).get("SECRET_KEY") == "value-with-newline"


def test_file_provider_returns_none_for_missing(tmp_path: Path) -> None:
    assert FileProvider(base_path=str(tmp_path)).get("MISSING") is None


def test_file_provider_handles_missing_base_dir(tmp_path: Path) -> None:
    nonexistent = tmp_path / "does-not-exist"
    assert FileProvider(base_path=str(nonexistent)).get("ANY") is None


# ---------------------------------------------------------------------------
# get_provider() dispatch
# ---------------------------------------------------------------------------


def test_get_provider_defaults_to_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SECRETS_BACKEND", raising=False)
    assert isinstance(get_provider(), EnvProvider)


def test_get_provider_selects_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SECRETS_BACKEND", "file")
    monkeypatch.setenv("SECRETS_FILE_PATH", str(tmp_path))
    assert isinstance(get_provider(), FileProvider)


def test_get_provider_raises_on_unknown_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECRETS_BACKEND", "totally-made-up")
    with pytest.raises(RuntimeError, match="Unknown SECRETS_BACKEND"):
        get_provider()


# ---------------------------------------------------------------------------
# resolve_secrets()
# ---------------------------------------------------------------------------


def test_resolve_secrets_returns_only_non_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provider returns None for absent keys; resolve_secrets filters those out."""

    class PartialProvider(SecretsProvider):
        def get(self, key: str) -> str | None:
            return {"SECRET_KEY": "abc", "WEBHOOK_KEK": "def"}.get(key)

    monkeypatch.setattr(secrets_module, "get_provider", lambda: PartialProvider())
    out = resolve_secrets()
    assert out == {"SECRET_KEY": "abc", "WEBHOOK_KEK": "def"}


# ---------------------------------------------------------------------------
# Lifespan integration: resolve_secrets is honoured at startup
# ---------------------------------------------------------------------------


def test_lifespan_injects_resolved_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock resolve_secrets so lifespan injects the values; verify crypto uses them."""
    from fastapi.testclient import TestClient

    from app.core import crypto
    from app.core.config import settings
    from main import app

    injected_kek = Fernet.generate_key().decode()
    injected = {"SECRET_KEY": "test-injected-key", "WEBHOOK_KEK": injected_kek}

    # Force the lifespan to take the non-env path so resolve_secrets() actually runs.
    monkeypatch.setattr(settings, "SECRETS_BACKEND", "file")

    import main as main_module
    monkeypatch.setattr(main_module, "resolve_secrets", lambda: injected)

    crypto.invalidate_caches()
    with TestClient(app) as _:
        assert settings.SECRET_KEY == "test-injected-key"
        # Round-trip works under the injected KEK.
        token = crypto.encrypt_for_storage("payload")
        assert crypto.decrypt_from_storage(token) == "payload"
    crypto.invalidate_caches()
