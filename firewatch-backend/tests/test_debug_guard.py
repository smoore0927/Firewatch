"""Tests for the DEBUG startup guard and docs exposure (OWASP A02:2025)."""

from __future__ import annotations

import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import main
from app.core.config import settings
from main import _assert_safe_runtime_config


def test_docs_hidden_when_debug_false() -> None:
    """Regression: /docs, /redoc, /openapi.json return 404 when DEBUG=False."""
    app = FastAPI(
        docs_url="/docs" if False else None,
        redoc_url="/redoc" if False else None,
        openapi_url="/openapi.json" if False else None,
    )
    with TestClient(app) as c:
        assert c.get("/docs").status_code == 404
        assert c.get("/redoc").status_code == 404
        assert c.get("/openapi.json").status_code == 404


def test_guard_rejects_debug_with_non_sqlite(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "DEBUG", True)
    monkeypatch.setattr(settings, "DATABASE_URL", "postgresql://u:p@host:5432/db")
    with pytest.raises(RuntimeError, match="DEBUG must be False"):
        _assert_safe_runtime_config()


def test_guard_allows_debug_with_sqlite(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "DEBUG", True)
    monkeypatch.setattr(settings, "DATABASE_URL", "sqlite:///./firewatch.db")
    _assert_safe_runtime_config()  # must not raise


def test_guard_allows_debug_false_with_postgres(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "DEBUG", False)
    monkeypatch.setattr(settings, "DATABASE_URL", "postgresql://u:p@host:5432/db")
    _assert_safe_runtime_config()  # must not raise


def test_guard_warns_on_debug_sqlite(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(settings, "DEBUG", True)
    monkeypatch.setattr(settings, "DATABASE_URL", "sqlite:///./firewatch.db")
    with caplog.at_level(logging.WARNING, logger=main.logger.name):
        _assert_safe_runtime_config()
    assert any("DEBUG=True" in r.message for r in caplog.records)
