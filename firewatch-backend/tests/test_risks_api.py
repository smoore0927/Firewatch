"""Integration tests for /api/risks routes."""

from __future__ import annotations

from datetime import date, timedelta

from app.models.risk import Risk, RiskAssessment, RiskStatus
from app.models.user import User, UserRole


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_risk_payload(**overrides) -> dict:
    base = {
        "title": "Phishing risk",
        "description": "Targeted phishing of finance team.",
        "threat_source": "External adversary",
        "threat_event": "Phishing email",
        "vulnerability": "No MFA on admin accounts",
        "affected_asset": "Customer PII database",
        "category": "Technical",
        "likelihood": 3,
        "impact": 4,
    }
    base.update(overrides)
    return base


def _create_risk(client, **overrides) -> dict:
    resp = client.post("/api/risks", json=_make_risk_payload(**overrides))
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# POST /api/risks (create)
# ---------------------------------------------------------------------------


def test_create_risk_as_admin_succeeds(client, admin_user, login_as):
    login_as(admin_user)
    resp = client.post("/api/risks", json=_make_risk_payload())
    assert resp.status_code == 201
    body = resp.json()
    assert body["title"] == "Phishing risk"
    assert body["status"] == "open"
    assert body["risk_id"].startswith("RISK-")
    assert body["owner_id"] == admin_user.id
    assert len(body["assessments"]) == 1
    assert body["assessments"][0]["risk_score"] == 12


def test_create_risk_assigns_risk_id_sequentially(client, admin_user, login_as):
    login_as(admin_user)
    a = _create_risk(client, title="A")
    b = _create_risk(client, title="B")
    assert a["risk_id"] == "RISK-001"
    assert b["risk_id"] == "RISK-002"


