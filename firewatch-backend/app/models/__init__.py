# Import all models here so Alembic's env.py only needs to import this module
# to discover every table. Keeping this list up to date is the only maintenance
# required when you add a new model.
from app.models.user import User          # noqa: F401
from app.models.risk import (             # noqa: F401
    Risk,
    RiskAssessment,
    RiskResponse,
    RiskHistory,
)
from app.models.audit_log import AuditLog  # noqa: F401
from app.models.api_key import ApiKey  # noqa: F401
from app.models.webhook import (  # noqa: F401
    WebhookSubscription,
    WebhookDelivery,
    DeliveryStatus,
)
from app.models.scheduler import SchedulerState  # noqa: F401
