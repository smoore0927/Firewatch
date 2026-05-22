"""Integration tests for /api/dashboard."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from app.models.risk import (
    Risk,
    RiskAssessment,
    RiskHistory,
    RiskResponse,
    RiskStatus,
    ResponseStatus,
    ResponseType,
)


def _create_risk(client, **overrides) -> dict:
    payload = {"title": "Default", "likelihood": 3, "impact": 3}
    payload.update(overrides)
    resp = client.post("/api/risks", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


_seed_counter = {"n": 0}


def _seed_risk_with_assessment(
    db,
    *,
    owner,
    score: int,
    assessed_at: datetime,
    deleted: bool = False,
) -> Risk:
    """Insert a Risk and one RiskAssessment with an exact score and timestamp."""
    _seed_counter["n"] += 1
    risk = Risk(
        risk_id=f"RISK-{_seed_counter['n']:04d}",
        title=f"Seed {_seed_counter['n']}",
        owner_id=owner.id,
        created_by_id=owner.id,
        status=RiskStatus.open,
    )
    if deleted:
        risk.deleted_at = datetime.now(timezone.utc)
    db.add(risk)
    db.flush()
    likelihood = 1
    impact = score if score <= 5 else 5
    db.add(RiskAssessment(
        risk_id=risk.id,
        likelihood=likelihood,
        impact=impact,
        risk_score=score,
        assessed_by_id=owner.id,
        assessed_at=assessed_at,
    ))
    db.commit()
    db.refresh(risk)
    return risk


# --- /summary ------------------------------------------------------------------


def test_summary_empty_state(client, admin_user, login_as):
    login_as(admin_user)
    resp = client.get("/api/dashboard/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0
    assert body["by_status"] == {
        "open": 0,
        "in_progress": 0,
        "mitigated": 0,
        "accepted": 0,
        "closed": 0,
    }
    assert body["by_severity"] == {
        "Critical": 0,
        "High": 0,
        "Medium": 0,
        "Low": 0,
        "Unscored": 0,
    }
    assert body["overdue_responses"] == 0
    assert body["overdue_reviews"] == 0
    assert body["risk_matrix"] == [[0] * 5 for _ in range(5)]


def test_summary_with_data(client, admin_user, login_as):
    login_as(admin_user)
    # Three scored risks across severity buckets
    _create_risk(client, title="Crit", likelihood=5, impact=5)  # score 25 → Critical
    _create_risk(client, title="High", likelihood=4, impact=4)  # score 16 → High
    _create_risk(client, title="Med", likelihood=3, impact=3)   # score  9 → Medium
    _create_risk(client, title="Low", likelihood=1, impact=2)   # score  2 → Low
    # One unscored risk
    unscored = client.post(
        "/api/risks", json={"title": "Unscored", "description": "no score"}
    )
    assert unscored.status_code == 201
    # One overdue review
    _create_risk(
        client,
        title="Overdue",
        likelihood=2,
        impact=2,
        review_frequency_days=30,
        next_review_date=(date.today() - timedelta(days=1)).isoformat(),
    )

    resp = client.get("/api/dashboard/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 6
    assert body["by_status"]["open"] == 6
    assert body["by_severity"]["Critical"] == 1
    assert body["by_severity"]["High"] == 1
    assert body["by_severity"]["Medium"] == 1
    assert body["by_severity"]["Low"] == 2  # the score=2 and score=4 (overdue) risks
    assert body["by_severity"]["Unscored"] == 1
    assert body["overdue_reviews"] >= 1
    # risk_matrix is [likelihood-1][impact-1]
    assert body["risk_matrix"][4][4] == 1   # 5x5 critical
    assert body["risk_matrix"][2][2] == 1   # 3x3 medium


def test_summary_unauthenticated_returns_401(client):
    resp = client.get("/api/dashboard/summary")
    assert resp.status_code == 401


# --- /score-history ------------------------------------------------------------


def test_score_history_empty(client, admin_user, login_as):
    login_as(admin_user)
    resp = client.get(
        "/api/dashboard/score-history",
        params={"start": "2026-01-01", "end": "2026-12-31"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"points": []}


def test_score_history_returns_average_per_day(client, admin_user, login_as):
    login_as(admin_user)
    _create_risk(client, title="A", likelihood=2, impact=3)  # score 6
    _create_risk(client, title="B", likelihood=4, impact=5)  # score 20
    # Rows are timestamped with func.now() (UTC) — the endpoint groups by UTC
    # date, so the test must ask for the UTC "today" to match.
    today = datetime.now(timezone.utc).date().isoformat()
    resp = client.get(
        "/api/dashboard/score-history",
        params={"start": today, "end": today},
    )
    assert resp.status_code == 200
    points = resp.json()["points"]
    assert len(points) == 1
    assert points[0]["count"] == 2
    # Average of 6 and 20 = 13.0
    assert points[0]["avg_score"] == 13.0


def test_score_history_missing_params_returns_422(client, admin_user, login_as):
    login_as(admin_user)
    resp = client.get("/api/dashboard/score-history")
    assert resp.status_code == 422


def test_score_history_unauthenticated_returns_401(client):
    resp = client.get(
        "/api/dashboard/score-history",
        params={"start": "2026-01-01", "end": "2026-12-31"},
    )
    assert resp.status_code == 401


# --- /score-totals-by-severity -------------------------------------------------


def test_score_totals_by_severity_unauthenticated_returns_401(client):
    resp = client.get(
        "/api/dashboard/score-totals-by-severity",
        params={"start": "2026-01-01", "end": "2026-12-31"},
    )
    assert resp.status_code == 401


def test_score_totals_by_severity_empty(client, admin_user, login_as):
    login_as(admin_user)
    # Cumulative semantics: one point per day in the window, all zero buckets
    # when there are no risks.
    resp = client.get(
        "/api/dashboard/score-totals-by-severity",
        params={"start": "2026-05-01", "end": "2026-05-07"},
    )
    assert resp.status_code == 200
    points = resp.json()["points"]
    assert len(points) == 7
    for p in points:
        assert p["low"] == 0
        assert p["medium"] == 0
        assert p["high"] == 0
        assert p["critical"] == 0


def test_score_totals_by_severity_severity_buckets_at_edges(
    client, admin_user, login_as, db
):
    login_as(admin_user)
    day = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
    # Edge scores covering all four buckets.
    # Low: 1, 5  ->  sum 6
    # Medium: 6, 12 -> sum 18
    # High: 13, 20 -> sum 33
    # Critical: 21, 25 -> sum 46
    for score in [1, 5, 6, 12, 13, 20, 21, 25]:
        _seed_risk_with_assessment(db, owner=admin_user, score=score, assessed_at=day)

    resp = client.get(
        "/api/dashboard/score-totals-by-severity",
        params={"start": "2026-05-01", "end": "2026-05-01"},
    )
    assert resp.status_code == 200
    points = resp.json()["points"]
    assert len(points) == 1
    p = points[0]
    assert p["date"] == "2026-05-01"
    assert p["low"] == 6       # 1 + 5
    assert p["medium"] == 18   # 6 + 12
    assert p["high"] == 33     # 13 + 20
    assert p["critical"] == 46  # 21 + 25


def test_score_totals_by_severity_cumulative_across_days(
    client, admin_user, login_as, db
):
    """Cumulative semantics: each day shows the active total as of that day.

    Risk 1 scored 10 (medium) on day_a (5/1). Risks 2 & 3 scored 4 (low) and
    22 (critical) on day_b (5/3). Day 5/1 sees only risk 1. Day 5/2 still
    shows only risk 1 (its score persists). Day 5/3+ sees all three.
    """
    login_as(admin_user)
    day_a = datetime(2026, 5, 1, 9, 0, tzinfo=timezone.utc)
    day_b = datetime(2026, 5, 3, 9, 0, tzinfo=timezone.utc)
    _seed_risk_with_assessment(db, owner=admin_user, score=4, assessed_at=day_b)
    _seed_risk_with_assessment(db, owner=admin_user, score=10, assessed_at=day_a)
    _seed_risk_with_assessment(db, owner=admin_user, score=22, assessed_at=day_b)

    resp = client.get(
        "/api/dashboard/score-totals-by-severity",
        params={"start": "2026-05-01", "end": "2026-05-05"},
    )
    assert resp.status_code == 200
    points = resp.json()["points"]
    assert len(points) == 5
    by_date = {p["date"]: p for p in points}

    # 5/1 — only risk 1 (score 10, medium).
    assert by_date["2026-05-01"]["medium"] == 10
    assert by_date["2026-05-01"]["low"] == 0
    assert by_date["2026-05-01"]["critical"] == 0

    # 5/2 — still only risk 1 (cumulative carry-over).
    assert by_date["2026-05-02"]["medium"] == 10
    assert by_date["2026-05-02"]["low"] == 0
    assert by_date["2026-05-02"]["critical"] == 0

    # 5/3 — all three risks now active.
    assert by_date["2026-05-03"]["low"] == 4
    assert by_date["2026-05-03"]["medium"] == 10
    assert by_date["2026-05-03"]["high"] == 0
    assert by_date["2026-05-03"]["critical"] == 22

    # 5/4, 5/5 — totals persist with no new assessments.
    for d in ("2026-05-04", "2026-05-05"):
        assert by_date[d]["low"] == 4
        assert by_date[d]["medium"] == 10
        assert by_date[d]["high"] == 0
        assert by_date[d]["critical"] == 22


def test_score_totals_by_severity_excludes_soft_deleted(
    client, admin_user, login_as, db
):
    login_as(admin_user)
    day = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
    _seed_risk_with_assessment(db, owner=admin_user, score=8, assessed_at=day)
    _seed_risk_with_assessment(
        db, owner=admin_user, score=15, assessed_at=day, deleted=True
    )

    resp = client.get(
        "/api/dashboard/score-totals-by-severity",
        params={"start": "2026-05-01", "end": "2026-05-01"},
    )
    assert resp.status_code == 200
    points = resp.json()["points"]
    assert len(points) == 1
    # Only the medium=8 assessment remains; the high=15 risk was soft-deleted.
    assert points[0]["medium"] == 8
    assert points[0]["high"] == 0


def test_score_totals_by_severity_assessment_before_window_persists(
    client, admin_user, login_as, db
):
    """A risk assessed before the window starts still contributes inside it.

    Under cumulative semantics, the latest assessment on-or-before each day
    counts — even when that assessment was recorded prior to ``start``.
    """
    login_as(admin_user)
    before = datetime(2026, 4, 30, 12, 0, tzinfo=timezone.utc)
    in_range = datetime(2026, 5, 10, 12, 0, tzinfo=timezone.utc)
    after = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    _seed_risk_with_assessment(db, owner=admin_user, score=9, assessed_at=before)
    _seed_risk_with_assessment(db, owner=admin_user, score=9, assessed_at=in_range)
    # Future-dated assessment must not contribute to any day in the window.
    _seed_risk_with_assessment(db, owner=admin_user, score=9, assessed_at=after)

    resp = client.get(
        "/api/dashboard/score-totals-by-severity",
        params={"start": "2026-05-01", "end": "2026-05-31"},
    )
    assert resp.status_code == 200
    points = resp.json()["points"]
    assert len(points) == 31
    by_date = {p["date"]: p for p in points}
    # 5/1..5/9 — only the "before" risk is active: medium = 9.
    assert by_date["2026-05-01"]["medium"] == 9
    assert by_date["2026-05-09"]["medium"] == 9
    # 5/10..5/31 — both the "before" and "in_range" risks are active: medium = 18.
    assert by_date["2026-05-10"]["medium"] == 18
    assert by_date["2026-05-31"]["medium"] == 18


def test_score_totals_includes_risks_after_their_assessment(
    client, admin_user, login_as, db
):
    """A risk scored 16 (high) on day 1 should still contribute 16 on day 5."""
    login_as(admin_user)
    day_1 = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
    _seed_risk_with_assessment(db, owner=admin_user, score=16, assessed_at=day_1)

    resp = client.get(
        "/api/dashboard/score-totals-by-severity",
        params={"start": "2026-05-01", "end": "2026-05-05"},
    )
    assert resp.status_code == 200
    points = resp.json()["points"]
    assert len(points) == 5
    for p in points:
        assert p["high"] == 16
        assert p["low"] == 0
        assert p["medium"] == 0
        assert p["critical"] == 0


def test_score_totals_reflects_latest_assessment(
    client, admin_user, login_as, db
):
    """Re-scoring a risk moves its contribution to the new bucket on that day."""
    login_as(admin_user)
    day_1 = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
    day_5 = datetime(2026, 5, 5, 12, 0, tzinfo=timezone.utc)

    # Seed the risk via the helper (creates the day-1 medium=12 assessment),
    # then add a second assessment on day 5 promoting it to high=20.
    risk = _seed_risk_with_assessment(db, owner=admin_user, score=12, assessed_at=day_1)
    db.add(RiskAssessment(
        risk_id=risk.id,
        likelihood=4,
        impact=5,
        risk_score=20,
        assessed_by_id=admin_user.id,
        assessed_at=day_5,
    ))
    db.commit()

    resp = client.get(
        "/api/dashboard/score-totals-by-severity",
        params={"start": "2026-05-01", "end": "2026-05-07"},
    )
    assert resp.status_code == 200
    points = resp.json()["points"]
    assert len(points) == 7
    by_date = {p["date"]: p for p in points}
    # Days 1–4 show the medium=12 score.
    for d in ("2026-05-01", "2026-05-02", "2026-05-03", "2026-05-04"):
        assert by_date[d]["medium"] == 12
        assert by_date[d]["high"] == 0
    # Day 5 onward shows the high=20 score; medium drops to 0.
    for d in ("2026-05-05", "2026-05-06", "2026-05-07"):
        assert by_date[d]["medium"] == 0
        assert by_date[d]["high"] == 20


def test_score_totals_returns_one_point_per_day(client, admin_user, login_as):
    """A 7-day window emits exactly 7 points, even with no data."""
    login_as(admin_user)
    resp = client.get(
        "/api/dashboard/score-totals-by-severity",
        params={"start": "2026-05-01", "end": "2026-05-07"},
    )
    assert resp.status_code == 200
    points = resp.json()["points"]
    assert len(points) == 7
    assert [p["date"] for p in points] == [
        "2026-05-01", "2026-05-02", "2026-05-03",
        "2026-05-04", "2026-05-05", "2026-05-06", "2026-05-07",
    ]


def test_score_totals_unscored_risk_contributes_nothing(
    client, admin_user, login_as, db
):
    """A risk with no assessments contributes nothing on any day."""
    login_as(admin_user)
    _seed_counter["n"] += 1
    risk = Risk(
        risk_id=f"RISK-{_seed_counter['n']:04d}",
        title=f"Unscored {_seed_counter['n']}",
        owner_id=admin_user.id,
        created_by_id=admin_user.id,
        status=RiskStatus.open,
    )
    db.add(risk)
    db.commit()

    resp = client.get(
        "/api/dashboard/score-totals-by-severity",
        params={"start": "2026-05-01", "end": "2026-05-05"},
    )
    assert resp.status_code == 200
    points = resp.json()["points"]
    assert len(points) == 5
    for p in points:
        assert p["low"] == 0
        assert p["medium"] == 0
        assert p["high"] == 0
        assert p["critical"] == 0


def test_score_totals_scoped_to_owner(
    client, owner_user, owner_user_b, login_as, db
):
    """A risk_owner only sees totals derived from their own risks."""
    day = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
    _seed_risk_with_assessment(db, owner=owner_user, score=10, assessed_at=day)
    _seed_risk_with_assessment(db, owner=owner_user_b, score=22, assessed_at=day)

    login_as(owner_user)
    resp = client.get(
        "/api/dashboard/score-totals-by-severity",
        params={"start": "2026-05-01", "end": "2026-05-03"},
    )
    assert resp.status_code == 200
    points = resp.json()["points"]
    assert len(points) == 3
    for p in points:
        # Only owner_user's medium=10 risk counts; owner_user_b's critical=22 is hidden.
        assert p["medium"] == 10
        assert p["critical"] == 0


def _add_status_change(
    db, *, risk: Risk, old: str, new: str, changed_at: datetime, changed_by_id: int
) -> None:
    """Insert a RiskHistory status-change row at an explicit timestamp."""
    db.add(RiskHistory(
        risk_id=risk.id,
        field_changed="status",
        old_value=old,
        new_value=new,
        changed_by_id=changed_by_id,
        changed_at=changed_at,
    ))
    db.commit()


def test_score_totals_excludes_closed_risk_after_status_change(
    client, admin_user, login_as, db
):
    """A risk scored 16 on day 1 and closed on day 5 contributes 16 days 1-4 and 0 thereafter."""
    login_as(admin_user)
    day_1 = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
    day_5 = datetime(2026, 5, 5, 12, 0, tzinfo=timezone.utc)

    risk = _seed_risk_with_assessment(db, owner=admin_user, score=16, assessed_at=day_1)
    _add_status_change(
        db, risk=risk, old="open", new="closed", changed_at=day_5, changed_by_id=admin_user.id
    )
    risk.status = RiskStatus.closed
    db.commit()

    resp = client.get(
        "/api/dashboard/score-totals-by-severity",
        params={"start": "2026-05-01", "end": "2026-05-07"},
    )
    assert resp.status_code == 200
    points = resp.json()["points"]
    by_date = {p["date"]: p for p in points}
    for d in ("2026-05-01", "2026-05-02", "2026-05-03", "2026-05-04"):
        assert by_date[d]["high"] == 16
    for d in ("2026-05-05", "2026-05-06", "2026-05-07"):
        assert by_date[d]["high"] == 0
        assert by_date[d]["low"] == 0
        assert by_date[d]["medium"] == 0
        assert by_date[d]["critical"] == 0


def test_score_totals_excludes_mitigated_and_accepted(
    client, admin_user, login_as, db
):
    """Mitigated and accepted statuses also drop a risk's contribution."""
    login_as(admin_user)
    day_1 = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
    day_5 = datetime(2026, 5, 5, 12, 0, tzinfo=timezone.utc)

    risk_m = _seed_risk_with_assessment(db, owner=admin_user, score=16, assessed_at=day_1)
    _add_status_change(
        db, risk=risk_m, old="open", new="mitigated", changed_at=day_5, changed_by_id=admin_user.id
    )
    risk_m.status = RiskStatus.mitigated

    risk_a = _seed_risk_with_assessment(db, owner=admin_user, score=22, assessed_at=day_1)
    _add_status_change(
        db, risk=risk_a, old="open", new="accepted", changed_at=day_5, changed_by_id=admin_user.id
    )
    risk_a.status = RiskStatus.accepted
    db.commit()

    resp = client.get(
        "/api/dashboard/score-totals-by-severity",
        params={"start": "2026-05-01", "end": "2026-05-07"},
    )
    assert resp.status_code == 200
    by_date = {p["date"]: p for p in resp.json()["points"]}
    for d in ("2026-05-01", "2026-05-02", "2026-05-03", "2026-05-04"):
        assert by_date[d]["high"] == 16
        assert by_date[d]["critical"] == 22
    for d in ("2026-05-05", "2026-05-06", "2026-05-07"):
        assert by_date[d]["high"] == 0
        assert by_date[d]["critical"] == 0


