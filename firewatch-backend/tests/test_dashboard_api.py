"""Integration tests for /api/dashboard."""

from __future__ import annotations

from datetime import date, timedelta


def _create_risk(client, **overrides) -> dict:
    payload = {"title": "Default", "likelihood": 3, "impact": 3}
    payload.update(overrides)
    resp = client.post("/api/risks", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


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
    assert body["overdue_treatments"] == 0
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
    today = date.today().isoformat()
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
