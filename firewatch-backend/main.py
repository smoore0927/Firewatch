"""
Application entry point.

Responsibilities:
  1. Create the FastAPI app instance with metadata
  2. Register CORS middleware (must be added before routers)
  3. Mount all API routers under /api
  4. Expose a /health endpoint for load balancers / Docker health checks

Security notes:
  - /docs and /redoc are hidden in production (DEBUG=False) to avoid exposing
    your API schema to potential attackers.
  - CORS is configured to only allow the specific frontend origin(s) defined in
    .env. Never use allow_origins=["*"] with allow_credentials=True -- browsers
    will reject it and it is a security risk.
  - allow_credentials=True is required because our auth uses HTTP-only cookies,
    which the browser only sends on cross-origin requests when this is set.
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api import auth, dashboard, risks, users

logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.APP_NAME,
    description="Cybersecurity Risk Register API -- NIST 800-30 aligned",
    version="0.1.0",
    # Hide interactive docs outside of development
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    openapi_url="/openapi.json" if settings.DEBUG else None,
)

# CORS must be registered before any routers
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,         # required for HTTP-only cookie auth
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type"],
)

# Mount routers -- all endpoints live under /api/...
app.include_router(auth.router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(risks.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")


@app.on_event("startup")
def create_tables_for_sqlite() -> None:
    if settings.DATABASE_URL.startswith("sqlite"):
        from app.models.database import Base, engine
        Base.metadata.create_all(bind=engine)


@app.on_event("startup")
def seed_admin_on_startup() -> None:
    """
    Create the first admin user on startup if:
      1. SEED_ADMIN_EMAIL and SEED_ADMIN_PASSWORD are set in the environment, AND
      2. No admin user exists yet in the database.

    This is idempotent -- it checks before inserting, so re-deploying or
    restarting the app will never create a duplicate or overwrite an existing user.

    In Azure App Service: set SEED_ADMIN_EMAIL and SEED_ADMIN_PASSWORD in
    Configuration -> Application settings, backed by Key Vault references.
    Once the first admin is created, you can remove those settings so they
    are not sitting in the environment indefinitely.
    """
    if not settings.SEED_ADMIN_EMAIL or not settings.SEED_ADMIN_PASSWORD:
        return  # env vars not set -- skip silently

    from app.models.database import SessionLocal
    from app.models.user import User, UserRole
    from app.core.security import hash_password

    db = SessionLocal()
    try:
        existing = db.query(User).filter(
            User.email == settings.SEED_ADMIN_EMAIL
        ).first()
        if existing:
            return  # admin already exists -- nothing to do

        admin = User(
            email=settings.SEED_ADMIN_EMAIL,
            hashed_password=hash_password(settings.SEED_ADMIN_PASSWORD),
            role=UserRole.admin,
            is_active=True,
        )
        db.add(admin)
        db.commit()
        logger.info("Seed admin created: %s", settings.SEED_ADMIN_EMAIL)
    except Exception as exc:
        logger.error("Failed to seed admin user: %s", exc)
        db.rollback()
    finally:
        db.close()


@app.get("/health", tags=["Health"])
def health_check() -> dict:
    """
    Returns 200 OK if the app is running.
    Used by Docker, load balancers, and uptime monitors.
    Does not check database connectivity (keep it fast).
    """
    return {"status": "ok", "app": settings.APP_NAME}
