"""Singleton row tracking the daily-tick scheduler's last run dates."""

from sqlalchemy import Column, Date, Integer

from app.models.database import Base

__all__ = ["SchedulerState"]


class SchedulerState(Base):
    """Single-row sentinel (id always = 1). Atomic UPDATE on the date columns is
    the multi-replica lock that prevents double-firing the daily tick."""

    __tablename__ = "scheduler_state"

    id = Column(Integer, primary_key=True)
    last_review_digest_date = Column(Date, nullable=True)
    last_response_overdue_date = Column(Date, nullable=True)