def test_score_totals_excludes_risk_created_already_closed(
    client, admin_user, login_as, db
):
    """A risk created already-closed (no status history) contributes 0 throughout."""
    login_as(admin_user)
    day_1 = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
    risk = _seed_risk_with_assessment(db, owner=admin_user, score=16, assessed_at=day_1)
    risk.status = RiskStatus.closed
    db.commit()

    resp = client.get(
        "/api/dashboard/score-totals-by-severity",
        params={"start": "2026-05-01", "end": "2026-05-07"},
    )
    assert resp.status_code == 200
    for p in resp.json()["points"]:
        assert p["low"] == 0
        assert p["medium"] == 0
        assert p["high"] == 0
        assert p["critical"] == 0


def test_score_totals_includes_risk_reopened_from_closed(
    client, admin_user, login_as, db
):
    """Open day 1, closed day 5, reopened day 10: contributes days 1-4 and 10+, zero in between."""
    login_as(admin_user)
    day_1 = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
    day_5 = datetime(2026, 5, 5, 12, 0, tzinfo=timezone.utc)
    day_10 = datetime(2026, 5, 10, 12, 0, tzinfo=timezone.utc)

    risk = _seed_risk_with_assessment(db, owner=admin_user, score=16, assessed_at=day_1)
    _add_status_change(
        db, risk=risk, old="open", new="closed", changed_at=day_5, changed_by_id=admin_user.id
    )
    _add_status_change(
        db, risk=risk, old="closed", new="open", changed_at=day_10, changed_by_id=admin_user.id
    )
    risk.status = RiskStatus.open
    db.commit()

    resp = client.get(
        "/api/dashboard/score-totals-by-severity",
        params={"start": "2026-05-01", "end": "2026-05-12"},
    )
    assert resp.status_code == 200
    by_date = {p["date"]: p for p in resp.json()["points"]}
    for d in ("2026-05-01", "2026-05-02", "2026-05-03", "2026-05-04"):
        assert by_date[d]["high"] == 16
    for d in ("2026-05-05", "2026-05-06", "2026-05-07", "2026-05-08", "2026-05-09"):
        assert by_date[d]["high"] == 0
    for d in ("2026-05-10", "2026-05-11", "2026-05-12"):
        assert by_date[d]["high"] == 16


