"""
Application settings loaded from environment variables (or a .env file).

pydantic-settings reads the .env file automatically and validates every field
against the declared types at startup — if SECRET_KEY is missing or DATABASE_URL
is malformed, the app refuses to start rather than failing at runtime.
"""

from pydantic_settings import BaseSettings
from pydantic import field_validator, ValidationInfo

from app.core.roles import UserRole


class Settings(BaseSettings):
    # App
    APP_NAME: str = "Firewatch"
    DEBUG: bool = False

    # --- Secrets provider (declared first so the SECRET_KEY validator can see it) ---
    SECRETS_BACKEND: str = "env"
    VAULT_ADDR: str | None = None
    VAULT_TOKEN: str | None = None
    VAULT_ROLE_ID: str | None = None
    VAULT_SECRET_ID: str | None = None
    VAULT_MOUNT_PATH: str = "secret"
    VAULT_PATH_PREFIX: str = "firewatch"
    AZURE_KEYVAULT_URL: str | None = None
    AWS_REGION: str | None = None
    SECRETS_FILE_PATH: str = "/run/secrets"

    # Database — defaults to a local SQLite file if not set in .env
    DATABASE_URL: str = "sqlite:///./firewatch.db"

    # Auth -- these are security-critical. When SECRETS_BACKEND=env (the default),
    # the placeholder/empty validator below enforces a real value. When a non-env
    # backend is configured the value is populated at lifespan startup, so the
    # field starts empty and the validator skips its placeholder check.
    SECRET_KEY: str = ""
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Optional master key (KEK) for at-rest webhook secret encryption. If unset, a
    # KEK is derived from SECRET_KEY via HKDF using a distinct context — fine for
    # dev, but in prod you should set this explicitly so SECRET_KEY rotation does
    # not invalidate webhook ciphertexts. Generate one with:
    #   openssl rand -hex 32
    WEBHOOK_KEK: str | None = None

    # Optional second key for rotation transition windows.
    # When set, decrypt tries both keys (MultiFernet); encrypt always uses WEBHOOK_KEK.
    WEBHOOK_KEK_PREVIOUS: str | None = None

    # CORS -- stored as a comma-separated string in .env
    # Kept as str here because pydantic-settings v2 tries to JSON-decode list[str]
    # fields, which breaks plain URLs. Parsed to a list via the cors_origins property.
    CORS_ORIGINS: str = "http://localhost:3000"

    # Frontend base URL — used for OIDC redirects after callback.
    FRONTEND_URL: str = "http://localhost:3000"

    # --- OIDC / SSO (all optional; SSO is off unless OIDC_ENABLED + the four required values are set) ---
    OIDC_ENABLED: bool = False
    OIDC_PROVIDER_NAME: str = "SSO"
    OIDC_DISCOVERY_URL: str | None = None
    OIDC_CLIENT_ID: str | None = None
    OIDC_CLIENT_SECRET: str | None = None
    OIDC_REDIRECT_URI: str | None = None
    OIDC_SCOPES: str = "openid email profile"
    OIDC_DEFAULT_ROLE: str = "risk_owner"

    # Name of the claim in the ID token that contains the user's groups/roles.
    # Defaults to "groups" (Entra group GUIDs, Okta group names).
    # Set to "roles" for Entra App Roles (recommended) or a custom claim name.
    OIDC_ROLE_CLAIM: str = "groups"

    # Map from claim value → Firewatch role. Empty by default → all SSO users get OIDC_DEFAULT_ROLE.
    # Pydantic-settings JSON-decodes dict-typed fields from env automatically.
    OIDC_ROLE_MAP: dict[str, UserRole] = {}

    # --- CAEP (Continuous Access Evaluation Protocol) receiver ---
    CAEP_ENABLED: bool = False
    # Audience expected in the SET's aud claim. Defaults to OIDC_CLIENT_ID if not set.
    CAEP_AUDIENCE: str | None = None

    # --- SCIM 2.0 provisioning ---
    SCIM_ENABLED: bool = False
    SCIM_BEARER_TOKEN: str | None = None  # Long-lived shared secret; set in IdP's SCIM connector

    @property
    def cors_origins_list(self) -> list[str]:
        """Return CORS_ORIGINS as a list, split on commas."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]

    @property
    def oidc_is_configured(self) -> bool:
        """True only if OIDC is enabled AND the required client/discovery values are set."""
        return bool(
            self.OIDC_ENABLED
            and self.OIDC_DISCOVERY_URL
            and self.OIDC_CLIENT_ID
            and self.OIDC_CLIENT_SECRET
            and self.OIDC_REDIRECT_URI
        )

    @field_validator("SECRET_KEY")
    @classmethod
    def secret_key_must_not_be_placeholder(cls, v: str, info: ValidationInfo) -> str:
        # External secrets backends populate SECRET_KEY at lifespan startup, so
        # an empty/placeholder value is acceptable here — main.py enforces a
        # real value after the provider has run.
        if info.data.get("SECRETS_BACKEND", "env") != "env":
            return v
        if v == "change-me-generate-a-real-secret" or v == "":
            raise ValueError(
                "SECRET_KEY is still the placeholder value. "
                "Run: openssl rand -hex 32"
            )
        return v

    @field_validator("OIDC_DEFAULT_ROLE")
    @classmethod
    def oidc_default_role_must_be_valid(cls, v: str) -> str:
        valid = {r.value for r in UserRole}
        if v not in valid:
            raise ValueError(
                f"OIDC_DEFAULT_ROLE={v!r} is not a valid role. "
                f"Valid roles: {', '.join(sorted(valid))}"
            )
        return v

    model_config = {"env_file": ".env", "case_sensitive": True}


# Single shared instance — import this everywhere, never instantiate Settings() again.
settings = Settings()