def test_create_risk_without_likelihood_or_impact(client, admin_user, login_as):
    login_as(admin_user)
    resp = client.post(
        "/api/risks",
        json={"title": "No score yet", "description": "TBD"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["assessments"] == []


def test_create_risk_as_owner_succeeds(client, owner_user, login_as):
    login_as(owner_user)
    resp = client.post("/api/risks", json=_make_risk_payload())
    assert resp.status_code == 201
    assert resp.json()["owner_id"] == owner_user.id


def test_create_risk_as_viewer_returns_403(client, viewer_user, login_as):
    login_as(viewer_user)
    resp = client.post("/api/risks", json=_make_risk_payload())
    assert resp.status_code == 403


def test_create_risk_unauthenticated_returns_401(client):
    resp = client.post("/api/risks", json=_make_risk_payload())
    assert resp.status_code == 401


def test_create_risk_validation_error_returns_422(client, admin_user, login_as):
    login_as(admin_user)
    resp = client.post(
        "/api/risks",
        json={"title": "Bad scores", "likelihood": 9, "impact": 9},
    )
    assert resp.status_code == 422


def test_create_risk_missing_title_returns_422(client, admin_user, login_as):
    login_as(admin_user)
    resp = client.post("/api/risks", json={"description": "no title"})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/risks (list, filter)
# ---------------------------------------------------------------------------


def test_list_risks_empty(client, admin_user, login_as):
    login_as(admin_user)
    resp = client.get("/api/risks")
    assert resp.status_code == 200
    assert resp.json() == {"total": 0, "items": []}


def test_list_risks_returns_created(client, admin_user, login_as):
    login_as(admin_user)
    _create_risk(client, title="A")
    _create_risk(client, title="B")
    resp = client.get("/api/risks")
    body = resp.json()
    assert body["total"] == 2
    titles = {item["title"] for item in body["items"]}
    assert titles == {"A", "B"}


def test_list_risks_filters_by_status(client, admin_user, login_as, db):
    login_as(admin_user)
    a = _create_risk(client, title="A")
    _create_risk(client, title="B")
    risk = db.query(Risk).filter(Risk.risk_id == a["risk_id"]).first()
    risk.status = RiskStatus.in_progress
    db.commit()

    resp = client.get("/api/risks?status=in_progress")
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "A"


def test_list_risks_filters_by_category(client, admin_user, login_as):
    login_as(admin_user)
    _create_risk(client, title="Tech", category="Technical")
    _create_risk(client, title="Compl", category="Compliance")
    resp = client.get("/api/risks?category=Technical")
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "Tech"


def test_list_risks_filters_by_owner_id(client, admin_user, owner_user, login_as):
    login_as(admin_user)
    _create_risk(client, title="Mine", owner_id=admin_user.id)
    _create_risk(client, title="Theirs", owner_id=owner_user.id)
    resp = client.get(f"/api/risks?owner_id={owner_user.id}")
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "Theirs"


def test_list_risks_filters_due_for_review(client, admin_user, login_as, db):
    login_as(admin_user)
    overdue = _create_risk(
        client,
        title="Overdue",
        review_frequency_days=30,
        next_review_date=(date.today() - timedelta(days=1)).isoformat(),
    )
    _create_risk(
        client,
        title="Future",
        review_frequency_days=30,
        next_review_date=(date.today() + timedelta(days=30)).isoformat(),
    )
    resp = client.get("/api/risks?due_for_review=true")
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["risk_id"] == overdue["risk_id"]


def test_list_risks_pagination(client, admin_user, login_as):
    login_as(admin_user)
    for i in range(5):
        _create_risk(client, title=f"R{i}")
    resp = client.get("/api/risks?skip=2&limit=2")
    body = resp.json()
    assert body["total"] == 5
    assert len(body["items"]) == 2


def test_list_risks_pages_same_second_risks_in_a_stable_order(
    client, admin_user, login_as
):
    # A CSV import creates many risks inside one second (SQLite timestamps have
    # 1-second resolution), so created_at alone can't order pages: ties must
    # fall back to id, newest first, or paging repeats some risks and skips others.
    login_as(admin_user)
    same_second = "2026-01-15T10:00:00+00:00"
    created = [
        _create_risk(client, title=f"R{i}", created_at=same_second)["risk_id"]
        for i in range(5)
    ]

    paged: list[str] = []
    for skip in range(0, 5, 2):
        body = client.get(f"/api/risks?skip={skip}&limit=2").json()
        paged.extend(item["risk_id"] for item in body["items"])

    assert paged == list(reversed(created))


def test_list_risks_owner_role_only_sees_their_own(
    client, admin_user, owner_user, login_as
):
    login_as(admin_user)
    _create_risk(client, title="Admins", owner_id=admin_user.id)
    _create_risk(client, title="Owners", owner_id=owner_user.id)
    # logout admin, login owner
    client.post("/api/auth/logout")
    client.cookies.clear()
    login_as(owner_user)
    resp = client.get("/api/risks")
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "Owners"


def test_list_risks_unauthenticated_returns_401(client):
    resp = client.get("/api/risks")
    assert resp.status_code == 401


def test_list_risks_invalid_limit_returns_422(client, admin_user, login_as):
    login_as(admin_user)
    resp = client.get("/api/risks?limit=9999")
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/risks/{id}
# ---------------------------------------------------------------------------


def test_get_risk_returns_full_record(client, admin_user, login_as):
    login_as(admin_user)
    created = _create_risk(client)
    resp = client.get(f"/api/risks/{created['risk_id']}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["risk_id"] == created["risk_id"]
    assert body["title"] == "Phishing risk"


def test_get_risk_not_found_returns_404(client, admin_user, login_as):
    login_as(admin_user)
    resp = client.get("/api/risks/RISK-999")
    assert resp.status_code == 404


def test_get_risk_unauthenticated_returns_401(client):
    resp = client.get("/api/risks/RISK-001")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# PUT /api/risks/{id}
# ---------------------------------------------------------------------------


def test_update_risk_changes_fields_and_logs_history(client, admin_user, login_as):
    login_as(admin_user)
    created = _create_risk(client)
    resp = client.put(
        f"/api/risks/{created['risk_id']}",
        json={"title": "Updated title", "status": "in_progress"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == "Updated title"
    assert body["status"] == "in_progress"
    fields_changed = {h["field_changed"] for h in body["history"]}
    assert "title" in fields_changed
    assert "status" in fields_changed


def test_risk_current_score_and_severity_follow_latest_residual(
    client, admin_user, login_as
):
    login_as(admin_user)
    created = _create_risk(client, likelihood=4, impact=4)
    assert (created["current_score"], created["severity"]) == (16, "high")

    resp = client.post(
        f"/api/risks/{created['risk_id']}/assessments",
        json={"likelihood": 4, "impact": 4, "residual_likelihood": 2, "residual_impact": 2},
    )
    assert resp.status_code == 200, resp.text
    assert (resp.json()["current_score"], resp.json()["severity"]) == (4, "low")

    listed = client.get("/api/risks").json()["items"][0]
    assert (listed["current_score"], listed["severity"]) == (4, "low")


def test_unscored_risk_has_no_current_score_or_severity(client, admin_user, login_as):
    login_as(admin_user)
    created = _create_risk(client, likelihood=None, impact=None)
    assert created["current_score"] is None
    assert created["severity"] is None


def test_update_risk_with_score_creates_new_assessment(client, admin_user, login_as):
    login_as(admin_user)
    created = _create_risk(client, likelihood=2, impact=2)
    resp = client.put(
        f"/api/risks/{created['risk_id']}",
        json={"likelihood": 5, "impact": 5},
    )
    assert resp.status_code == 200
    assessments = resp.json()["assessments"]
    assert len(assessments) == 2
    # assessments are ordered desc by assessed_at, so [0] is latest
    assert assessments[0]["risk_score"] == 25


def test_update_risk_not_found_returns_404(client, admin_user, login_as):
    login_as(admin_user)
    resp = client.put("/api/risks/RISK-NOPE", json={"title": "x"})
    assert resp.status_code == 404


def test_update_risk_as_viewer_returns_403(
    client, admin_user, viewer_user, login_as
):
    login_as(admin_user)
    created = _create_risk(client)
    client.post("/api/auth/logout")
    client.cookies.clear()
    login_as(viewer_user)
    resp = client.put(
        f"/api/risks/{created['risk_id']}",
        json={"title": "viewer tried"},
    )
    assert resp.status_code == 403


def test_update_risk_as_other_owner_returns_403(
    client, admin_user, owner_user, login_as
):
    """A risk_owner cannot edit a risk they don't own."""
    login_as(admin_user)
    created = _create_risk(client, owner_id=admin_user.id)
    client.post("/api/auth/logout")
    client.cookies.clear()
    login_as(owner_user)
    resp = client.put(
        f"/api/risks/{created['risk_id']}", json={"title": "stealing"}
    )
    assert resp.status_code == 403


def test_update_risk_as_owner_of_their_risk_succeeds(
    client, admin_user, owner_user, login_as
):
    login_as(admin_user)
    created = _create_risk(client, owner_id=owner_user.id)
    client.post("/api/auth/logout")
    client.cookies.clear()
    login_as(owner_user)
    resp = client.put(
        f"/api/risks/{created['risk_id']}", json={"title": "Updated by owner"}
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# DELETE /api/risks/{id}  (admin only, soft delete)
# ---------------------------------------------------------------------------


def test_delete_risk_as_admin_soft_deletes(client, admin_user, login_as):
    login_as(admin_user)
    created = _create_risk(client)
    resp = client.delete(f"/api/risks/{created['risk_id']}")
    assert resp.status_code == 204
    # After delete, GET returns 404
    follow_up = client.get(f"/api/risks/{created['risk_id']}")
    assert follow_up.status_code == 404
    # And it no longer appears in the list
    listing = client.get("/api/risks")
    assert listing.json()["total"] == 0


def test_delete_risk_as_analyst_returns_403(
    client, admin_user, analyst_user, login_as
):
    login_as(admin_user)
    created = _create_risk(client)
    client.post("/api/auth/logout")
    client.cookies.clear()
    login_as(analyst_user)
    resp = client.delete(f"/api/risks/{created['risk_id']}")
    assert resp.status_code == 403


def test_delete_risk_unauthenticated_returns_401(client):
    resp = client.delete("/api/risks/RISK-001")
    assert resp.status_code == 401


def test_delete_risk_not_found_returns_404(client, admin_user, login_as):
    login_as(admin_user)
    resp = client.delete("/api/risks/RISK-NOPE")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/risks/{id}/assessments
# ---------------------------------------------------------------------------


def test_add_assessment_appends_row(client, admin_user, login_as):
    login_as(admin_user)
    created = _create_risk(client, likelihood=2, impact=2)
    resp = client.post(
        f"/api/risks/{created['risk_id']}/assessments",
        json={
            "likelihood": 4,
            "impact": 5,
            "residual_likelihood": 2,
            "residual_impact": 2,
            "notes": "After MFA rollout",
        },
    )
    assert resp.status_code == 200
    assessments = resp.json()["assessments"]
    assert len(assessments) == 2
    latest = assessments[0]
    assert latest["risk_score"] == 20
    assert latest["residual_risk_score"] == 4
    assert latest["notes"] == "After MFA rollout"


def test_add_assessment_validation_returns_422(client, admin_user, login_as):
    login_as(admin_user)
    created = _create_risk(client)
    resp = client.post(
        f"/api/risks/{created['risk_id']}/assessments",
        json={"likelihood": 0, "impact": 9},
    )
    assert resp.status_code == 422


def test_add_assessment_as_viewer_returns_403(
    client, admin_user, viewer_user, login_as
):
    login_as(admin_user)
    created = _create_risk(client)
    client.post("/api/auth/logout")
    client.cookies.clear()
    login_as(viewer_user)
    resp = client.post(
        f"/api/risks/{created['risk_id']}/assessments",
        json={"likelihood": 3, "impact": 3},
    )
    assert resp.status_code == 403


def test_add_assessment_to_missing_risk_returns_404(client, admin_user, login_as):
    login_as(admin_user)
    resp = client.post(
        "/api/risks/RISK-NOPE/assessments",
        json={"likelihood": 2, "impact": 2},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/risks/{id}/responses
# ---------------------------------------------------------------------------


def test_add_response_succeeds(client, admin_user, login_as):
    login_as(admin_user)
    created = _create_risk(client)
    resp = client.post(
        f"/api/risks/{created['risk_id']}/responses",
        json={
            "response_type": "mitigate",
            "mitigation_strategy": "Roll out MFA org-wide",
            "cost_estimate": "12000.00",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["responses"]) == 1
    t = body["responses"][0]
    assert t["response_type"] == "mitigate"
    assert t["mitigation_strategy"] == "Roll out MFA org-wide"


def test_add_response_validation_returns_422(client, admin_user, login_as):
    login_as(admin_user)
    created = _create_risk(client)
    # mitigation_strategy is required & must be non-empty
    resp = client.post(
        f"/api/risks/{created['risk_id']}/responses",
        json={"response_type": "mitigate", "mitigation_strategy": ""},
    )
    assert resp.status_code == 422


def test_add_response_invalid_type_returns_422(client, admin_user, login_as):
    login_as(admin_user)
    created = _create_risk(client)
    resp = client.post(
        f"/api/risks/{created['risk_id']}/responses",
        json={"response_type": "ignore", "mitigation_strategy": "x"},
    )
    assert resp.status_code == 422


def test_add_response_as_viewer_returns_403(
    client, admin_user, viewer_user, login_as
):
    login_as(admin_user)
    created = _create_risk(client)
    client.post("/api/auth/logout")
    client.cookies.clear()
    login_as(viewer_user)
    resp = client.post(
        f"/api/risks/{created['risk_id']}/responses",
        json={"response_type": "accept", "mitigation_strategy": "Live with it"},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# PATCH /api/risks/{id}/responses/{response_id}
# ---------------------------------------------------------------------------


def _create_response(client, risk_id, **overrides) -> dict:
    payload = {
        "response_type": "mitigate",
        "mitigation_strategy": "Initial plan",
    }
    payload.update(overrides)
    resp = client.post(f"/api/risks/{risk_id}/responses", json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()["responses"][0]


def test_update_response_changes_target_date_and_status(client, admin_user, login_as):
    login_as(admin_user)
    created = _create_risk(client)
    response = _create_response(client, created["risk_id"])
    new_target = "2026-12-31T00:00:00+00:00"
    resp = client.patch(
        f"/api/risks/{created['risk_id']}/responses/{response['id']}",
        json={"status": "in_progress", "target_date": new_target},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    updated = next(r for r in body["responses"] if r["id"] == response["id"])
    assert updated["status"] == "in_progress"
    assert updated["target_date"].startswith("2026-12-31")


def test_update_response_to_completed_auto_stamps_completion_date(
    client, admin_user, login_as
):
    login_as(admin_user)
    created = _create_risk(client)
    response = _create_response(client, created["risk_id"])
    assert response["completion_date"] is None
    resp = client.patch(
        f"/api/risks/{created['risk_id']}/responses/{response['id']}",
        json={"status": "completed"},
    )
    assert resp.status_code == 200, resp.text
    updated = next(
        r for r in resp.json()["responses"] if r["id"] == response["id"]
    )
    assert updated["status"] == "completed"
    assert updated["completion_date"] is not None


def test_update_response_from_completed_clears_completion_date(
    client, admin_user, login_as
):
    login_as(admin_user)
    created = _create_risk(client)
    response = _create_response(client, created["risk_id"])
    # First mark completed (auto-stamps completion_date).
    resp = client.patch(
        f"/api/risks/{created['risk_id']}/responses/{response['id']}",
        json={"status": "completed"},
    )
    assert resp.status_code == 200
    completed = next(
        r for r in resp.json()["responses"] if r["id"] == response["id"]
    )
    assert completed["completion_date"] is not None

    # Now move back to in_progress; completion_date should be cleared.
    resp = client.patch(
        f"/api/risks/{created['risk_id']}/responses/{response['id']}",
        json={"status": "in_progress"},
    )
    assert resp.status_code == 200
    reverted = next(
        r for r in resp.json()["responses"] if r["id"] == response["id"]
    )
    assert reverted["status"] == "in_progress"
    assert reverted["completion_date"] is None


def test_update_response_with_unknown_response_id_returns_404(
    client, admin_user, login_as
):
    login_as(admin_user)
    created = _create_risk(client)
    resp = client.patch(
        f"/api/risks/{created['risk_id']}/responses/99999",
        json={"status": "in_progress"},
    )
    assert resp.status_code == 404


def test_update_response_as_other_owner_returns_403(
    client, admin_user, owner_user, login_as
):
    login_as(admin_user)
    created = _create_risk(client, owner_id=admin_user.id)
    response = _create_response(client, created["risk_id"])
    client.post("/api/auth/logout")
    client.cookies.clear()
    login_as(owner_user)
    resp = client.patch(
        f"/api/risks/{created['risk_id']}/responses/{response['id']}",
        json={"status": "in_progress"},
    )
    assert resp.status_code == 403


def test_update_response_writes_audit_row(client, admin_user, login_as, db):
    from app.models.audit_log import AuditLog

    login_as(admin_user)
    created = _create_risk(client)
    response = _create_response(client, created["risk_id"])
    resp = client.patch(
        f"/api/risks/{created['risk_id']}/responses/{response['id']}",
        json={"status": "in_progress"},
    )
    assert resp.status_code == 200
    audit = (
        db.query(AuditLog)
        .filter(AuditLog.action == "risk.response.updated")
        .order_by(AuditLog.id.desc())
        .first()
    )
    assert audit is not None
    assert audit.resource_id == created["risk_id"]


# ---------------------------------------------------------------------------
# DELETE /api/risks/{id}/responses/{response_id}
# ---------------------------------------------------------------------------


def test_delete_response_removes_row(client, admin_user, login_as):
    login_as(admin_user)
    created = _create_risk(client)
    response = _create_response(client, created["risk_id"])
    resp = client.delete(
        f"/api/risks/{created['risk_id']}/responses/{response['id']}"
    )
    assert resp.status_code == 204
    # Verify it's gone from the parent risk.
    got = client.get(f"/api/risks/{created['risk_id']}").json()
    assert all(r["id"] != response["id"] for r in got["responses"])


def test_delete_response_unknown_id_returns_404(client, admin_user, login_as):
    login_as(admin_user)
    created = _create_risk(client)
    resp = client.delete(f"/api/risks/{created['risk_id']}/responses/99999")
    assert resp.status_code == 404


def test_delete_response_as_viewer_returns_403(
    client, admin_user, viewer_user, login_as
):
    login_as(admin_user)
    created = _create_risk(client)
    response = _create_response(client, created["risk_id"])
    client.post("/api/auth/logout")
    client.cookies.clear()
    login_as(viewer_user)
    resp = client.delete(
        f"/api/risks/{created['risk_id']}/responses/{response['id']}"
    )
    assert resp.status_code == 403


def test_delete_response_writes_audit_row(client, admin_user, login_as, db):
    from app.models.audit_log import AuditLog

    login_as(admin_user)
    created = _create_risk(client)
    response = _create_response(client, created["risk_id"])
    resp = client.delete(
        f"/api/risks/{created['risk_id']}/responses/{response['id']}"
    )
    assert resp.status_code == 204
    audit = (
        db.query(AuditLog)
        .filter(AuditLog.action == "risk.response.deleted")
        .order_by(AuditLog.id.desc())
        .first()
    )
    assert audit is not None
    assert audit.resource_id == created["risk_id"]


# ---------------------------------------------------------------------------
# CSV export / import / template
# ---------------------------------------------------------------------------


def test_export_returns_csv(client, admin_user, login_as):
    login_as(admin_user)
    _create_risk(client, title="Exported")
    resp = client.get("/api/risks/export")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "attachment" in resp.headers["content-disposition"]
    text = resp.text
    assert "risk_id" in text.splitlines()[0]
    assert "Exported" in text


def test_export_unauthenticated_returns_401(client):
    resp = client.get("/api/risks/export")
    assert resp.status_code == 401


def test_export_does_not_capture_export_as_risk_id(client, admin_user, login_as):
    """Sanity-check route ordering: /export must not be matched as /{risk_id}."""
    login_as(admin_user)
    resp = client.get("/api/risks/export")
    # Returning a 404 here would mean the literal "export" was treated as a risk_id.
    assert resp.status_code == 200


def test_import_template_returns_csv(client, admin_user, login_as):
    login_as(admin_user)
    resp = client.get("/api/risks/import-template")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "title" in resp.text.splitlines()[0]


def test_import_template_unauthenticated_returns_401(client):
    resp = client.get("/api/risks/import-template")
    assert resp.status_code == 401


def test_import_creates_risks_and_reports_errors(
    client, admin_user, owner_user, login_as
):
    login_as(admin_user)
    csv_content = (
        "title,description,threat_source,threat_event,vulnerability,affected_asset,"
        "category,owner_email,likelihood,impact,review_frequency_days,next_review_date\n"
        "Good row,desc,src,evt,vuln,asset,Technical,owner@example.com,3,3,90,2026-08-01\n"
        ",no title row,,,,,,,,,,\n"
        "Bad score,desc,,,,,,,9,9,,\n"
    )
    resp = client.post(
        "/api/risks/import",
        files={"file": ("risks.csv", csv_content, "text/csv")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] == 1
    assert len(body["errors"]) == 2
    error_messages = " ".join(e["message"] for e in body["errors"])
    assert "title" in error_messages.lower() or "score" in error_messages.lower()


def test_import_unknown_owner_email_reports_error(client, admin_user, login_as):
    login_as(admin_user)
    csv_content = (
        "title,description,threat_source,threat_event,vulnerability,affected_asset,"
        "category,owner_email,likelihood,impact,review_frequency_days,next_review_date\n"
        "Owner mismatch,desc,,,,,,nobody@example.com,2,2,,\n"
    )
    resp = client.post(
        "/api/risks/import",
        files={"file": ("risks.csv", csv_content, "text/csv")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] == 0
    assert len(body["errors"]) == 1
    assert "owner_email" in body["errors"][0]["message"]


def test_import_as_owner_returns_403(client, owner_user, login_as):
    login_as(owner_user)
    csv_content = "title\nx\n"
    resp = client.post(
        "/api/risks/import",
        files={"file": ("risks.csv", csv_content, "text/csv")},
    )
    assert resp.status_code == 403


def test_import_unauthenticated_returns_401(client):
    csv_content = "title\nx\n"
    resp = client.post(
        "/api/risks/import",
        files={"file": ("risks.csv", csv_content, "text/csv")},
    )
    assert resp.status_code == 401


def test_import_malformed_csv_returns_400(client, admin_user, login_as):
    login_as(admin_user)
    resp = client.post(
        "/api/risks/import",
        files={"file": ("bad.csv", b"\x00\x01\x02\xff\xfe", "text/csv")},
    )
    assert resp.status_code == 400


def test_import_over_cap_is_413(client, admin_user, login_as, monkeypatch):
    # Shrink the cap so a tiny payload trips the chunked-read 413 without 5 MB.
    from app.api import risks

    monkeypatch.setattr(risks, "MAX_IMPORT_BYTES", 1024)
    login_as(admin_user)
    resp = client.post(
        "/api/risks/import",
        files={"file": ("big.csv", b"x" * 2048, "text/csv")},
    )
    assert resp.status_code == 413
    assert resp.json()["detail"] == "CSV upload exceeds 5 MB limit"


def test_import_empty_file_returns_400(client, admin_user, login_as):
    login_as(admin_user)
    resp = client.post(
        "/api/risks/import",
        files={"file": ("empty.csv", b"", "text/csv")},
    )
    assert resp.status_code == 400


def test_import_missing_required_columns_returns_400(client, admin_user, login_as):
    login_as(admin_user)
    csv_content = "description,threat_source\nsome desc,some source\n"
    resp = client.post(
        "/api/risks/import",
        files={"file": ("risks.csv", csv_content, "text/csv")},
    )
    assert resp.status_code == 400
    assert "missing required columns" in resp.json()["detail"]


def test_import_partial_required_columns_returns_400(client, admin_user, login_as):
    login_as(admin_user)
    # Has title but no likelihood or impact
    csv_content = "title,description\nTest risk,some desc\n"
    resp = client.post(
        "/api/risks/import",
        files={"file": ("risks.csv", csv_content, "text/csv")},
    )
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "impact" in detail or "likelihood" in detail


def test_export_then_import_round_trip(client, admin_user, login_as):
    """Exported CSV header must be a superset of importable columns and parse cleanly."""
    login_as(admin_user)
    # Create one risk, then download the import template (exact header schema for import)
    _create_risk(client, title="Round-trip", category="Technical")
    template = client.get("/api/risks/import-template").text
    header, _example = template.splitlines()[0], template.splitlines()[1]
    # Build a fresh row matching that header exactly.
    new_row = ",".join(
        [
            "Imported back",  # title
            "desc",  # description
            "src",  # threat_source
            "evt",  # threat_event
            "vuln",  # vulnerability
            "asset",  # affected_asset
            "Technical",  # category
            "admin@example.com",  # owner_email
            "2",  # likelihood
            "3",  # impact
            "60",  # review_frequency_days
            "2026-09-01",  # next_review_date
        ]
    )
    csv_text = header + "\n" + new_row + "\n"
    resp = client.post(
        "/api/risks/import",
        files={"file": ("risks.csv", csv_text, "text/csv")},
    )
    assert resp.status_code == 200
    assert resp.json() == {"created": 1, "errors": []}

    listing = client.get("/api/risks").json()
    titles = {item["title"] for item in listing["items"]}
    assert "Imported back" in titles


# ---------------------------------------------------------------------------
# risk.assigned event emission
# ---------------------------------------------------------------------------


def test_changing_owner_emits_risk_assigned_event(
    client, admin_user, owner_user, login_as, monkeypatch
):
    from app.services import events as events_module
    from app.services import risk_service as risk_service_module

    captured: list[dict] = []

    def fake_emit_sync(event_type, *, subject, data, actor=None):
        captured.append({
            "type": event_type,
            "subject": subject,
            "data": data,
            "actor": actor,
        })
        return {"id": "evt_fake", "type": event_type}

    monkeypatch.setattr(risk_service_module.events, "emit_sync", fake_emit_sync)

    login_as(admin_user)
    created = _create_risk(client, owner_id=admin_user.id)

    resp = client.put(
        f"/api/risks/{created['risk_id']}",
        json={"owner_id": owner_user.id},
    )
    assert resp.status_code == 200

    risk_events = [c for c in captured if c["type"] == "risk.assigned"]
    assert len(risk_events) == 1
    env = risk_events[0]
    assert env["subject"]["risk_id"] == created["risk_id"]
    assert env["data"]["new_owner_id"] == owner_user.id
    assert env["data"]["previous_owner_id"] == admin_user.id
    assert env["actor"]["id"] == admin_user.id
    assert env["actor"]["email"] == admin_user.email


def test_updating_other_fields_does_not_emit_risk_assigned(
    client, admin_user, login_as, monkeypatch
):
    from app.services import risk_service as risk_service_module

    captured: list[str] = []

    def fake_emit_sync(event_type, **kwargs):
        captured.append(event_type)
        return {}

    monkeypatch.setattr(risk_service_module.events, "emit_sync", fake_emit_sync)

    login_as(admin_user)
    created = _create_risk(client)

    resp = client.put(
        f"/api/risks/{created['risk_id']}",
        json={"title": "Just a rename"},
    )
    assert resp.status_code == 200
    assert "risk.assigned" not in captured


# ---------------------------------------------------------------------------
# Bulk action endpoints
# ---------------------------------------------------------------------------


def test_bulk_reassign_updates_multiple_risks(
    client, admin_user, owner_user, login_as
):
    login_as(admin_user)
    a = _create_risk(client, title="A", owner_id=admin_user.id)
    b = _create_risk(client, title="B", owner_id=admin_user.id)
    resp = client.post(
        "/api/risks/bulk/reassign",
        json={"risk_ids": [a["risk_id"], b["risk_id"]], "owner_id": owner_user.id},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body["updated"]) == {a["risk_id"], b["risk_id"]}
    assert body["errors"] == []
    # Verify ownership actually changed
    for rid in (a["risk_id"], b["risk_id"]):
        got = client.get(f"/api/risks/{rid}").json()
        assert got["owner_id"] == owner_user.id


def test_bulk_reassign_captures_unknown_id_as_error(
    client, admin_user, owner_user, login_as
):
    login_as(admin_user)
    a = _create_risk(client, title="A", owner_id=admin_user.id)
    resp = client.post(
        "/api/risks/bulk/reassign",
        json={"risk_ids": [a["risk_id"], "RISK-DOESNOTEXIST"], "owner_id": owner_user.id},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["updated"] == [a["risk_id"]]
    assert len(body["errors"]) == 1
    assert body["errors"][0]["risk_id"] == "RISK-DOESNOTEXIST"
    assert "not found" in body["errors"][0]["message"].lower()


def test_bulk_reassign_dedupes_risk_ids(
    client, admin_user, owner_user, login_as
):
    login_as(admin_user)
    a = _create_risk(client, title="A", owner_id=admin_user.id)
    resp = client.post(
        "/api/risks/bulk/reassign",
        json={"risk_ids": [a["risk_id"], a["risk_id"]], "owner_id": owner_user.id},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["updated"] == [a["risk_id"]]
    assert body["errors"] == []


def test_bulk_reassign_as_owner_returns_403(
    client, admin_user, owner_user, login_as
):
    login_as(admin_user)
    a = _create_risk(client, title="A", owner_id=admin_user.id)
    client.post("/api/auth/logout")
    client.cookies.clear()
    login_as(owner_user)
    resp = client.post(
        "/api/risks/bulk/reassign",
        json={"risk_ids": [a["risk_id"]], "owner_id": owner_user.id},
    )
    assert resp.status_code == 403


def test_bulk_reassign_rejects_too_many_ids(client, admin_user, login_as):
    login_as(admin_user)
    resp = client.post(
        "/api/risks/bulk/reassign",
        json={"risk_ids": [f"RISK-{i:03d}" for i in range(201)], "owner_id": admin_user.id},
    )
    assert resp.status_code == 422


def test_bulk_reassign_empty_list_returns_422(client, admin_user, login_as):
    login_as(admin_user)
    resp = client.post(
        "/api/risks/bulk/reassign",
        json={"risk_ids": [], "owner_id": admin_user.id},
    )
    assert resp.status_code == 422


def test_bulk_status_updates_multiple_risks(client, admin_user, login_as):
    login_as(admin_user)
    a = _create_risk(client, title="A")
    b = _create_risk(client, title="B")
    resp = client.post(
        "/api/risks/bulk/status",
        json={"risk_ids": [a["risk_id"], b["risk_id"]], "status": "in_progress"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body["updated"]) == {a["risk_id"], b["risk_id"]}
    assert body["errors"] == []
    for rid in (a["risk_id"], b["risk_id"]):
        got = client.get(f"/api/risks/{rid}").json()
        assert got["status"] == "in_progress"


def test_bulk_status_as_viewer_captures_per_risk_403(
    client, admin_user, viewer_user, login_as
):
    login_as(admin_user)
    a = _create_risk(client, title="A")
    client.post("/api/auth/logout")
    client.cookies.clear()
    login_as(viewer_user)
    resp = client.post(
        "/api/risks/bulk/status",
        json={"risk_ids": [a["risk_id"]], "status": "in_progress"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["updated"] == []
    assert len(body["errors"]) == 1
    assert body["errors"][0]["risk_id"] == a["risk_id"]
    assert "read-only" in body["errors"][0]["message"].lower()


def test_bulk_status_unknown_risk_id_captured(client, admin_user, login_as):
    login_as(admin_user)
    resp = client.post(
        "/api/risks/bulk/status",
        json={"risk_ids": ["RISK-NONE"], "status": "closed"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["updated"] == []
    assert len(body["errors"]) == 1
    assert body["errors"][0]["risk_id"] == "RISK-NONE"


def test_bulk_rescore_creates_new_assessment_per_risk(
    client, admin_user, login_as
):
    login_as(admin_user)
    a = _create_risk(client, likelihood=2, impact=2)
    b = _create_risk(client, likelihood=1, impact=1)
    resp = client.post(
        "/api/risks/bulk/rescore",
        json={
            "risk_ids": [a["risk_id"], b["risk_id"]],
            "likelihood": 4,
            "impact": 5,
            "notes": "Post-incident reassessment",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body["updated"]) == {a["risk_id"], b["risk_id"]}
    assert body["errors"] == []
    for rid in (a["risk_id"], b["risk_id"]):
        got = client.get(f"/api/risks/{rid}").json()
        latest = got["assessments"][0]
        assert latest["likelihood"] == 4
        assert latest["impact"] == 5
        assert latest["risk_score"] == 20
        assert latest["notes"] == "Post-incident reassessment"


def test_bulk_rescore_rejects_out_of_range_score(client, admin_user, login_as):
    login_as(admin_user)
    a = _create_risk(client)
    resp = client.post(
        "/api/risks/bulk/rescore",
        json={"risk_ids": [a["risk_id"]], "likelihood": 9, "impact": 9},
    )
    assert resp.status_code == 422


def test_bulk_rescore_unknown_id_captured_as_error(client, admin_user, login_as):
    login_as(admin_user)
    a = _create_risk(client)
    resp = client.post(
        "/api/risks/bulk/rescore",
        json={
            "risk_ids": [a["risk_id"], "RISK-NOPE"],
            "likelihood": 3,
            "impact": 3,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["updated"] == [a["risk_id"]]
    assert len(body["errors"]) == 1
    assert body["errors"][0]["risk_id"] == "RISK-NOPE"


def test_bulk_routes_unauthenticated_returns_401(client):
    resp = client.post(
        "/api/risks/bulk/status",
        json={"risk_ids": ["RISK-001"], "status": "open"},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Datetime serialization — naive DB values must come back tz-aware (UTC)
#
# SQLite drops tzinfo from DateTime(timezone=True) columns. Without an explicit
# serializer the API would emit ISO strings without an offset (e.g.
# "2026-05-26T03:00:00"), which JS interprets as LOCAL time on the frontend
# — shifting toLocaleDateString() by up to a day. Every datetime on a response
# schema must include `Z` or `+00:00`.
# ---------------------------------------------------------------------------


def _has_utc_offset(value: str) -> bool:
    return value.endswith("Z") or value.endswith("+00:00")


def test_risk_response_datetimes_include_utc_offset(client, admin_user, login_as, db):
    """Even with naive DB datetimes, every response datetime must end in Z/+00:00."""
    login_as(admin_user)
    created = _create_risk(client)

    # Force the stored datetimes naive to simulate the SQLite tzinfo-stripping path.
    row = db.query(Risk).filter_by(risk_id=created["risk_id"]).one()
    row.created_at = row.created_at.replace(tzinfo=None)
    for a in row.assessments:
        a.assessed_at = a.assessed_at.replace(tzinfo=None)
    db.commit()

    resp = client.get(f"/api/risks/{created['risk_id']}")
    assert resp.status_code == 200
    body = resp.json()

    assert _has_utc_offset(body["created_at"]), body["created_at"]
    assert body["assessments"], "expected at least one assessment"
    for a in body["assessments"]:
        assert _has_utc_offset(a["assessed_at"]), a["assessed_at"]


def test_risk_response_naive_db_datetime_serialized_as_utc(
    client, admin_user, login_as, db
):
    """A naive 2026-05-26T03:00:00 row must serialize as 2026-05-26T03:00:00+00:00."""
    from datetime import datetime as _dt

    login_as(admin_user)
    created = _create_risk(client)
    row = db.query(Risk).filter_by(risk_id=created["risk_id"]).one()
    naive_value = _dt(2026, 5, 26, 3, 0, 0)
    row.assessments[0].assessed_at = naive_value
    db.commit()

    resp = client.get(f"/api/risks/{created['risk_id']}")
    body = resp.json()
    assessed_at = body["assessments"][0]["assessed_at"]
    # Wire format must explicitly mark the value as UTC.
    assert assessed_at == "2026-05-26T03:00:00+00:00", assessed_at


# ---------------------------------------------------------------------------
# GET /api/risks — search
# ---------------------------------------------------------------------------


def test_list_risks_search_matches_title(client, admin_user, login_as):
    login_as(admin_user)
    _create_risk(client, title="Ransomware exposure")
    _create_risk(client, title="Vendor risk")
    body = client.get("/api/risks?search=ransomware").json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "Ransomware exposure"


def test_list_risks_search_matches_description(client, admin_user, login_as):
    login_as(admin_user)
    _create_risk(client, title="A", description="Unpatched VPN appliance")
    _create_risk(client, title="B", description="Unrelated")
    body = client.get("/api/risks?search=vpn").json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "A"


def test_list_risks_search_matches_risk_id(client, admin_user, login_as):
    login_as(admin_user)
    created = _create_risk(client, title="A")
    _create_risk(client, title="B")
    body = client.get(f"/api/risks?search={created['risk_id']}").json()
    assert body["total"] == 1
    assert body["items"][0]["risk_id"] == created["risk_id"]


def test_list_risks_search_matches_owner_name(client, admin_user, owner_user, login_as):
    login_as(admin_user)
    _create_risk(client, title="Owned", owner_id=owner_user.id)
    _create_risk(client, title="Not owned", owner_id=admin_user.id)
    body = client.get(f"/api/risks?search={owner_user.full_name}").json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "Owned"


def test_list_risks_search_percent_is_literal(client, admin_user, login_as):
    login_as(admin_user)
    # Neither title contains a literal "%" — if the LIKE wildcard weren't
    # escaped, "A%B" would match "AxB" (any chars between A and B).
    _create_risk(client, title="AxB risk")
    _create_risk(client, title="50% outage risk")
    body = client.get("/api/risks?search=A%25B").json()
    assert body["total"] == 0

    body = client.get("/api/risks?search=50%25").json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "50% outage risk"


def test_list_risks_search_underscore_is_literal(client, admin_user, login_as):
    login_as(admin_user)
    # If "_" weren't escaped, it would match any single character, so "A_B"
    # would match "AXB" even though neither title contains a literal "_".
    _create_risk(client, title="AXB risk")
    _create_risk(client, title="Unrelated")
    body = client.get("/api/risks?search=A_B").json()
    assert body["total"] == 0


def test_list_risks_search_blank_is_ignored(client, admin_user, login_as):
    login_as(admin_user)
    _create_risk(client, title="A")
    _create_risk(client, title="B")
    body = client.get("/api/risks?search=   ").json()
    assert body["total"] == 2


def test_list_risks_search_case_insensitive(client, admin_user, login_as):
    login_as(admin_user)
    _create_risk(client, title="Phishing Risk")
    body = client.get("/api/risks?search=PHISHING").json()
    assert body["total"] == 1


def test_list_risks_search_too_long_returns_422(client, admin_user, login_as):
    login_as(admin_user)
    resp = client.get(f"/api/risks?search={'a' * 201}")
    assert resp.status_code == 422


def test_list_risks_search_with_owner_scoping(
    client, admin_user, owner_user, owner_user_b, login_as
):
    login_as(admin_user)
    _create_risk(client, title="Owner A risk", owner_id=owner_user.id)
    _create_risk(client, title="Owner B risk", owner_id=owner_user_b.id)
    client.post("/api/auth/logout")
    client.cookies.clear()
    login_as(owner_user)
    body = client.get("/api/risks?search=risk").json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "Owner A risk"


# ---------------------------------------------------------------------------
# GET /api/risks — severity filter
# ---------------------------------------------------------------------------


def test_list_risks_severity_buckets(client, admin_user, login_as):
    login_as(admin_user)
    _create_risk(client, title="Low", likelihood=1, impact=2)       # score 2
    _create_risk(client, title="Medium", likelihood=3, impact=3)    # score 9
    _create_risk(client, title="High", likelihood=4, impact=4)      # score 16
    _create_risk(client, title="Critical", likelihood=5, impact=5)  # score 25
    _create_risk(client, title="Unscored", likelihood=None, impact=None)

    for severity, expected_title in [
        ("low", "Low"),
        ("medium", "Medium"),
        ("high", "High"),
        ("critical", "Critical"),
        ("unscored", "Unscored"),
    ]:
        body = client.get(f"/api/risks?severity={severity}").json()
        assert body["total"] == 1, severity
        assert body["items"][0]["title"] == expected_title, severity


def test_list_risks_severity_uses_residual_score_over_inherent(client, admin_user, login_as):
    login_as(admin_user)
    created = _create_risk(client, likelihood=5, impact=5)  # inherent 25, critical
    client.post(
        f"/api/risks/{created['risk_id']}/assessments",
        json={"likelihood": 5, "impact": 5, "residual_likelihood": 1, "residual_impact": 1},
    )
    # Residual score (1) puts it in "low", not "critical".
    assert client.get("/api/risks?severity=critical").json()["total"] == 0
    body = client.get("/api/risks?severity=low").json()
    assert body["total"] == 1
    assert body["items"][0]["risk_id"] == created["risk_id"]


def test_list_risks_severity_invalid_returns_422(client, admin_user, login_as):
    login_as(admin_user)
    resp = client.get("/api/risks?severity=extreme")
    assert resp.status_code == 422


def _minimal_risk(client, **overrides) -> dict:
    """Create a risk with no incidental "phishing" text in the other fields."""
    payload = {
        "title": overrides.pop("title"),
        "description": "",
        "threat_source": "",
        "threat_event": "",
        "vulnerability": "",
        "affected_asset": "",
        "category": "General",
    }
    payload.update(overrides)
    resp = client.post("/api/risks", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_list_risks_total_reflects_search_and_severity(client, admin_user, login_as):
    login_as(admin_user)
    _minimal_risk(client, title="Phishing high", likelihood=4, impact=4)
    _minimal_risk(client, title="Phishing low", likelihood=1, impact=1)
    _minimal_risk(client, title="Other risk", likelihood=4, impact=4)
    body = client.get("/api/risks?search=phishing&severity=high").json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "Phishing high"


# ---------------------------------------------------------------------------
# GET /api/risks — sort / order
# ---------------------------------------------------------------------------


def test_list_risks_default_order_unchanged_when_sort_omitted(client, admin_user, login_as):
    login_as(admin_user)
    same_second = "2026-01-15T10:00:00+00:00"
    created = [
        _create_risk(client, title=f"R{i}", created_at=same_second)["risk_id"]
        for i in range(3)
    ]
    body = client.get("/api/risks").json()
    assert [item["risk_id"] for item in body["items"]] == list(reversed(created))


def test_list_risks_sort_by_id(client, admin_user, login_as):
    login_as(admin_user)
    a = _create_risk(client, title="A")
    b = _create_risk(client, title="B")
    c = _create_risk(client, title="C")

    body = client.get("/api/risks?sort=id&order=asc").json()
    assert [i["risk_id"] for i in body["items"]] == [a["risk_id"], b["risk_id"], c["risk_id"]]

    body = client.get("/api/risks?sort=id&order=desc").json()
    assert [i["risk_id"] for i in body["items"]] == [c["risk_id"], b["risk_id"], a["risk_id"]]


def test_list_risks_sort_by_title(client, admin_user, login_as):
    login_as(admin_user)
    _create_risk(client, title="Charlie")
    _create_risk(client, title="alpha")
    _create_risk(client, title="Bravo")

    body = client.get("/api/risks?sort=title&order=asc").json()
    assert [i["title"] for i in body["items"]] == ["alpha", "Bravo", "Charlie"]

    body = client.get("/api/risks?sort=title&order=desc").json()
    assert [i["title"] for i in body["items"]] == ["Charlie", "Bravo", "alpha"]


def test_list_risks_sort_by_category_nulls_last_both_directions(client, admin_user, login_as):
    login_as(admin_user)
    _create_risk(client, title="NoCategory", category=None)
    _create_risk(client, title="Zebra", category="Zebra")
    _create_risk(client, title="Alpha", category="Alpha")

    body = client.get("/api/risks?sort=category&order=asc").json()
    assert [i["title"] for i in body["items"]] == ["Alpha", "Zebra", "NoCategory"]

    body = client.get("/api/risks?sort=category&order=desc").json()
    assert [i["title"] for i in body["items"]] == ["Zebra", "Alpha", "NoCategory"]


def test_list_risks_sort_by_score_unscored_is_lowest(client, admin_user, login_as):
    login_as(admin_user)
    _create_risk(client, title="Unscored", likelihood=None, impact=None)
    _create_risk(client, title="Low", likelihood=1, impact=1)
    _create_risk(client, title="High", likelihood=4, impact=4)

    body = client.get("/api/risks?sort=score&order=asc").json()
    assert [i["title"] for i in body["items"]] == ["Unscored", "Low", "High"]

    body = client.get("/api/risks?sort=score&order=desc").json()
    assert [i["title"] for i in body["items"]] == ["High", "Low", "Unscored"]


def test_list_risks_sort_by_status(client, admin_user, login_as, db):
    login_as(admin_user)
    a = _create_risk(client, title="A")
    b = _create_risk(client, title="B")
    risk_a = db.query(Risk).filter(Risk.risk_id == a["risk_id"]).first()
    risk_a.status = RiskStatus.closed
    db.commit()

    body = client.get("/api/risks?sort=status&order=asc").json()
    statuses = [i["status"] for i in body["items"]]
    assert statuses == sorted(statuses)


def test_list_risks_sort_by_owner(client, admin_user, owner_user, owner_user_b, login_as):
    login_as(admin_user)
    _create_risk(client, title="Owned by B", owner_id=owner_user_b.id)
    _create_risk(client, title="Owned by A", owner_id=owner_user.id)

    body = client.get("/api/risks?sort=owner&order=asc").json()
    owner_names_in_order = [i["owner"]["full_name"] for i in body["items"]]
    assert owner_names_in_order == sorted(owner_names_in_order, key=str.lower)


def test_list_risks_sort_by_next_review_nulls_last_both_directions(client, admin_user, login_as):
    login_as(admin_user)
    _create_risk(client, title="NoDate")
    _create_risk(
        client,
        title="Later",
        review_frequency_days=30,
        next_review_date=(date.today() + timedelta(days=30)).isoformat(),
    )
    _create_risk(
        client,
        title="Sooner",
        review_frequency_days=30,
        next_review_date=(date.today() + timedelta(days=1)).isoformat(),
    )

    body = client.get("/api/risks?sort=next_review&order=asc").json()
    assert [i["title"] for i in body["items"]] == ["Sooner", "Later", "NoDate"]

    body = client.get("/api/risks?sort=next_review&order=desc").json()
    assert [i["title"] for i in body["items"]] == ["Later", "Sooner", "NoDate"]


def test_list_risks_sort_invalid_returns_422(client, admin_user, login_as):
    login_as(admin_user)
    resp = client.get("/api/risks?sort=bogus")
    assert resp.status_code == 422


def test_list_risks_order_invalid_returns_422(client, admin_user, login_as):
    login_as(admin_user)
    resp = client.get("/api/risks?sort=id&order=sideways")
    assert resp.status_code == 422


def test_list_risks_sort_stable_paging_with_ties(client, admin_user, login_as):
    """All risks share the same category (a heavy tie), so the id.desc()
    tiebreak must still produce a stable, gap-free, repeat-free page walk."""
    login_as(admin_user)
    created = [
        _create_risk(client, title=f"R{i}", category="Same")["risk_id"] for i in range(9)
    ]

    seen: list[str] = []
    for skip in range(0, 9, 4):
        body = client.get(f"/api/risks?sort=category&order=asc&skip={skip}&limit=4").json()
        seen.extend(i["risk_id"] for i in body["items"])

    assert len(seen) == len(set(seen)), "paging produced duplicates"
    assert set(seen) == set(created), "paging missed some risks"


def test_list_risks_sort_with_owner_scoping_still_enforced(
    client, admin_user, owner_user, owner_user_b, login_as
):
    login_as(admin_user)
    _create_risk(client, title="Owner A risk", owner_id=owner_user.id)
    _create_risk(client, title="Owner B risk", owner_id=owner_user_b.id)
    client.post("/api/auth/logout")
    client.cookies.clear()
    login_as(owner_user)
    body = client.get("/api/risks?sort=title&order=asc").json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "Owner A risk"


# ---------------------------------------------------------------------------
# GET /api/risks/owners
# ---------------------------------------------------------------------------


def test_list_owners_returns_distinct_owners_sorted(
    client, admin_user, owner_user, owner_user_b, login_as
):
    login_as(admin_user)
    _create_risk(client, title="A", owner_id=owner_user_b.id)
    _create_risk(client, title="B", owner_id=owner_user_b.id)  # same owner, should dedupe
    _create_risk(client, title="C", owner_id=owner_user.id)

    resp = client.get("/api/risks/owners")
    assert resp.status_code == 200
    body = resp.json()
    names = [o["full_name"] for o in body]
    assert len(names) == len(set(o["id"] for o in body))
    assert names == sorted(names, key=str.lower)
    owner_ids = {o["id"] for o in body}
    assert owner_ids == {owner_user.id, owner_user_b.id}


def test_list_owners_risk_owner_sees_only_self(
    client, admin_user, owner_user, owner_user_b, login_as
):
    login_as(admin_user)
    _create_risk(client, title="A", owner_id=owner_user.id)
    _create_risk(client, title="B", owner_id=owner_user_b.id)
    client.post("/api/auth/logout")
    client.cookies.clear()
    login_as(owner_user)
    resp = client.get("/api/risks/owners")
    body = resp.json()
    assert [o["id"] for o in body] == [owner_user.id]


def test_list_owners_executive_viewer_allowed(client, admin_user, viewer_user, login_as):
    login_as(admin_user)
    _create_risk(client, title="A", owner_id=admin_user.id)
    client.post("/api/auth/logout")
    client.cookies.clear()
    login_as(viewer_user)
    resp = client.get("/api/risks/owners")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_list_owners_excludes_owners_of_only_soft_deleted_risks(
    client, admin_user, owner_user, login_as
):
    login_as(admin_user)
    created = _create_risk(client, title="Will be deleted", owner_id=owner_user.id)
    client.delete(f"/api/risks/{created['risk_id']}")
    resp = client.get("/api/risks/owners")
    body = resp.json()
    assert owner_user.id not in {o["id"] for o in body}


def test_list_owners_unauthenticated_returns_401(client):
    resp = client.get("/api/risks/owners")
    assert resp.status_code == 401


def test_owners_route_not_captured_by_risk_id_path(client, admin_user, login_as):
    """`/owners` must resolve to the owners endpoint, not GET /{risk_id}."""
    login_as(admin_user)
    resp = client.get("/api/risks/owners")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
