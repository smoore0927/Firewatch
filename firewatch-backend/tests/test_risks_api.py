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
