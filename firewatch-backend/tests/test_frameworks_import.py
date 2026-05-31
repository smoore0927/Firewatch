"""Tests for the control framework importer + admin import endpoints."""

import io
import json
import socket

import httpx
import pytest

from app.api import frameworks
from app.models.control import Control, ControlFramework
from app.services.control_import import (
    MAX_OSCAL_GROUP_DEPTH,
    detect_and_parse,
    parse_oscal_json,
)
from app.services.control_import import import_framework
from app.services.control_seed import seed_control_frameworks


def _nested_oscal(depth: int) -> str:
    """Build OSCAL JSON whose catalog.groups nest `depth` levels deep."""
    inner = {"title": "Leaf", "controls": []}
    for _ in range(depth):
        inner = {"title": "G", "groups": [inner]}
    return json.dumps({"catalog": {"metadata": {"title": "Deep FW"}, "groups": [inner]}})


@pytest.fixture
def _public_dns(monkeypatch):
    """Resolve every hostname to a public IP so the import-from-url SSRF guard
    (which now resolves DNS in all modes) stays hermetic."""
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **kw: [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 0))],
    )


# --- Seed / upsert (service level) ----------------------------------------------

def test_seed_populates_from_vendored_files(db):
    seed_control_frameworks(db)
    names = {f.name for f in db.query(ControlFramework).all()}
    assert "NIST 800-53 Rev 5" in names
    assert "NIST CSF 2.0" in names
    assert db.query(Control).count() > 100


def test_seed_is_idempotent(db):
    seed_control_frameworks(db)
    count1 = db.query(Control).count()
    fw_count1 = db.query(ControlFramework).count()
    seed_control_frameworks(db)
    assert db.query(Control).count() == count1
    assert db.query(ControlFramework).count() == fw_count1


def test_seed_does_not_touch_risk_controls(db):
    # Re-running seed must not delete/recreate controls (which would orphan mappings).
    seed_control_frameworks(db)
    ac2 = db.query(Control).filter(Control.control_id == "AC-2").first()
    original_id = ac2.id
    seed_control_frameworks(db)
    ac2_again = db.query(Control).filter(Control.control_id == "AC-2").first()
    assert ac2_again.id == original_id


def test_import_upsert_counts(db):
    csv1 = "control_id,family,title,description\nX-1,Fam,One,d1\nX-2,Fam,Two,d2\n"
    r = import_framework(db, detect_and_parse(csv1), framework_name="FW")
    db.commit()
    assert r == {"framework_name": "FW", "version": None, "created": 2, "updated": 0}

    csv2 = "control_id,family,title,description\nX-1,Fam,One CHANGED,d1\nX-3,Fam,Three,d3\n"
    r = import_framework(db, detect_and_parse(csv2), framework_name="FW")
    db.commit()
    assert r["created"] == 1
    assert r["updated"] == 1
    assert db.query(Control).count() == 3


def test_oscal_json_parsing():
    oscal = """{"catalog":{"metadata":{"title":"OSCAL FW","version":"5.1"},
      "groups":[{"title":"Access Control","controls":[
        {"id":"ac-1","title":"Policy","props":[{"name":"label","value":"AC-1"}],
         "parts":[{"name":"statement","prose":"Do policy."}],
         "controls":[{"id":"ac-1.1","title":"Enh","props":[{"name":"label","value":"AC-1(1)"}]}]}]}]}}"""
    parsed = detect_and_parse(oscal)
    assert parsed.framework_name == "OSCAL FW"
    assert parsed.version == "5.1"
    ids = {c.control_id for c in parsed.controls}
    assert ids == {"AC-1", "AC-1(1)"}
    ac1 = next(c for c in parsed.controls if c.control_id == "AC-1")
    assert ac1.family == "Access Control"
    assert ac1.description == "Do policy."


# --- OSCAL nesting depth cap ----------------------------------------------------

def test_oscal_depth_cap_raises_value_error():
    deep = _nested_oscal(MAX_OSCAL_GROUP_DEPTH + 5)
    with pytest.raises(ValueError, match="too deep"):
        parse_oscal_json(deep)


