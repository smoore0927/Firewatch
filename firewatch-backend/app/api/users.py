"""
User management routes — admin-only except for /me (in auth.py).

RBAC enforcement: require_role(UserRole.admin) is used as a dependency.
If the calling user isn't an admin, FastAPI returns 403 before the function body runs.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_db, require_role
from app.core.security import hash_password
from app.models.user import User, UserRole
from app.schemas.user import RoleUpdateRequest, UserCreate, UserResponse
from app.services.audit_service import record_event

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/assignable", response_model=list[UserResponse])
def list_assignable_users(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_role(UserRole.admin, UserRole.security_analyst))],
) -> list[User]:
    """
    Users available for risk ownership assignment.

    Excludes executive_viewers — they have a read-only role and aren't valid
    risk owners. Accessible to admins and security analysts since those are the
    only roles that can change a risk's owner_id via the API.

    Note: this route MUST appear before any /{user_id} routes so FastAPI does
    not interpret the literal string "assignable" as a user ID.
    """
    return (
        db.query(User)
        .filter(
            User.is_active.is_(True),
            User.role != UserRole.executive_viewer,
        )
        .order_by(User.full_name, User.email)
        .all()
    )


@router.get("", response_model=list[UserResponse])
def list_users(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_role(UserRole.admin))],
    include_inactive: Annotated[bool, Query()] = False,
) -> list[User]:
    """List users. Admin only. Pass ?include_inactive=true to include deactivated accounts."""
    query = db.query(User)
    if not include_inactive:
        query = query.filter(User.is_active.is_(True))
    return query.all()


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    request: Request,
    user_data: UserCreate,
    db: Annotated[Session, Depends(get_db)],
    current_admin: Annotated[User, Depends(require_role(UserRole.admin))],
) -> User:
    """
    Create a new user account. Admin only.
    The plain-text password never touches the database — it's hashed here.
    """
    existing = db.query(User).filter(User.email == user_data.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with that email already exists",
        )

    user = User(
        email=user_data.email,
        hashed_password=hash_password(user_data.password),
        full_name=user_data.full_name,
        role=user_data.role,
        # Force new admin-provisioned users through /change-password on first login.
        # SCIM/OIDC users don't hit this route and stay at the default False.
        must_change_password=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    record_event(
        db,
        action="user.created",
        user=current_admin,
        resource_type="user",
        resource_id=str(user.id),
        request=request,
        details={"created_email": user.email, "role": user.role.value},
    )
    db.commit()
    return user


@router.patch("/{user_id}/deactivate", response_model=UserResponse)
def deactivate_user(
    request: Request,
    user_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_admin: Annotated[User, Depends(require_role(UserRole.admin))],
) -> User:
    """
    Deactivate a user (soft disable — preserves all their risk history).
    An admin cannot deactivate themselves.
    """
    if user_id == current_admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot deactivate your own account",
        )
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.is_active = False
    db.commit()
    db.refresh(user)
    record_event(
        db,
        action="user.deactivated",
        user=current_admin,
        resource_type="user",
        resource_id=str(user.id),
        request=request,
        details={"deactivated_email": user.email},
    )
    db.commit()
    return user


@router.patch("/{user_id}/role", response_model=UserResponse)
def change_user_role(
    request: Request,
    user_id: int,
    body: RoleUpdateRequest,
    db: Annotated[Session, Depends(get_db)],
    current_admin: Annotated[User, Depends(require_role(UserRole.admin))],
) -> User:
    """Change a local user's role. Admin only."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if user.hashed_password is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Cannot change role for SSO-provisioned accounts. "
                "Their role is set by the identity provider's group claims on every sign-in."
            ),
        )

    if user_id == current_admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot change your own role",
        )

    if body.role != UserRole.admin and user.role == UserRole.admin:
        remaining_admins = (
            db.query(User)
            .filter(
                User.role == UserRole.admin,
                User.is_active.is_(True),
                User.id != user.id,
            )
            .count()
        )
        if remaining_admins == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot demote the last active admin",
            )

    if body.role == user.role:
        return user

    old_role = user.role.value
    user.role = body.role
    db.commit()
    db.refresh(user)
    record_event(
        db,
        action="user.role.changed",
        user=current_admin,
        resource_type="user",
        resource_id=str(user.id),
        request=request,
        details={"target_email": user.email, "from": old_role, "to": user.role.value},
    )
    db.commit()
    return user


@router.patch("/{user_id}/activate", response_model=UserResponse)
def activate_user(
    request: Request,
    user_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_admin: Annotated[User, Depends(require_role(UserRole.admin))],
) -> User:
    """Reactivate a previously deactivated user account. Admin only."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.is_active = True
    db.commit()
    db.refresh(user)
    record_event(
        db,
        action="user.activated",
        user=current_admin,
        resource_type="user",
        resource_id=str(user.id),
        request=request,
        details={"activated_email": user.email},
    )
    db.commit()
    return user
