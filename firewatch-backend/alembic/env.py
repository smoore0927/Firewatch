"""
Alembic environment — connects the migration engine to our models and database.

How autogenerate works:
  When you run `alembic revision --autogenerate -m "description"`, Alembic
  compares Base.metadata (the schema defined by your SQLAlchemy models) against
  the actual database schema and generates a migration file with the differences.

  For this to work, ALL models must be imported before target_metadata is set.
  We do this by importing app.models (the __init__.py imports every model).
"""

import os
import sys
from pathlib import Path
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Add the project root (firewatch-backend/) to sys.path so that `import app`
# works when Alembic runs env.py. Without this, Python only sees the alembic/
# subdirectory and can't find the app package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Load all models so Alembic sees the full schema
import app.models  # noqa: F401 - side-effect import to register all models
from app.models.database import Base

# Alembic Config object — gives access to alembic.ini values
config = context.config

# Set up Python logging from the alembic.ini [loggers] section.
# `disable_existing_loggers=False` is critical: when env.py runs inside the
# FastAPI lifespan, the default (True) silently disables every logger the
# app already created (e.g. app.services.sso_service), making downstream
# warnings invisible to handlers like pytest's caplog.
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# The metadata Alembic diffs against to detect schema changes
target_metadata = Base.metadata


def get_url() -> str:
    """
    Read DATABASE_URL from the environment (or .env file via the app config).
    This is intentionally separate from alembic.ini so credentials aren't
    committed to version control.
    """
    # Import here to trigger pydantic-settings .env loading
    from app.core.config import settings
    return settings.DATABASE_URL


def run_migrations_offline() -> None:
    """
    'Offline' mode: generate SQL without connecting to the database.
    Useful for generating migration scripts to review before applying.
    Run with: alembic upgrade head --sql
    """
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,          # detect column type changes
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    'Online' mode: connect to the database and apply migrations directly.
    This is the normal mode when running `alembic upgrade head`.
    """
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = get_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,    # NullPool: don't reuse connections in migrations
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            # SQLite has very limited ALTER TABLE support; batch mode rewrites
            # the whole table to apply schema changes.
            render_as_batch=get_url().startswith("sqlite"),
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