def test_oscal_reasonable_nesting_parses_fine():
    # A few levels within the cap must parse without error (guard off-by-one).
    ok = _nested_oscal(3)
    parsed = detect_and_parse(ok)
    assert parsed.framework_name == "Deep FW"


def test_oscal_depth_at_cap_boundary_parses():
    # Exactly at the cap is still accepted (the leaf walk hits depth == cap).
    parsed = parse_oscal_json(_nested_oscal(MAX_OSCAL_GROUP_DEPTH))
    assert parsed.framework_name == "Deep FW"


# --- Endpoints ------------------------------------------------------------------

def _csv_bytes() -> bytes:
    return b"control_id,family,title,description\nT-1,TestFam,Test Control,A test\n"


def test_import_upload_requires_admin(client, analyst_user, login_as):
    login_as(analyst_user)
    resp = client.post(
        "/api/frameworks/import?framework_name=Custom",
        files={"file": ("c.csv", io.BytesIO(_csv_bytes()), "text/csv")},
    )
    assert resp.status_code == 403


def test_import_upload_succeeds(client, admin_user, login_as, db):
    login_as(admin_user)
    resp = client.post(
        "/api/frameworks/import?framework_name=Custom%20FW&version=v1",
        files={"file": ("c.csv", io.BytesIO(_csv_bytes()), "text/csv")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body == {"framework_name": "Custom FW", "version": "v1", "created": 1, "updated": 0}
    fw = db.query(ControlFramework).filter(ControlFramework.name == "Custom FW").first()
    assert fw is not None


def test_import_upload_deep_oscal_is_400(client, admin_user, login_as):
    login_as(admin_user)
    deep = _nested_oscal(MAX_OSCAL_GROUP_DEPTH + 5).encode()
    resp = client.post(
        "/api/frameworks/import?framework_name=Deep",
        files={"file": ("c.json", io.BytesIO(deep), "application/json")},
    )
    assert resp.status_code == 400
    assert "too deep" in resp.json()["detail"]


def test_import_upload_missing_name_is_400(client, admin_user, login_as):
    login_as(admin_user)
    # CSV carries no framework name and none provided -> ValueError -> 400.
    resp = client.post(
        "/api/frameworks/import",
        files={"file": ("c.csv", io.BytesIO(_csv_bytes()), "text/csv")},
    )
    assert resp.status_code == 400


def test_import_upload_over_cap_is_413(client, admin_user, login_as, monkeypatch):
    # Shrink the cap so a tiny payload trips the chunked-read 413 without 25 MB.
    monkeypatch.setattr(frameworks, "MAX_IMPORT_BYTES", 1024)
    login_as(admin_user)
    resp = client.post(
        "/api/frameworks/import?framework_name=Custom",
        files={"file": ("c.csv", io.BytesIO(b"x" * 2048), "text/csv")},
    )
    assert resp.status_code == 413
    assert "exceeds" in resp.json()["detail"]


def test_import_from_url_succeeds(client, admin_user, login_as, db, monkeypatch, _public_dns):
    payload = _csv_bytes()

    class _Resp:
        status_code = 200
        content = payload
        def raise_for_status(self): pass

    class _Client:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url, **kwargs): return _Resp()

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    login_as(admin_user)
    resp = client.post(
        "/api/frameworks/import-from-url",
        json={"url": "https://example.com/catalog.csv", "framework_name": "URL FW"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["created"] == 1
    fw = db.query(ControlFramework).filter(ControlFramework.name == "URL FW").first()
    assert fw.source_url == "https://example.com/catalog.csv"
    assert fw.last_imported_at is not None


def test_import_from_url_fetch_failure_is_502(client, admin_user, login_as, monkeypatch, _public_dns):
    class _Client:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url, **kwargs): raise httpx.ConnectError("boom")

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    login_as(admin_user)
    resp = client.post(
        "/api/frameworks/import-from-url",
        json={"url": "https://bad.example.com/x.csv", "framework_name": "X"},
    )
    assert resp.status_code == 502


# --- import-from-url SSRF / hardening -------------------------------------------


from app.core.config import settings  # noqa: E402


def _addrinfo(addr: str, family: int = socket.AF_INET):
    sockaddr = (addr, 0) if family == socket.AF_INET else (addr, 0, 0, 0)
    return [(family, socket.SOCK_STREAM, 0, "", sockaddr)]


class _RecordedGet:
    def __init__(self, url, headers, extensions):
        self.url = url
        self.headers = headers
        self.extensions = extensions


def _install_get_mock(monkeypatch, *, status_code=200, content=b"", recorded=None):
    """Patch httpx.AsyncClient.get to return a scripted response and record calls."""
    async def fake_get(self, url, *, headers=None, extensions=None, **kwargs):
        if recorded is not None:
            recorded.append(
                _RecordedGet(url, dict(headers or {}), dict(extensions or {}))
            )
        return httpx.Response(
            status_code=status_code,
            content=content,
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)


@pytest.mark.parametrize("addr", ["127.0.0.1", "169.254.169.254", "10.0.0.5"])
def test_import_from_url_rejects_internal_ip_without_fetching(
    client, admin_user, login_as, monkeypatch, addr
):
    """Regression for the scanner suite hang: an internal-resolving host is
    rejected 422 BEFORE any httpx GET (fail fast, no 10s/30s network timeout)."""
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: _addrinfo(addr))

    async def boom_get(self, *a, **kw):
        raise AssertionError("httpx GET must not be called for an internal target")

    monkeypatch.setattr(httpx.AsyncClient, "get", boom_get)

    login_as(admin_user)
    resp = client.post(
        "/api/frameworks/import-from-url",
        json={"url": "https://attacker.example.com/catalog.csv", "framework_name": "X"},
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert "private/internal IP" in detail
    assert addr in detail


def test_import_from_url_pins_ip_and_sets_host_and_sni_in_prod(
    client, admin_user, login_as, db, monkeypatch
):
    """In production mode the GET is issued to the pinned IP literal with the
    original hostname as Host header + SNI extension."""
    login_as(admin_user)
    # Flip DEBUG off only AFTER login (login needs Secure-cookie-friendly mode).
    monkeypatch.setattr(settings, "DEBUG", False)
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: _addrinfo("93.184.216.34"))

    recorded: list[_RecordedGet] = []
    _install_get_mock(monkeypatch, status_code=200, content=_csv_bytes(), recorded=recorded)

    resp = client.post(
        "/api/frameworks/import-from-url",
        json={"url": "https://legit.example.com/catalog.csv", "framework_name": "Pinned FW"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["created"] == 1

    assert len(recorded) == 1
    req = recorded[0]
    assert req.url == "https://93.184.216.34:443/catalog.csv"
    assert req.headers["Host"] == "legit.example.com"
    assert req.extensions.get("sni_hostname") == "legit.example.com"

    fw = db.query(ControlFramework).filter(ControlFramework.name == "Pinned FW").first()
    assert fw is not None
    assert fw.source_url == "https://legit.example.com/catalog.csv"


def test_import_from_url_rejects_redirect_with_502(
    client, admin_user, login_as, monkeypatch, _public_dns
):
    """With follow_redirects disabled, a 3xx is a failed fetch (502), not an
    empty silent success."""
    _install_get_mock(monkeypatch, status_code=302, content=b"")

    login_as(admin_user)
    resp = client.post(
        "/api/frameworks/import-from-url",
        json={"url": "https://example.com/catalog.csv", "framework_name": "X"},
    )
    assert resp.status_code == 502
    assert "redirects are not followed" in resp.json()["detail"]


def test_import_from_url_requires_admin(client, analyst_user, login_as):
    login_as(analyst_user)
    resp = client.post(
        "/api/frameworks/import-from-url",
        json={"url": "https://example.com/catalog.csv", "framework_name": "X"},
    )
    assert resp.status_code == 403
