"""Internal ops endpoints — used by cron / test harness to drive background jobs."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.dependencies import get_db, require_role
from app.models.user import User, UserRole
from app.services import scheduler

router = APIRouter(prefix="/internal", tags=["Internal"])


@router.post("/tick")
def run_tick(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_role(UserRole.admin))],
) -> dict:
    """Run the daily scheduler tick synchronously. Idempotent per-day."""
    scheduler.run_daily_tick(db)
    return {"ran": True}
