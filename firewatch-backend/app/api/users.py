"""
User management routes — admin-only except for /me (in auth.py).

RBAC enforcement: require_role(UserRole.admin) is used as a dependency.
If the calling user isn't an admin, FastAPI returns 403 before the function body runs.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_db, require_role
from app.core.security import hash_password
from app.models.user import User, UserRole
from app.schemas.user import UserCreate, UserResponse

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


@router.get("/", response_model=list[UserResponse])
def list_users(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_role(UserRole.admin))],
) -> list[User]:
    """List all active users. Admin only."""
    return db.query(User).filter(User.is_active.is_(True)).all()


@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    user_data: UserCreate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_role(UserRole.admin))],
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
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.patch("/{user_id}/deactivate", response_model=UserResponse)
def deactivate_user(
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
    return user
