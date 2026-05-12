"""Integration tests for /api/reports/risk-summary."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone

from app.models.audit_log import AuditLog
from app.models.risk import Risk, RiskAssessment, RiskStatus
from app.models.user import User


_seed_counter = {"n": 0}


def _seed_risk(
    db,
    *,
    owner: User,
    title: str,
    score: int | None,
    deleted: bool = False,
) -> Risk:
    """Insert a Risk and (optionally) one assessment with an exact score."""
    _seed_counter["n"] += 1
    risk = Risk(
        risk_id=f"RISK-{_seed_counter['n']:04d}",
        title=title,
        owner_id=owner.id,
        created_by_id=owner.id,
        status=RiskStatus.open,
    )
    if deleted:
        risk.deleted_at = datetime.now(timezone.utc)
    db.add(risk)
    db.flush()

    if score is not None:
        # Pick a (likelihood, impact) pair whose product equals `score` so the
        # severity classifier sees the exact score. For scores not expressible
        # as a 1-5 product (e.g. 24) we still set risk_score directly — only
        # risk_score is used by the severity classifier in the report row.
        likelihood = 1
        impact = score if score <= 5 else 5
        db.add(RiskAssessment(
            risk_id=risk.id,
            likelihood=likelihood,
            impact=impact,
            risk_score=score,
            assessed_by_id=owner.id,
        ))
    db.commit()
    db.refresh(risk)
    return risk


# --- Auth ---------------------------------------------------------------------


def test_risk_summary_unauthenticated_returns_401(client):
    resp = client.get(
        "/api/reports/risk-summary",
        params={"start": "2026-01-01", "end": "2026-12-31"},
    )
    assert resp.status_code == 401


# --- include_risks=False (default) -------------------------------------------


def test_risk_summary_omits_risks_by_default(client, admin_user, login_as):
    login_as(admin_user)
    resp = client.get(
        "/api/reports/risk-summary",
        params={"start": "2026-01-01", "end": "2026-12-31"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert "summary" in body
    assert "score_history" in body
    assert body["risks"] is None
    assert body["date_range"] == {"start": "2026-01-01", "end": "2026-12-31"}
    assert body["generated_by"]["email"] == admin_user.email
    assert body["generated_by"]["role"] == admin_user.role.value
    # Summary shape sanity-check
    assert set(body["summary"]["by_severity"]) == {
        "Critical", "High", "Medium", "Low", "Unscored"
    }


def test_risk_summary_explicit_include_false(client, admin_user, login_as):
    login_as(admin_user)
    resp = client.get(
        "/api/reports/risk-summary",
        params={
            "start": "2026-01-01",
            "end": "2026-12-31",
            "include_risks": "false",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["risks"] is None


# --- include_risks=True -------------------------------------------------------


def test_risk_summary_includes_risks_when_requested(
    client, admin_user, login_as, db
):
    login_as(admin_user)
    _seed_risk(db, owner=admin_user, title="Active1", score=9)
    _seed_risk(db, owner=admin_user, title="Active2", score=16)
    _seed_risk(db, owner=admin_user, title="Soft", score=20, deleted=True)

    resp = client.get(
        "/api/reports/risk-summary",
        params={
            "start": "2026-01-01",
            "end": "2026-12-31",
            "include_risks": "true",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["risks"] is not None
    titles = {r["title"] for r in body["risks"]}
    assert titles == {"Active1", "Active2"}
    # Soft-deleted risk is excluded
    assert "Soft" not in titles


# --- Severity classification --------------------------------------------------


def test_risk_summary_severity_classification(
    client, admin_user, login_as, db
):
    login_as(admin_user)
    # Score 0 → seeded with no assessment so it's Unscored
    _seed_risk(db, owner=admin_user, title="None", score=None)
    _seed_risk(db, owner=admin_user, title="Three", score=3)
    _seed_risk(db, owner=admin_user, title="Nine", score=9)
    _seed_risk(db, owner=admin_user, title="Sixt", score=16)
    _seed_risk(db, owner=admin_user, title="TwoFr", score=24)

    resp = client.get(
        "/api/reports/risk-summary",
        params={
            "start": "2026-01-01",
            "end": "2026-12-31",
            "include_risks": "true",
        },
    )
    assert resp.status_code == 200
    rows = {r["title"]: r for r in resp.json()["risks"]}

    assert rows["None"]["severity"] == "Unscored"
    assert rows["None"]["current_score"] is None
    assert rows["None"]["current_likelihood"] is None
    assert rows["None"]["current_impact"] is None

    assert rows["Three"]["severity"] == "Low"
    assert rows["Three"]["current_score"] == 3

    assert rows["Nine"]["severity"] == "Medium"
    assert rows["Nine"]["current_score"] == 9

    assert rows["Sixt"]["severity"] == "High"
    assert rows["Sixt"]["current_score"] == 16

    assert rows["TwoFr"]["severity"] == "Critical"
    assert rows["TwoFr"]["current_score"] == 24


# --- Role-based scoping of the risks list ------------------------------------


def test_risk_owner_only_sees_own_risks_in_report(
    client, owner_user, owner_user_b, login_as, db
):
    _seed_risk(db, owner=owner_user, title="OwnedByA", score=9)
    _seed_risk(db, owner=owner_user_b, title="OwnedByB", score=9)

    login_as(owner_user)
    resp = client.get(
        "/api/reports/risk-summary",
        params={
            "start": "2026-01-01",
            "end": "2026-12-31",
            "include_risks": "true",
        },
    )
    assert resp.status_code == 200
    titles = {r["title"] for r in resp.json()["risks"]}
    assert "OwnedByA" in titles
    assert "OwnedByB" not in titles


def test_admin_sees_all_risks_in_report(
    client, admin_user, owner_user, owner_user_b, login_as, db
):
    _seed_risk(db, owner=owner_user, title="OwnedByA", score=9)
    _seed_risk(db, owner=owner_user_b, title="OwnedByB", score=9)

    login_as(admin_user)
    resp = client.get(
        "/api/reports/risk-summary",
        params={
            "start": "2026-01-01",
            "end": "2026-12-31",
            "include_risks": "true",
        },
    )
    assert resp.status_code == 200
    titles = {r["title"] for r in resp.json()["risks"]}
    assert {"OwnedByA", "OwnedByB"}.issubset(titles)


def test_security_analyst_sees_all_risks_in_report(
    client, analyst_user, owner_user, owner_user_b, login_as, db
):
    _seed_risk(db, owner=owner_user, title="OwnedByA", score=9)
    _seed_risk(db, owner=owner_user_b, title="OwnedByB", score=9)

    login_as(analyst_user)
    resp = client.get(
        "/api/reports/risk-summary",
        params={
            "start": "2026-01-01",
            "end": "2026-12-31",
            "include_risks": "true",
        },
    )
    assert resp.status_code == 200
    titles = {r["title"] for r in resp.json()["risks"]}
    assert {"OwnedByA", "OwnedByB"}.issubset(titles)


def test_executive_viewer_sees_all_risks_in_report(
    client, viewer_user, owner_user, owner_user_b, login_as, db
):
    _seed_risk(db, owner=owner_user, title="OwnedByA", score=9)
    _seed_risk(db, owner=owner_user_b, title="OwnedByB", score=9)

    login_as(viewer_user)
    resp = client.get(
        "/api/reports/risk-summary",
        params={
            "start": "2026-01-01",
            "end": "2026-12-31",
            "include_risks": "true",
        },
    )
    assert resp.status_code == 200
    titles = {r["title"] for r in resp.json()["risks"]}
    assert {"OwnedByA", "OwnedByB"}.issubset(titles)


# --- Audit logging ------------------------------------------------------------


def test_risk_summary_writes_audit_row(client, admin_user, login_as, db):
    login_as(admin_user)
    resp = client.get(
        "/api/reports/risk-summary",
        params={
            "start": "2026-01-01",
            "end": "2026-12-31",
            "include_risks": "true",
        },
    )
    assert resp.status_code == 200

    row = (
        db.query(AuditLog)
        .filter(AuditLog.action == "report_exported")
        .order_by(AuditLog.id.desc())
        .first()
    )
    assert row is not None
    assert row.user_id == admin_user.id
    assert row.resource_type == "report"
    assert row.resource_id is None
    meta = json.loads(row.details)
    assert meta == {
        "start": "2026-01-01",
        "end": "2026-12-31",
        "include_risks": True,
    }


def test_risk_summary_audit_row_records_include_risks_false(
    client, admin_user, login_as, db
):
    login_as(admin_user)
    resp = client.get(
        "/api/reports/risk-summary",
        params={"start": "2026-01-01", "end": "2026-12-31"},
    )
    assert resp.status_code == 200

    row = (
        db.query(AuditLog)
        .filter(AuditLog.action == "report_exported")
        .order_by(AuditLog.id.desc())
        .first()
    )
    assert row is not None
    assert row.user_id == admin_user.id
    assert row.resource_type == "report"
    assert row.resource_id is None
    meta = json.loads(row.details)
    assert meta == {
        "start": "2026-01-01",
        "end": "2026-12-31",
        "include_risks": False,
    }
