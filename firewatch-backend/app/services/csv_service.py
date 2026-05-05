"""
CSV serialization helpers for risks export/import.

Keep route handlers thin: routes call risks_to_csv() to render an export
or parse_risks_csv() to validate uploaded rows. DB-side concerns (creating
the risks, resolving owner emails) stay in the route + RiskService.
"""

import csv
import io
from datetime import date, datetime
from typing import Iterable

from app.models.risk import Risk
from app.schemas.risk import RiskCreate


EXPORT_COLUMNS = [
    "risk_id",
    "title",
    "description",
    "threat_source",
    "threat_event",
    "vulnerability",
    "affected_asset",
    "category",
    "status",
    "owner_email",
    "likelihood",
    "impact",
    "risk_score",
    "review_frequency_days",
    "next_review_date",
    "created_at",
]

IMPORT_COLUMNS = [
    "title",
    "description",
    "threat_source",
    "threat_event",
    "vulnerability",
    "affected_asset",
    "category",
    "owner_email",
    "likelihood",
    "impact",
    "review_frequency_days",
    "next_review_date",
]

IMPORT_TEMPLATE_EXAMPLE = [
    "Phishing attack on finance team",
    "Targeted phishing emails attempting to harvest credentials from finance staff.",
    "External adversary",
    "Phishing email",
    "No MFA on admin accounts",
    "Customer PII database",
    "Technical",
    "admin@example.com",
    "4",
    "3",
    "90",
    "2026-08-01",
]


def _fmt_date(value: date | None) -> str:
    return value.isoformat() if value else ""


def _fmt_datetime(value: datetime | None) -> str:
    return value.isoformat() if value else ""


def risks_to_csv(risks: Iterable[Risk]) -> str:
    """Serialize risks to a CSV string with EXPORT_COLUMNS."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(EXPORT_COLUMNS)
    for risk in risks:
        latest = risk.assessments[0] if risk.assessments else None
        owner_email = risk.owner.email if risk.owner else ""
        writer.writerow([
            risk.risk_id,
            risk.title or "",
            risk.description or "",
            risk.threat_source or "",
            risk.threat_event or "",
            risk.vulnerability or "",
            risk.affected_asset or "",
            risk.category or "",
            risk.status.value if risk.status else "",
            owner_email,
            latest.likelihood if latest else "",
            latest.impact if latest else "",
            latest.risk_score if latest else "",
            risk.review_frequency_days if risk.review_frequency_days is not None else "",
            _fmt_date(risk.next_review_date),
            _fmt_datetime(risk.created_at),
        ])
    return buf.getvalue()


def import_template_csv() -> str:
    """Return a CSV with the import header plus one example row."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(IMPORT_COLUMNS)
    writer.writerow(IMPORT_TEMPLATE_EXAMPLE)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Import parsing
# ---------------------------------------------------------------------------

ParsedRow = tuple[int, RiskCreate | None, str | None, str | None]
# (row_number, RiskCreate-or-None, owner_email-or-None, error-or-None)


def _clean(value: str | None) -> str | None:
    """Strip whitespace; treat empty strings as None."""
    if value is None:
        return None
    stripped = value.strip()
    return stripped if stripped else None


def _parse_score(raw: str | None, field_name: str) -> int:
    try:
        n = int(raw)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be an integer 1-5")
    if n < 1 or n > 5:
        raise ValueError(f"{field_name} must be between 1 and 5")
    return n


def parse_risks_csv(content: str) -> list[ParsedRow]:
    """
    Validate every row's structural fields (without DB lookup).
    Returns one tuple per non-blank data row. Owner email resolution
    happens in the route, where the DB session is available.
    """
    reader = csv.DictReader(io.StringIO(content))
    results: list[ParsedRow] = []
    row_number = 0

    for raw_row in reader:
        row_number += 1
        # Skip rows where every cell is blank/whitespace
        if not any((v or "").strip() for v in raw_row.values()):
            continue

        try:
            row = {k: _clean(v) for k, v in raw_row.items()}

            title = row.get("title")
            if not title:
                raise ValueError("title is required")

            likelihood_raw = row.get("likelihood")
            impact_raw = row.get("impact")
            if (likelihood_raw is None) != (impact_raw is None):
                raise ValueError(
                    "likelihood and impact must both be provided or both omitted"
                )

            likelihood: int | None = None
            impact: int | None = None
            if likelihood_raw is not None:
                likelihood = _parse_score(likelihood_raw, "likelihood")
                impact = _parse_score(impact_raw, "impact")

            review_frequency_days: int | None = None
            freq_raw = row.get("review_frequency_days")
            if freq_raw is not None:
                try:
                    review_frequency_days = int(freq_raw)
                except ValueError:
                    raise ValueError("review_frequency_days must be an integer")
                if review_frequency_days < 1:
                    raise ValueError("review_frequency_days must be >= 1")

            next_review_date: date | None = None
            nrd_raw = row.get("next_review_date")
            if nrd_raw is not None:
                try:
                    next_review_date = date.fromisoformat(nrd_raw)
                except ValueError:
                    raise ValueError("next_review_date must be ISO date YYYY-MM-DD")

            risk_create = RiskCreate(
                title=title,
                description=row.get("description"),
                threat_source=row.get("threat_source"),
                threat_event=row.get("threat_event"),
                vulnerability=row.get("vulnerability"),
                affected_asset=row.get("affected_asset"),
                category=row.get("category"),
                review_frequency_days=review_frequency_days,
                next_review_date=next_review_date,
                likelihood=likelihood,
                impact=impact,
            )
            results.append((row_number, risk_create, row.get("owner_email"), None))
        except ValueError as exc:
            results.append((row_number, None, None, str(exc)))
        except Exception as exc:
            results.append((row_number, None, None, f"invalid row: {exc}"))

    return results
