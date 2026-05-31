"""Unit tests for validate_outbound_url (SSRF defense)."""

from __future__ import annotations

import socket

import pytest

from app.core.config import settings
from app.core.url_safety import ResolvedTarget, validate_outbound_url


def _addrinfo(addr: str, family: int = socket.AF_INET) -> list[tuple]:
    sockaddr = (addr, 0) if family == socket.AF_INET else (addr, 0, 0, 0)
    return [(family, socket.SOCK_STREAM, 0, "", sockaddr)]


def _mock_dns(monkeypatch, addr: str, family: int = socket.AF_INET) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: _addrinfo(addr, family))


# --- DEBUG mode: internal IPs must still be rejected (the regression) --------


def test_debug_rejects_loopback(monkeypatch):
    """Regression for the SSRF finding: http://localhost in DEBUG must reject."""
    monkeypatch.setattr(settings, "DEBUG", True)
    _mock_dns(monkeypatch, "127.0.0.1")
    with pytest.raises(ValueError, match="private/internal IP"):
        validate_outbound_url("http://localhost:8000/api/internal/tick")


def test_debug_rejects_cloud_metadata(monkeypatch):
    monkeypatch.setattr(settings, "DEBUG", True)
    _mock_dns(monkeypatch, "169.254.169.254")
    with pytest.raises(ValueError, match="private/internal IP"):
        validate_outbound_url("http://169.254.169.254/latest/meta-data")


def test_debug_rejects_rfc1918(monkeypatch):
    monkeypatch.setattr(settings, "DEBUG", True)
    _mock_dns(monkeypatch, "10.0.0.5")
    with pytest.raises(ValueError, match="private/internal IP"):
        validate_outbound_url("http://internal.dev/hook")


# --- DEBUG mode: public host + http is allowed, no pinning ------------------


def test_debug_allows_public_http_without_pinning(monkeypatch):
    monkeypatch.setattr(settings, "DEBUG", True)
    _mock_dns(monkeypatch, "93.184.216.34")
    result = validate_outbound_url("http://public.example.com/hook")
    assert isinstance(result, ResolvedTarget)
    assert result.pinned_ip is None
    assert result.pinned_port == 80


# --- Production mode --------------------------------------------------------


def test_prod_rejects_http(monkeypatch):
    monkeypatch.setattr(settings, "DEBUG", False)
    _mock_dns(monkeypatch, "93.184.216.34")
    with pytest.raises(ValueError, match="non-HTTPS"):
        validate_outbound_url("http://public.example.com/hook")


def test_prod_pins_public_https(monkeypatch):
    monkeypatch.setattr(settings, "DEBUG", False)
    _mock_dns(monkeypatch, "93.184.216.34")
    result = validate_outbound_url("https://public.example.com/hook")
    assert result.pinned_ip == "93.184.216.34"
    assert result.pinned_port == 443
