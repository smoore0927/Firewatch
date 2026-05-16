"""User ORM model."""

from sqlalchemy import Boolean, Column, DateTime, Enum, Integer, String, text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.roles import UserRole
from app.models.database import Base

__all__ = ["User", "UserRole"]


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
    # Forces a password change on next login. Set to True for users created via
    # POST /api/users; cleared once they POST /api/auth/change-password successfully.
    # Default False so seeded admins and SCIM/OIDC users skip the first-login gate.
    must_change_password = Column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    last_logout_at = Column(DateTime(timezone=True), nullable=True)
    session_version = Column(Integer, nullable=False, default=1, server_default="1")
    created_at = Column(DateTime(timezone=True), server_default=text('CURRENT_TIMESTAMP'), nullable=False)
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
