"""
Application settings loaded from environment variables (or a .env file).

pydantic-settings reads the .env file automatically and validates every field
against the declared types at startup — if SECRET_KEY is missing or DATABASE_URL
is malformed, the app refuses to start rather than failing at runtime.
"""

from pydantic_settings import BaseSettings
from pydantic import field_validator


class Settings(BaseSettings):
    # App
    APP_NAME: str = "Firewatch"
    DEBUG: bool = False

    # Database — defaults to a local SQLite file if not set in .env
    DATABASE_URL: str = "sqlite:///./firewatch.db"

    # Auth -- these are security-critical; no defaults for the secret key
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # CORS -- stored as a comma-separated string in .env
    # Kept as str here because pydantic-settings v2 tries to JSON-decode list[str]
    # fields, which breaks plain URLs. Parsed to a list via the cors_origins property.
    CORS_ORIGINS: str = "http://localhost:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        """Return CORS_ORIGINS as a list, split on commas."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]

    @field_validator("SECRET_KEY")
    @classmethod
    def secret_key_must_not_be_placeholder(cls, v: str) -> str:
        if v == "change-me-generate-a-real-secret":
            raise ValueError(
                "SECRET_KEY is still the placeholder value. "
                "Run: python -c \"import secrets; print(secrets.token_hex(32))\""
            )
        return v

    model_config = {"env_file": ".env", "case_sensitive": True}


# Single shared instance — import this everywhere, never instantiate Settings() again.
settings = Settings()
