import enum


class UserRole(str, enum.Enum):
    admin = "admin"
    security_analyst = "security_analyst"
    risk_owner = "risk_owner"
    executive_viewer = "executive_viewer"
