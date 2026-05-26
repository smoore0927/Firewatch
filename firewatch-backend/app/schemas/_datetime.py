"""Shared UTC-aware datetime serializer used by every response schema.

SQLite (dev DB) silently strips tzinfo from `DateTime(timezone=True)` columns,
so values come back as naive datetimes even though they were stored as UTC.
Pydantic v2 then serializes those as `"2026-05-26T03:00:00"` with no offset,
which JavaScript's `new Date(...)` interprets as LOCAL time — causing the
"one day off" bug on the frontend.

Every response-schema `datetime` field uses `serialize_utc_datetime` via a
`@field_serializer` so the wire format always carries an explicit `+00:00`.
"""

from datetime import datetime, timezone


def serialize_utc_datetime(dt: datetime | None) -> str | None:
    """Serialize a datetime as a UTC ISO 8601 string with explicit offset.

    Treats naive datetimes as UTC. SQLite drops tzinfo even with
    DateTime(timezone=True), so this guards against that ambiguity.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat()