# --- Role-based scoping (risk_owner) ------------------------------------------


def _seed_owner_dataset(db, *, owner_a, owner_b):
    """Seed 2 risks for owner_a and 3 risks for owner_b, each with one assessment.

    Owner_a gets one risk with an overdue review and one risk with an overdue
    RiskResponse so we can verify both overdue counters scope correctly.
    Owner_b gets parallel-but-different data so isolation is observable.

    All assessments are dated 2026-05-10 so a single date-range covers both.
    """
    assessed_at = datetime(2026, 5, 10, 12, 0, tzinfo=timezone.utc)
    today = date.today()

    # Owner A — 2 risks. One overdue review, one with an overdue RiskResponse.
    a_overdue_review = _seed_risk_with_assessment(
        db, owner=owner_a, score=8, assessed_at=assessed_at
    )
    a_overdue_review.next_review_date = today - timedelta(days=2)
    a_overdue_review.status = RiskStatus.open
    db.commit()

    a_overdue_response_risk = _seed_risk_with_assessment(
        db, owner=owner_a, score=15, assessed_at=assessed_at
    )
    db.add(RiskResponse(
        risk_id=a_overdue_response_risk.id,
        response_type=ResponseType.mitigate,
        mitigation_strategy="A — overdue",
        target_date=today - timedelta(days=3),
        status=ResponseStatus.in_progress,
    ))
    db.commit()

    # Owner B — 3 risks. Different overdue review count + different responses.
    b_risks = [
        _seed_risk_with_assessment(db, owner=owner_b, score=4, assessed_at=assessed_at),
        _seed_risk_with_assessment(db, owner=owner_b, score=10, assessed_at=assessed_at),
        _seed_risk_with_assessment(db, owner=owner_b, score=22, assessed_at=assessed_at),
    ]
    # Two overdue reviews for B (different number from A).
    for r in b_risks[:2]:
        r.next_review_date = today - timedelta(days=1)
        r.status = RiskStatus.open
    db.commit()
    # And one overdue response for B (different risk).
    db.add(RiskResponse(
        risk_id=b_risks[2].id,
        response_type=ResponseType.mitigate,
        mitigation_strategy="B — overdue",
        target_date=today - timedelta(days=5),
        status=ResponseStatus.planned,
    ))
    # And one completed (NOT overdue) response on owner A's data to verify the
    # status filter still excludes completed regardless of scope.
    db.add(RiskResponse(
        risk_id=a_overdue_response_risk.id,
        response_type=ResponseType.mitigate,
        mitigation_strategy="A — completed",
        target_date=today - timedelta(days=10),
        status=ResponseStatus.completed,
    ))
    db.commit()


