"""Tests for admin framework metadata edit + control-source reimport (block-when-mapped)."""

import io
import socket

import httpx
import pytest

from app.api import frameworks
from app.models.control import Control, ControlFramework, RiskControl
from app.models.risk import Risk, RiskStatus


@pytest.fixture
def _public_dns(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **kw: [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 0))],
    )


def _make_framework(db, name="Custom FW") -> ControlFramework:
    fw = ControlFramework(name=name, version="v1", description="orig desc")
    db.add(fw)
    db.flush()
    db.add(Control(framework_id=fw.id, control_id="C-1", title="Control One"))
    db.add(Control(framework_id=fw.id, control_id="C-2", title="Control Two"))
    db.commit()
    db.refresh(fw)
    return fw


def _make_risk(db, owner) -> Risk:
    risk = Risk(
        risk_id="RISK-0001",
        title="Test risk",
        status=RiskStatus.open,
        owner_id=owner.id,
        created_by_id=owner.id,
    )
    db.add(risk)
    db.commit()
    db.refresh(risk)
    return risk


def _new_csv_bytes() -> bytes:
    return b"control_id,family,title,description\nN-1,Fam,New One,a\nN-2,Fam,New Two,b\n"


# --- PATCH metadata edit --------------------------------------------------------

def test_patch_updates_metadata_leaves_controls(client, admin_user, login_as, db):
    fw = _make_framework(db)
    fw_id = fw.id
    login_as(admin_user)
    resp = client.patch(
        f"/api/frameworks/{fw_id}",
        json={"name": "Renamed FW", "version": "v2", "description": "new desc"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == "Renamed FW"
    assert body["version"] == "v2"
    assert body["description"] == "new desc"
    # Controls untouched.
    assert db.query(Control).filter(Control.framework_id == fw_id).count() == 2


def test_patch_partial_only_changes_provided_fields(client, admin_user, login_as, db):
    fw = _make_framework(db)
    fw_id = fw.id
    login_as(admin_user)
    resp = client.patch(f"/api/frameworks/{fw_id}", json={"version": "v9"})
    assert resp.status_code == 200, resp.text
    db.expire_all()
    refreshed = db.query(ControlFramework).filter(ControlFramework.id == fw_id).first()
    assert refreshed.version == "v9"
    assert refreshed.name == "Custom FW"
    assert refreshed.description == "orig desc"


def test_patch_missing_framework_404(client, admin_user, login_as):
    login_as(admin_user)
    resp = client.patch("/api/frameworks/99999", json={"name": "X"})
    assert resp.status_code == 404


def test_patch_rename_collision_409(client, admin_user, login_as, db):
    _make_framework(db, name="FW A")
    fw_b = _make_framework(db, name="FW B")
    login_as(admin_user)
    resp = client.patch(f"/api/frameworks/{fw_b.id}", json={"name": "FW A"})
    assert resp.status_code == 409, resp.text
    assert "already exists" in resp.json()["detail"]


def test_patch_requires_admin(client, analyst_user, login_as, db):
    fw = _make_framework(db)
    login_as(analyst_user)
    resp = client.patch(f"/api/frameworks/{fw.id}", json={"name": "X"})
    assert resp.status_code == 403


# --- reimport (file) ------------------------------------------------------------

def test_reimport_file_replaces_controls(client, admin_user, login_as, db):
    fw = _make_framework(db)
    fw_id = fw.id
    login_as(admin_user)
    resp = client.post(
        f"/api/frameworks/{fw_id}/reimport?version=v2",
        files={"file": ("c.csv", io.BytesIO(_new_csv_bytes()), "text/csv")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body == {"framework_name": "Custom FW", "version": "v2", "created": 2, "updated": 0}
    ids = {c.control_id for c in db.query(Control).filter(Control.framework_id == fw_id).all()}
    assert ids == {"N-1", "N-2"}  # old C-1/C-2 wiped, new ones present
    db.expire_all()
    refreshed = db.query(ControlFramework).filter(ControlFramework.id == fw_id).first()
    assert refreshed.version == "v2"
    assert refreshed.last_imported_at is not None


def test_reimport_file_blocked_when_mapped(client, admin_user, owner_user, login_as, db):
    fw = _make_framework(db)
    fw_id = fw.id
    control = db.query(Control).filter(Control.framework_id == fw_id, Control.control_id == "C-1").first()
    risk = _make_risk(db, owner_user)
    db.add(RiskControl(risk_id=risk.id, control_id=control.id, created_by_id=owner_user.id))
    db.commit()

    login_as(admin_user)
    resp = client.post(
        f"/api/frameworks/{fw_id}/reimport",
        files={"file": ("c.csv", io.BytesIO(_new_csv_bytes()), "text/csv")},
    )
    assert resp.status_code == 409, resp.text
    assert "Remove those mappings" in resp.json()["detail"]
    # Nothing changed: original controls intact.
    ids = {c.control_id for c in db.query(Control).filter(Control.framework_id == fw_id).all()}
    assert ids == {"C-1", "C-2"}


def test_reimport_file_over_cap_is_413(client, admin_user, login_as, db, monkeypatch):
    fw = _make_framework(db)
    monkeypatch.setattr(frameworks, "MAX_IMPORT_BYTES", 1024)
    login_as(admin_user)
    resp = client.post(
        f"/api/frameworks/{fw.id}/reimport",
        files={"file": ("c.csv", io.BytesIO(b"x" * 2048), "text/csv")},
    )
    assert resp.status_code == 413
    assert "exceeds" in resp.json()["detail"]


def test_reimport_missing_framework_404(client, admin_user, login_as):
    login_as(admin_user)
    resp = client.post(
        "/api/frameworks/99999/reimport",
        files={"file": ("c.csv", io.BytesIO(_new_csv_bytes()), "text/csv")},
    )
    assert resp.status_code == 404


def test_reimport_requires_admin(client, analyst_user, login_as, db):
    fw = _make_framework(db)
    login_as(analyst_user)
    resp = client.post(
        f"/api/frameworks/{fw.id}/reimport",
        files={"file": ("c.csv", io.BytesIO(_new_csv_bytes()), "text/csv")},
    )
    assert resp.status_code == 403


# --- reimport-from-url ----------------------------------------------------------

def test_reimport_from_url_replaces_controls(client, admin_user, login_as, db, monkeypatch, _public_dns):
    fw = _make_framework(db)
    fw_id = fw.id
    payload = _new_csv_bytes()

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
        f"/api/frameworks/{fw_id}/reimport-from-url",
        json={"url": "https://example.com/catalog.csv", "version": "v3"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["created"] == 2
    ids = {c.control_id for c in db.query(Control).filter(Control.framework_id == fw_id).all()}
    assert ids == {"N-1", "N-2"}
    db.expire_all()
    refreshed = db.query(ControlFramework).filter(ControlFramework.id == fw_id).first()
    assert refreshed.source_url == "https://example.com/catalog.csv"


def test_reimport_from_url_rejects_internal_ip_without_fetching(
    client, admin_user, login_as, db, monkeypatch
):
    fw = _make_framework(db)
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **kw: [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("127.0.0.1", 0))],
    )

    async def boom_get(self, *a, **kw):
        raise AssertionError("httpx GET must not be called for an internal target")

    monkeypatch.setattr(httpx.AsyncClient, "get", boom_get)

    login_as(admin_user)
    resp = client.post(
        f"/api/frameworks/{fw.id}/reimport-from-url",
        json={"url": "https://attacker.example.com/catalog.csv"},
    )
    assert resp.status_code == 422
    assert "private/internal IP" in resp.json()["detail"]
