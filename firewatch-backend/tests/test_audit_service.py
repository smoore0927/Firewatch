"""Unit tests for the record_event helper in app/services/audit_service.py."""

from __future__ import annotations

import json

import pytest
from starlette.requests import Request

from app.models.audit_log import AuditLog
from app.services import audit_service
from app.services.audit_service import record_event


def _make_request(*, ip: str = "1.2.3.4", ua: bytes = b"my-ua/1.0") -> Request:
    """Build a minimal Starlette Request with a client tuple and user-agent header."""
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(b"user-agent", ua)],
        "client": (ip, 1234),
    }
    return Request(scope)


def test_record_event_writes_row_with_minimal_args(db):
    record_event(db, action="x")
    db.commit()

    rows = db.query(AuditLog).all()
    assert len(rows) == 1
    assert rows[0].action == "x"


def test_record_event_snapshots_user_email_from_user(db, existing_local_user):
    record_event(db, action="auth.test", user=existing_local_user)
    db.commit()

    row = db.query(AuditLog).first()
    assert row is not None
    assert row.user_id == existing_local_user.id
    assert row.user_email == existing_local_user.email


def test_record_event_does_not_commit(db):
    record_event(db, action="staged")

    # The row is staged on the session but not committed: SQLAlchemy tracks it in `db.new`.
    pending_actions = {obj.action for obj in db.new if isinstance(obj, AuditLog)}
    assert "staged" in pending_actions
    # No row is queryable yet without an explicit commit (autoflush is off in conftest).
    assert db.query(AuditLog).count() == 0

    db.commit()
    assert db.query(AuditLog).count() == 1


def test_record_event_serializes_details_as_json_string(db):
    payload = {"a": 1, "b": [2, 3], "nested": {"k": "v"}}
    record_event(db, action="x", details=payload)
    db.commit()

    row = db.query(AuditLog).first()
    assert isinstance(row.details, str)
    assert json.loads(row.details) == payload


def test_record_event_extracts_request_metadata(db):
    request = _make_request(ip="1.2.3.4", ua=b"my-ua/1.0")
    record_event(db, action="x", request=request)
    db.commit()

    row = db.query(AuditLog).first()
    assert row.ip_address == "1.2.3.4"
    assert row.user_agent == "my-ua/1.0"


def test_record_event_truncates_long_user_agent(db):
    long_ua = ("A" * 1000).encode()
    request = _make_request(ua=long_ua)
    record_event(db, action="x", request=request)
    db.commit()

    row = db.query(AuditLog).first()
    assert row.user_agent is not None
    assert len(row.user_agent) <= 500
    assert len(row.user_agent) == 500  # exact: implementation slices [:500]


def test_record_event_swallows_internal_exception(db, monkeypatch):
    """If serialization (or any other inner step) raises, the call must return cleanly."""

    def boom(*_args, **_kwargs):
        raise RuntimeError("deliberate failure")

    monkeypatch.setattr(audit_service.json, "dumps", boom)

    # Must not raise even though json.dumps blows up while building the row.
    record_event(db, action="x", details={"will": "explode"})
    db.commit()

    # Either no row was added, or any partially-built row didn't make it past the exception.
    # The contract is "swallow + log" — what matters is that the call returns
    # and the session is not left poisoned for subsequent writes.
    record_event(db, action="after", details=None)  # details=None bypasses json.dumps
    db.commit()
    actions = {row.action for row in db.query(AuditLog).all()}
    assert "after" in actions
