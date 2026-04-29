"""
SQLAlchemy engine and session factory.

Everything that talks to the database flows through these three objects:
  - engine:       The connection pool. One per process.
  - SessionLocal: A factory for creating sessions. One session per request
                  (managed by the get_db() dependency in core/dependencies.py).
  - Base:         The declarative base class that all models inherit from.
                  SQLAlchemy uses it to track the schema and generate migrations.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings


_is_sqlite = settings.DATABASE_URL.startswith("sqlite")

engine = create_engine(
    settings.DATABASE_URL,
    # SQLite requires check_same_thread=False for FastAPI's threaded request handling.
    connect_args={"check_same_thread": False} if _is_sqlite else {},
    # pool_pre_ping tests connections before use — not meaningful for SQLite file databases.
    pool_pre_ping=not _is_sqlite,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """
    All models inherit from this. Using the modern DeclarativeBase (SQLAlchemy 2.x)
    rather than the deprecated declarative_base() function from ext.declarative.
    """
    pass
