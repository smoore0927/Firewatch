"""Tests for admin delete-framework with block-when-mapped + seed tombstones."""

from app.models.control import (
    Control,
    ControlFramework,
    DeletedFrameworkSeed,
    RiskControl,
)
from app.models.risk import Risk, RiskStatus
from app.services.control_import import detect_and_parse, import_framework
from app.services.control_seed import seed_control_frameworks


def _make_framework(db, name="Custom FW") -> ControlFramework:
    fw = ControlFramework(name=name, version="v1")
    db.add(fw)
    db.flush()
    db.add(Control(framework_id=fw.id, control_id="C-1", title="Control One"))
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


def test_delete_framework_no_mappings(client, admin_user, login_as, db):
    fw = _make_framework(db)
    fw_id = fw.id
    login_as(admin_user)
    resp = client.delete(f"/api/frameworks/{fw_id}")
    assert resp.status_code == 204, resp.text
    assert db.query(ControlFramework).filter(ControlFramework.id == fw_id).first() is None
    assert db.query(Control).filter(Control.framework_id == fw_id).count() == 0
    tomb = db.query(DeletedFrameworkSeed).filter(DeletedFrameworkSeed.name == "Custom FW").first()
    assert tomb is not None
    assert tomb.deleted_by_id == admin_user.id


def test_delete_framework_blocked_when_mapped(client, admin_user, owner_user, login_as, db):
    fw = _make_framework(db)
    fw_id = fw.id
    control = db.query(Control).filter(Control.framework_id == fw_id).first()
    risk = _make_risk(db, owner_user)
    db.add(RiskControl(risk_id=risk.id, control_id=control.id, created_by_id=owner_user.id))
    db.commit()

    login_as(admin_user)
    resp = client.delete(f"/api/frameworks/{fw_id}")
    assert resp.status_code == 409, resp.text
    assert "1 control mapping(s) across 1 risk(s)" in resp.json()["detail"]
    assert db.query(ControlFramework).filter(ControlFramework.id == fw_id).first() is not None
    assert db.query(DeletedFrameworkSeed).count() == 0


def test_delete_framework_requires_admin(client, analyst_user, login_as, db):
    fw = _make_framework(db)
    login_as(analyst_user)
    resp = client.delete(f"/api/frameworks/{fw.id}")
    assert resp.status_code == 403


def test_delete_framework_unauthenticated(client, db):
    fw = _make_framework(db)
    resp = client.delete(f"/api/frameworks/{fw.id}")
    assert resp.status_code == 401


def test_delete_missing_framework_404(client, admin_user, login_as):
    login_as(admin_user)
    resp = client.delete("/api/frameworks/99999")
    assert resp.status_code == 404


def test_seed_skips_tombstoned_framework(db):
    db.add(DeletedFrameworkSeed(name="NIST CSF 2.0"))
    db.commit()
    seed_control_frameworks(db)
    names = {f.name for f in db.query(ControlFramework).all()}
    assert "NIST CSF 2.0" not in names
    assert "NIST 800-53 Rev 5" in names


def test_import_clears_tombstone(db):
    db.add(DeletedFrameworkSeed(name="FW"))
    db.commit()
    csv = "control_id,family,title,description\nX-1,Fam,One,d1\n"
    import_framework(db, detect_and_parse(csv), framework_name="FW")
    db.commit()
    assert db.query(DeletedFrameworkSeed).filter(DeletedFrameworkSeed.name == "FW").first() is None
    assert db.query(ControlFramework).filter(ControlFramework.name == "FW").first() is not None