def test_summary_scoped_to_risk_owner_a(client, owner_user, owner_user_b, login_as, db):
    _seed_owner_dataset(db, owner_a=owner_user, owner_b=owner_user_b)
    login_as(owner_user)
    resp = client.get("/api/dashboard/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    # Owner A's matrix sums equal owner A's risk count.
    matrix_sum = sum(sum(row) for row in body["risk_matrix"])
    assert matrix_sum == 2
    # Severity buckets sum to 2 as well (no unscored risks for A).
    assert sum(body["by_severity"].values()) == 2
    assert body["by_severity"]["Unscored"] == 0
    # Exactly one overdue review and one overdue response for owner A.
    assert body["overdue_reviews"] == 1
    assert body["overdue_responses"] == 1


def test_summary_scoped_to_risk_owner_b(client, owner_user, owner_user_b, login_as, db):
    _seed_owner_dataset(db, owner_a=owner_user, owner_b=owner_user_b)
    login_as(owner_user_b)
    resp = client.get("/api/dashboard/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    matrix_sum = sum(sum(row) for row in body["risk_matrix"])
    assert matrix_sum == 3
    assert sum(body["by_severity"].values()) == 3
    assert body["by_severity"]["Unscored"] == 0
    assert body["overdue_reviews"] == 2
    assert body["overdue_responses"] == 1


def test_summary_admin_sees_everyones_risks(
    client, admin_user, owner_user, owner_user_b, login_as, db
):
    _seed_owner_dataset(db, owner_a=owner_user, owner_b=owner_user_b)
    login_as(admin_user)
    resp = client.get("/api/dashboard/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 5  # 2 + 3
    matrix_sum = sum(sum(row) for row in body["risk_matrix"])
    assert matrix_sum == 5
    assert body["overdue_reviews"] == 3   # 1 (A) + 2 (B)
    assert body["overdue_responses"] == 2  # 1 (A) + 1 (B)


def test_summary_analyst_sees_everyones_risks(
    client, analyst_user, owner_user, owner_user_b, login_as, db
):
    _seed_owner_dataset(db, owner_a=owner_user, owner_b=owner_user_b)
    login_as(analyst_user)
    resp = client.get("/api/dashboard/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 5


def test_score_history_scoped_by_role(
    client, admin_user, owner_user, owner_user_b, login_as, db
):
    _seed_owner_dataset(db, owner_a=owner_user, owner_b=owner_user_b)
    params = {"start": "2026-05-01", "end": "2026-05-31"}

    login_as(owner_user)
    resp = client.get("/api/dashboard/score-history", params=params)
    assert resp.status_code == 200
    points = resp.json()["points"]
    assert len(points) == 1
    assert points[0]["count"] == 2  # owner A's 2 assessments

    login_as(owner_user_b)
    resp = client.get("/api/dashboard/score-history", params=params)
    assert resp.status_code == 200
    points = resp.json()["points"]
    assert len(points) == 1
    assert points[0]["count"] == 3  # owner B's 3 assessments

    login_as(admin_user)
    resp = client.get("/api/dashboard/score-history", params=params)
    assert resp.status_code == 200
    points = resp.json()["points"]
    assert len(points) == 1
    assert points[0]["count"] == 5  # all assessments


def test_score_totals_by_severity_scoped_by_role(
    client, admin_user, owner_user, owner_user_b, login_as, db
):
    """The seeded dataset puts all assessments on 5/10. The window starts on
    5/1, so days 5/1-5/9 should be all-zero, and days 5/10-5/31 should reflect
    the cumulative scope-appropriate totals.
    """
    _seed_owner_dataset(db, owner_a=owner_user, owner_b=owner_user_b)
    params = {"start": "2026-05-01", "end": "2026-05-31"}

    def _by_date(points):
        return {p["date"]: p for p in points}

    # Owner A: scores 8 (medium) + 15 (high)
    login_as(owner_user)
    resp = client.get("/api/dashboard/score-totals-by-severity", params=params)
    assert resp.status_code == 200
    points = resp.json()["points"]
    assert len(points) == 31
    by_date = _by_date(points)
    # Pre-assessment days are all zero.
    assert by_date["2026-05-01"] == {
        "date": "2026-05-01", "low": 0, "medium": 0, "high": 0, "critical": 0
    }
    # Post-assessment days carry owner A's medium=8 + high=15.
    p = by_date["2026-05-10"]
    assert p["low"] == 0
    assert p["medium"] == 8
    assert p["high"] == 15
    assert p["critical"] == 0
    assert by_date["2026-05-31"]["high"] == 15

    # Owner B: scores 4 (low) + 10 (medium) + 22 (critical)
    login_as(owner_user_b)
    resp = client.get("/api/dashboard/score-totals-by-severity", params=params)
    assert resp.status_code == 200
    points = resp.json()["points"]
    assert len(points) == 31
    by_date = _by_date(points)
    assert by_date["2026-05-09"]["medium"] == 0
    p = by_date["2026-05-10"]
    assert p["low"] == 4
    assert p["medium"] == 10
    assert p["high"] == 0
    assert p["critical"] == 22

    # Admin: sum of everything
    login_as(admin_user)
    resp = client.get("/api/dashboard/score-totals-by-severity", params=params)
    assert resp.status_code == 200
    points = resp.json()["points"]
    assert len(points) == 31
    by_date = _by_date(points)
    p = by_date["2026-05-10"]
    assert p["low"] == 4
    assert p["medium"] == 18  # 8 + 10
    assert p["high"] == 15
    assert p["critical"] == 22


# --- /action-queue -------------------------------------------------------------


def _add_overdue_review(db, *, owner, days_overdue: int, status: RiskStatus = RiskStatus.open) -> Risk:
    _seed_counter["n"] += 1
    risk = Risk(
        risk_id=f"RISK-{_seed_counter['n']:04d}",
        title=f"Review-{_seed_counter['n']}",
        owner_id=owner.id,
        created_by_id=owner.id,
        status=status,
        next_review_date=date.today() - timedelta(days=days_overdue),
    )
    db.add(risk)
    db.commit()
    db.refresh(risk)
    return risk


def _add_response_for_risk(
    db, *, risk: Risk, days_overdue: int, status: ResponseStatus = ResponseStatus.planned
) -> RiskResponse:
    resp = RiskResponse(
        risk_id=risk.id,
        response_type=ResponseType.mitigate,
        mitigation_strategy="m",
        target_date=date.today() - timedelta(days=days_overdue),
        status=status,
    )
    db.add(resp)
    db.commit()
    db.refresh(resp)
    return resp


def test_action_queue_empty_state(client, admin_user, login_as):
    login_as(admin_user)
    resp = client.get("/api/dashboard/action-queue")
    assert resp.status_code == 200
    assert resp.json() == {"items": [], "total": 0}


def test_action_queue_overdue_review_surfaces(client, admin_user, login_as, db):
    risk = _add_overdue_review(db, owner=admin_user, days_overdue=3)
    login_as(admin_user)
    resp = client.get("/api/dashboard/action-queue")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    item = items[0]
    assert item["kind"] == "review"
    assert item["risk_id"] == risk.risk_id
    assert item["risk_title"] == risk.title
    assert item["days_overdue"] == 3
    assert item["due_date"] == (date.today() - timedelta(days=3)).isoformat()


def test_action_queue_overdue_response_surfaces(client, admin_user, login_as, db):
    _seed_counter["n"] += 1
    risk = Risk(
        risk_id=f"RISK-{_seed_counter['n']:04d}",
        title=f"WithResponse-{_seed_counter['n']}",
        owner_id=admin_user.id,
        created_by_id=admin_user.id,
        status=RiskStatus.open,
    )
    db.add(risk)
    db.commit()
    db.refresh(risk)
    _add_response_for_risk(db, risk=risk, days_overdue=5, status=ResponseStatus.planned)
    login_as(admin_user)
    resp = client.get("/api/dashboard/action-queue")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    item = items[0]
    assert item["kind"] == "response"
    assert item["risk_id"] == risk.risk_id
    assert item["risk_title"] == risk.title
    assert item["days_overdue"] == 5
    assert item["due_date"] == (date.today() - timedelta(days=5)).isoformat()


def test_action_queue_excludes_closed_and_mitigated_reviews(
    client, admin_user, login_as, db
):
    _add_overdue_review(db, owner=admin_user, days_overdue=2, status=RiskStatus.closed)
    _add_overdue_review(db, owner=admin_user, days_overdue=2, status=RiskStatus.mitigated)
    open_risk = _add_overdue_review(
        db, owner=admin_user, days_overdue=2, status=RiskStatus.open
    )
    login_as(admin_user)
    resp = client.get("/api/dashboard/action-queue")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["risk_id"] == open_risk.risk_id


def test_action_queue_excludes_completed_responses(client, admin_user, login_as, db):
    _seed_counter["n"] += 1
    risk = Risk(
        risk_id=f"RISK-{_seed_counter['n']:04d}",
        title=f"R-{_seed_counter['n']}",
        owner_id=admin_user.id,
        created_by_id=admin_user.id,
        status=RiskStatus.open,
    )
    db.add(risk)
    db.commit()
    db.refresh(risk)
    _add_response_for_risk(db, risk=risk, days_overdue=4, status=ResponseStatus.completed)
    login_as(admin_user)
    resp = client.get("/api/dashboard/action-queue")
    assert resp.status_code == 200
    assert resp.json() == {"items": [], "total": 0}


def test_action_queue_scoped_to_risk_owner(
    client, owner_user, owner_user_b, login_as, db
):
    own = _add_overdue_review(db, owner=owner_user, days_overdue=2)
    _add_overdue_review(db, owner=owner_user_b, days_overdue=4)

    login_as(owner_user)
    resp = client.get("/api/dashboard/action-queue")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["risk_id"] == own.risk_id


def test_action_queue_admin_sees_everyone(
    client, admin_user, owner_user, owner_user_b, login_as, db
):
    _add_overdue_review(db, owner=owner_user, days_overdue=2)
    _add_overdue_review(db, owner=owner_user_b, days_overdue=4)

    login_as(admin_user)
    resp = client.get("/api/dashboard/action-queue")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 2


def test_action_queue_analyst_sees_everyone(
    client, analyst_user, owner_user, owner_user_b, login_as, db
):
    _add_overdue_review(db, owner=owner_user, days_overdue=2)
    _add_overdue_review(db, owner=owner_user_b, days_overdue=4)

    login_as(analyst_user)
    resp = client.get("/api/dashboard/action-queue")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 2


def test_action_queue_orders_most_overdue_first(client, admin_user, login_as, db):
    _add_overdue_review(db, owner=admin_user, days_overdue=1)
    _add_overdue_review(db, owner=admin_user, days_overdue=10)
    _add_overdue_review(db, owner=admin_user, days_overdue=5)

    login_as(admin_user)
    resp = client.get("/api/dashboard/action-queue")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert [i["days_overdue"] for i in items] == [10, 5, 1]


def test_action_queue_unauthenticated_returns_401(client):
    resp = client.get("/api/dashboard/action-queue")
    assert resp.status_code == 401


def test_action_queue_returns_total_count(client, admin_user, login_as, db):
    for days in (1, 3, 5, 7):
        _add_overdue_review(db, owner=admin_user, days_overdue=days)
    login_as(admin_user)
    resp = client.get("/api/dashboard/action-queue", params={"limit": 50})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 4
    assert len(body["items"]) == 4
    assert body["total"] == len(body["items"])


def test_action_queue_respects_limit_query_param(client, admin_user, login_as, db):
    for days in (1, 2, 3, 4, 5, 6, 7):
        _add_overdue_review(db, owner=admin_user, days_overdue=days)
    login_as(admin_user)
    resp = client.get("/api/dashboard/action-queue", params={"limit": 3})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) == 3
    assert body["total"] == 7
    assert body["total"] > 3
    assert [i["days_overdue"] for i in body["items"]] == [7, 6, 5]
