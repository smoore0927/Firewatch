"""Control framework importer — parses CSV / OSCAL-JSON and upserts idempotently.

Normalized parse result:
  ParsedFramework(framework_name, version, controls=[ParsedControl(...)])

Used by:
  - seed_control_frameworks (startup, vendored files)
  - POST /frameworks/import        (file upload)
  - POST /frameworks/import-from-url
"""

from __future__ import annotations

import csv
import io
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.control import Control, ControlFramework, DeletedFrameworkSeed

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "frameworks"

MAX_OSCAL_GROUP_DEPTH = 64  # real OSCAL catalogs nest only a few levels

# Vendored files loaded at startup: (path, framework_name, version, description)
VENDORED_FRAMEWORKS = [
    (
        "nist_800_53_rev5.csv",
        "NIST 800-53 Rev 5",
        "Rev 5",
        "NIST Special Publication 800-53 security and privacy controls.",
    ),
    (
        "nist_csf_2_0.csv",
        "NIST CSF 2.0",
        "2.0",
        "NIST Cybersecurity Framework 2.0 subcategories.",
    ),
]


@dataclass
class ParsedControl:
    control_id: str
    title: str
    family: str | None = None
    description: str | None = None


@dataclass
class ParsedFramework:
    framework_name: str | None
    version: str | None
    controls: list[ParsedControl] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_csv(text: str) -> ParsedFramework:
    """Parse a control CSV with headers control_id,family,title,description."""
    reader = csv.DictReader(io.StringIO(text), restkey="_overflow")
    fields = {(h or "").strip().lower() for h in (reader.fieldnames or [])}
    required = {"control_id", "title"}
    if not required.issubset(fields):
        raise ValueError("CSV must contain at least 'control_id' and 'title' columns")

    controls: list[ParsedControl] = []
    for row in reader:
        # An unquoted comma in the final column spills into restkey — fold it back.
        overflow = row.pop("_overflow", None)
        if overflow:
            row["description"] = ",".join(
                p for p in [row.get("description")] + list(overflow) if p
            )
        norm = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        control_id = norm.get("control_id", "")
        title = norm.get("title", "")
        if not control_id or not title:
            continue
        controls.append(ParsedControl(
            control_id=control_id,
            title=title,
            family=norm.get("family") or None,
            description=norm.get("description") or None,
        ))
    return ParsedFramework(framework_name=None, version=None, controls=controls)


def parse_oscal_json(text: str) -> ParsedFramework:
    """Parse a NIST OSCAL catalog JSON into a normalized framework."""
    doc = json.loads(text)
    catalog = doc.get("catalog", doc)
    metadata = catalog.get("metadata", {})
    framework_name = metadata.get("title")
    version = metadata.get("version")

    controls: list[ParsedControl] = []

    def prop(obj: dict, name: str) -> str | None:
        for p in obj.get("props", []):
            if p.get("name") == name:
                return p.get("value")
        return None

    def part_prose(obj: dict, part_name: str) -> str | None:
        for part in obj.get("parts", []):
            if part.get("name") == part_name and part.get("prose"):
                return part["prose"]
        return None

    def walk(group: dict, family: str | None, depth: int = 0) -> None:
        if depth > MAX_OSCAL_GROUP_DEPTH:
            raise ValueError("OSCAL group nesting too deep")
        fam = group.get("title") or family
        for ctrl in group.get("controls", []):
            cid = prop(ctrl, "label") or ctrl.get("id", "").upper()
            title = ctrl.get("title", "")
            if cid and title:
                controls.append(ParsedControl(
                    control_id=cid,
                    title=title,
                    family=fam,
                    description=part_prose(ctrl, "statement"),
                ))
            # Nested control enhancements.
            for sub in ctrl.get("controls", []):
                scid = prop(sub, "label") or sub.get("id", "").upper()
                if scid and sub.get("title"):
                    controls.append(ParsedControl(
                        control_id=scid,
                        title=sub.get("title", ""),
                        family=fam,
                        description=part_prose(sub, "statement"),
                    ))
        for child in group.get("groups", []):
            walk(child, fam, depth + 1)

    for grp in catalog.get("groups", []):
        walk(grp, None)
    for ctrl in catalog.get("controls", []):  # controls at catalog root
        cid = prop(ctrl, "label") or ctrl.get("id", "").upper()
        if cid and ctrl.get("title"):
            controls.append(ParsedControl(
                control_id=cid,
                title=ctrl.get("title", ""),
                family=None,
                description=part_prose(ctrl, "statement"),
            ))

    return ParsedFramework(framework_name=framework_name, version=version, controls=controls)


def detect_and_parse(data: str | bytes) -> ParsedFramework:
    """Detect CSV vs OSCAL-JSON from content and parse to a normalized framework."""
    text = data.decode("utf-8-sig", errors="replace") if isinstance(data, bytes) else data
    stripped = text.lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        return parse_oscal_json(text)
    return parse_csv(text)


# ---------------------------------------------------------------------------
# Upsert
# ---------------------------------------------------------------------------

def import_framework(
    db: Session,
    parsed: ParsedFramework,
    *,
    framework_name: str | None = None,
    version: str | None = None,
    description: str | None = None,
    source_url: str | None = None,
) -> dict:
    """Upsert a framework and its controls by (framework_name, control_id).

    Inserts new controls, updates changed title/family/description, never
    duplicates, and leaves risk_controls mappings untouched. Does not commit.
    """
    name = framework_name or parsed.framework_name
    if not name:
        raise ValueError("framework name is required (none in file and none provided)")
    ver = version or parsed.version

    # Re-importing un-deletes a previously-deleted seeded framework of the same name.
    db.query(DeletedFrameworkSeed).filter(DeletedFrameworkSeed.name == name).delete()

    framework = db.query(ControlFramework).filter(ControlFramework.name == name).first()
    if framework is None:
        framework = ControlFramework(name=name, version=ver, description=description)
        db.add(framework)
        db.flush()
    else:
        if ver is not None:
            framework.version = ver
        if description is not None:
            framework.description = description
    if source_url is not None and hasattr(framework, "source_url"):
        framework.source_url = source_url
    if hasattr(framework, "last_imported_at"):
        framework.last_imported_at = datetime.now(timezone.utc)

    existing = {
        c.control_id: c
        for c in db.query(Control).filter(Control.framework_id == framework.id).all()
    }

    created = 0
    updated = 0
    for pc in parsed.controls:
        current = existing.get(pc.control_id)
        if current is None:
            db.add(Control(
                framework_id=framework.id,
                control_id=pc.control_id,
                title=pc.title,
                family=pc.family,
                description=pc.description,
            ))
            created += 1
        else:
            changed = False
            if current.title != pc.title:
                current.title = pc.title
                changed = True
            if current.family != pc.family:
                current.family = pc.family
                changed = True
            if current.description != pc.description:
                current.description = pc.description
                changed = True
            if changed:
                updated += 1

    return {"framework_name": name, "version": ver, "created": created, "updated": updated}
