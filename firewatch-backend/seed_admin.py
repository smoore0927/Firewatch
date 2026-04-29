"""
One-time script to create the initial admin user.

Run once from inside firewatch-backend/ with the venv active:
  python seed_admin.py

Then delete this file -- it has no place in production.
The admin account it creates can then log in and create all other users
via POST /api/users.
"""

import sys
from app.models.database import SessionLocal
from app.models.user import User, UserRole
from app.core.security import hash_password


def main() -> None:
    email = input("Admin email: ").strip()
    if not email:
        print("Email cannot be empty.")
        sys.exit(1)

    password = input("Admin password (min 12 chars): ").strip()
    if len(password) < 12:
        print("Password must be at least 12 characters.")
        sys.exit(1)

    full_name = input("Full name (optional, press Enter to skip): ").strip() or None

    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            print(f"A user with email '{email}' already exists.")
            sys.exit(1)

        admin = User(
            email=email,
            hashed_password=hash_password(password),
            full_name=full_name,
            role=UserRole.admin,
            is_active=True,
        )
        db.add(admin)
        db.commit()
        db.refresh(admin)
        print(f"\nAdmin user created successfully.")
        print(f"  ID:    {admin.id}")
        print(f"  Email: {admin.email}")
        print(f"  Role:  {admin.role.value}")
        print(f"\nYou can now log in at POST /api/auth/login")
        print("Delete this file when done: del seed_admin.py")
    finally:
        db.close()


if __name__ == "__main__":
    main()
