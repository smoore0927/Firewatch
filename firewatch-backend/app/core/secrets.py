"""Pluggable secrets provider. Selected by SECRETS_BACKEND env var."""

import os
from abc import ABC, abstractmethod
from functools import lru_cache
from pathlib import Path


class SecretsProvider(ABC):
    @abstractmethod
    def get(self, key: str) -> str | None: ...


class EnvProvider(SecretsProvider):
    """Reads directly from environment variables. Default / local-dev backend."""

    def get(self, key: str) -> str | None:
        return os.environ.get(key)


class FileProvider(SecretsProvider):
    """Reads secrets from mounted files (Docker secrets, k8s volume mounts).
    Tries the key name as-is, lowercased, and lowercased-with-hyphens.
    """

    def __init__(self, base_path: str = "/run/secrets"):
        self._base = Path(base_path)

    def get(self, key: str) -> str | None:
        for name in (key, key.lower(), key.lower().replace("_", "-")):
            p = self._base / name
            if p.is_file():
                return p.read_text().strip()
        return None


class VaultProvider(SecretsProvider):
    """HashiCorp Vault KV v2. Requires hvac."""

    def __init__(
        self,
        addr: str,
        path_prefix: str,
        token: str | None,
        role_id: str | None,
        secret_id: str | None,
        mount_path: str,
    ):
        try:
            import hvac  # noqa: PLC0415
        except ImportError as e:
            raise RuntimeError(
                "hvac required for SECRETS_BACKEND=vault. Run: pip install hvac"
            ) from e

        client = hvac.Client(url=addr)
        if token:
            client.token = token
        elif role_id and secret_id:
            client.auth.approle.login(role_id=role_id, secret_id=secret_id)
        else:
            raise RuntimeError(
                "Vault auth requires VAULT_TOKEN or VAULT_ROLE_ID+VAULT_SECRET_ID"
            )

        self._client = client
        self._prefix = path_prefix.rstrip("/")
        self._mount = mount_path

    def get(self, key: str) -> str | None:
        import hvac.exceptions  # noqa: PLC0415

        path = f"{self._prefix}/{key}" if self._prefix else key
        try:
            resp = self._client.secrets.kv.v2.read_secret(
                path=path, mount_point=self._mount
            )
            data = resp["data"]["data"]
            return data.get("value") or data.get(key)
        except hvac.exceptions.InvalidPath:
            return None


class AzureKeyVaultProvider(SecretsProvider):
    """Azure Key Vault. Uses DefaultAzureCredential (Managed Identity in prod, az login in dev).
    Underscores in keys are converted to hyphens (Key Vault naming rules).
    """

    def __init__(self, vault_url: str):
        try:
            from azure.identity import DefaultAzureCredential  # noqa: PLC0415
            from azure.keyvault.secrets import SecretClient  # noqa: PLC0415
        except ImportError as e:
            raise RuntimeError(
                "azure-keyvault-secrets and azure-identity required for "
                "SECRETS_BACKEND=azure_keyvault. "
                "Run: pip install azure-keyvault-secrets azure-identity"
            ) from e
        self._client = SecretClient(vault_url=vault_url, credential=DefaultAzureCredential())

    def get(self, key: str) -> str | None:
        from azure.core.exceptions import ResourceNotFoundError  # noqa: PLC0415

        try:
            return self._client.get_secret(key.replace("_", "-")).value
        except ResourceNotFoundError:
            return None


class AWSSecretsManagerProvider(SecretsProvider):
    """AWS Secrets Manager. Requires boto3."""

    def __init__(self, region: str):
        try:
            import boto3  # noqa: PLC0415
        except ImportError as e:
            raise RuntimeError(
                "boto3 required for SECRETS_BACKEND=aws. Run: pip install boto3"
            ) from e
        self._client = boto3.client("secretsmanager", region_name=region)

    def get(self, key: str) -> str | None:
        from botocore.exceptions import ClientError  # noqa: PLC0415

        try:
            return self._client.get_secret_value(SecretId=key)["SecretString"]
        except ClientError:
            return None


@lru_cache(maxsize=1)
def get_provider() -> SecretsProvider:
    """Initialise and return the configured provider. Called once at startup."""
    backend = os.environ.get("SECRETS_BACKEND", "env").lower()
    if backend == "env":
        return EnvProvider()
    if backend == "file":
        return FileProvider(base_path=os.environ.get("SECRETS_FILE_PATH", "/run/secrets"))
    if backend == "vault":
        return VaultProvider(
            addr=os.environ["VAULT_ADDR"],
            path_prefix=os.environ.get("VAULT_PATH_PREFIX", "firewatch"),
            token=os.environ.get("VAULT_TOKEN"),
            role_id=os.environ.get("VAULT_ROLE_ID"),
            secret_id=os.environ.get("VAULT_SECRET_ID"),
            mount_path=os.environ.get("VAULT_MOUNT_PATH", "secret"),
        )
    if backend == "azure_keyvault":
        return AzureKeyVaultProvider(vault_url=os.environ["AZURE_KEYVAULT_URL"])
    if backend == "aws":
        return AWSSecretsManagerProvider(region=os.environ["AWS_REGION"])
    raise RuntimeError(
        f"Unknown SECRETS_BACKEND={backend!r}. Valid: env, file, vault, azure_keyvault, aws"
    )


# Keys the provider may resolve. Everything else is plain env var config.
SECRET_KEYS = frozenset(
    {
        "SECRET_KEY",
        "WEBHOOK_KEK",
        "WEBHOOK_KEK_PREVIOUS",  # optional, for rotation transition windows
        "SCIM_BEARER_TOKEN",
        "OIDC_CLIENT_SECRET",
        "DATABASE_URL",
    }
)


def resolve_secrets() -> dict[str, str]:
    """Fetch all known secrets from the provider. Returns only non-None values."""
    provider = get_provider()
    return {k: v for k in SECRET_KEYS if (v := provider.get(k)) is not None}
