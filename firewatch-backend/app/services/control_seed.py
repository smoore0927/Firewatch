"""Idempotent seed for control frameworks + their controls.

Loads vendored framework files via the importer (upsert), so it is safe to call
every startup and never duplicates. Called at startup (lifespan) and runnable:
  python -m app.services.control_seed
"""

import logging

from sqlalchemy.orm import Session

from app.models.control import DeletedFrameworkSeed
from app.services.control_import import (
    DATA_DIR,
    VENDORED_FRAMEWORKS,
    detect_and_parse,
    import_framework,
)

logger = logging.getLogger(__name__)


def seed_control_frameworks(db: Session) -> None:
    """Upsert the vendored frameworks/controls from app/data/frameworks."""
    total_created = 0
    total_updated = 0
    tombstoned = {row.name for row in db.query(DeletedFrameworkSeed).all()}
    for filename, name, version, description in VENDORED_FRAMEWORKS:
        if name in tombstoned:
            logger.info("Skipping tombstoned framework: %s", name)
            continue
        path = DATA_DIR / filename
        if not path.exists():
            logger.warning("Vendored framework file missing: %s", path)
            continue
        parsed = detect_and_parse(path.read_text(encoding="utf-8-sig"))
        result = import_framework(
            db,
            parsed,
            framework_name=name,
            version=version,
            description=description,
        )
        total_created += result["created"]
        total_updated += result["updated"]
    db.commit()
    logger.info(
        "Seeded control frameworks: %d created, %d updated", total_created, total_updated
    )


if __name__ == "__main__":
    from app.models.database import SessionLocal

    session = SessionLocal()
    try:
        seed_control_frameworks(session)
        print("Control framework seed complete.")
    finally:
        session.close()
