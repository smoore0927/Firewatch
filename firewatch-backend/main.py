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



@app.get("/health", tags=["Health"])
def health_check() -> dict:
    """
    Returns 200 OK if the app is running.
    Used by Docker, load balancers, and uptime monitors.
    Does not check database connectivity (keep it fast).
    """
    return {"status": "ok", "app": settings.APP_NAME}
