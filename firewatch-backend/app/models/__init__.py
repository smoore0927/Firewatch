# Import all models here so Alembic's env.py only needs to import this module
# to discover every table. Keeping this list up to date is the only maintenance
# required when you add a new model.
from app.models.user import User          # noqa: F401
from app.models.risk import (             # noqa: F401
    Risk,
    RiskAssessment,
    RiskTreatment,
    RiskHistory,
)
