"""Integration tests for /api/dashboard."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from app.models.risk import (
    Risk,
    RiskAssessment,
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
    resp = client.get(
        "/api/dashboard/score-totals-by-severity",
        params={"start": "2026-01-01", "end": "2026-12-31"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"points": []}


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


def test_score_totals_by_severity_multiple_days_sorted(
    client, admin_user, login_as, db
):
    login_as(admin_user)
    day_a = datetime(2026, 5, 1, 9, 0, tzinfo=timezone.utc)
    day_b = datetime(2026, 5, 3, 9, 0, tzinfo=timezone.utc)
    _seed_risk_with_assessment(db, owner=admin_user, score=4, assessed_at=day_b)
    _seed_risk_with_assessment(db, owner=admin_user, score=10, assessed_at=day_a)
    _seed_risk_with_assessment(db, owner=admin_user, score=22, assessed_at=day_b)

    resp = client.get(
        "/api/dashboard/score-totals-by-severity",
        params={"start": "2026-05-01", "end": "2026-05-31"},
    )
    assert resp.status_code == 200
    points = resp.json()["points"]
    assert len(points) == 2
    assert points[0]["date"] == "2026-05-01"
    assert points[1]["date"] == "2026-05-03"
    # Day A: only score 10 (medium)
    assert points[0]["low"] == 0
    assert points[0]["medium"] == 10
    assert points[0]["high"] == 0
    assert points[0]["critical"] == 0
    # Day B: 4 (low) + 22 (critical)
    assert points[1]["low"] == 4
    assert points[1]["medium"] == 0
    assert points[1]["high"] == 0
    assert points[1]["critical"] == 22


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


def test_score_totals_by_severity_filters_by_date_range(
    client, admin_user, login_as, db
):
    login_as(admin_user)
    in_range = datetime(2026, 5, 10, 12, 0, tzinfo=timezone.utc)
    before = datetime(2026, 4, 30, 12, 0, tzinfo=timezone.utc)
    after = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    _seed_risk_with_assessment(db, owner=admin_user, score=9, assessed_at=in_range)
    _seed_risk_with_assessment(db, owner=admin_user, score=9, assessed_at=before)
    _seed_risk_with_assessment(db, owner=admin_user, score=9, assessed_at=after)

    resp = client.get(
        "/api/dashboard/score-totals-by-severity",
        params={"start": "2026-05-01", "end": "2026-05-31"},
    )
    assert resp.status_code == 200
    points = resp.json()["points"]
    assert len(points) == 1
    assert points[0]["date"] == "2026-05-10"
    assert points[0]["medium"] == 9


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
    _seed_owner_dataset(db, owner_a=owner_user, owner_b=owner_user_b)
    params = {"start": "2026-05-01", "end": "2026-05-31"}

    # Owner A: scores 8 (medium) + 15 (high)
    login_as(owner_user)
    resp = client.get("/api/dashboard/score-totals-by-severity", params=params)
    assert resp.status_code == 200
    points = resp.json()["points"]
    assert len(points) == 1
    p = points[0]
    assert p["low"] == 0
    assert p["medium"] == 8
    assert p["high"] == 15
    assert p["critical"] == 0

    # Owner B: scores 4 (low) + 10 (medium) + 22 (critical)
    login_as(owner_user_b)
    resp = client.get("/api/dashboard/score-totals-by-severity", params=params)
    assert resp.status_code == 200
    points = resp.json()["points"]
    assert len(points) == 1
    p = points[0]
    assert p["low"] == 4
    assert p["medium"] == 10
    assert p["high"] == 0
    assert p["critical"] == 22

    # Admin: sum of everything
    login_as(admin_user)
    resp = client.get("/api/dashboard/score-totals-by-severity", params=params)
    assert resp.status_code == 200
    points = resp.json()["points"]
    assert len(points) == 1
    p = points[0]
    assert p["low"] == 4
    assert p["medium"] == 18  # 8 + 10
    assert p["high"] == 15
    assert p["critical"] == 22
