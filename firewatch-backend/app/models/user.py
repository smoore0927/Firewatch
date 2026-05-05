"""
User model and role definitions.

UserRole is a Python enum stored as a string in Postgres (not an integer).
String storage makes the database readable without a lookup table:
  SELECT * FROM users WHERE role = 'admin'
  vs.
  SELECT * FROM users WHERE role = 3  (what does 3 mean?)

Role capabilities (enforced in API routes via require_role()):
  admin             -- full access, user management, can delete risks
  security_analyst  -- view all risks, generate reports, run analytics
  risk_owner        -- create risks, edit their own risks, add mitigations
  executive_viewer  -- read-only access to dashboards and summaries
"""

import enum

from sqlalchemy import Boolean, Column, DateTime, Enum, Integer, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models.database import Base


class UserRole(str, enum.Enum):
    """
    Inheriting from both str and enum.Enum means:
      - Values compare equal to plain strings: UserRole.admin == "admin"
      - JSON serialization works automatically (Pydantic, FastAPI responses)
      - SQLAlchemy stores and retrieves the string value, not the enum name
    """
    admin = "admin"
    security_analyst = "security_analyst"
    risk_owner = "risk_owner"
    executive_viewer = "executive_viewer"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    # Nullable: SSO-only users authenticate via the IdP and never set a password.
    hashed_password = Column(String(255), nullable=True)
    full_name = Column(String(255))
    role = Column(Enum(UserRole), nullable=False, default=UserRole.risk_owner)
    # 'local' = email+password, 'oidc' = provisioned via SSO. Drives no logic on its
    # own — both methods can co-exist on a single account once linked.
    auth_provider = Column(
        String(20), nullable=False, default="local", server_default="local"
    )
    # OIDC `sub` claim (or other stable IdP identifier). Used to link an SSO login
    # back to a user record when the email address changes at the IdP.
    external_id = Column(String(255), nullable=True, index=True)
    # is_active disables an account without deleting it -- preserves audit history
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # foreign_keys is required because Risk has two FKs pointing at users
    owned_risks = relationship(
        "Risk", back_populates="owner", foreign_keys="Risk.owner_id"
    )
    created_risks = relationship(
        "Risk", back_populates="created_by", foreign_keys="Risk.created_by_id"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email} role={self.role}>"
