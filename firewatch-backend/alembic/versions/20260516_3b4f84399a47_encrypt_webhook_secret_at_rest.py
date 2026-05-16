"""encrypt webhook secret at rest

Revision ID: 3b4f84399a47
Revises: 8e2f5f8a7e82
Create Date: 2026-05-16 10:18:44.434473

"""
import base64
import hashlib
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


# revision identifiers, used by Alembic
revision: str = '3b4f84399a47'
down_revision: Union[str, None] = '8e2f5f8a7e82'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Legacy single-key encryption: HKDF-from-SECRET_KEY, context v1. Pinned here so
# this migration stays runnable even after the production crypto module switches
# to envelope encryption.
_LEGACY_CONTEXT = b"firewatch.webhook.secret.v1"


def _legacy_fernet() -> Fernet:
    from app.core.config import settings

    hkdf = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=_LEGACY_CONTEXT)
    key = hkdf.derive(settings.SECRET_KEY.encode("utf-8"))
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_for_storage(plaintext: str) -> str:
    return _legacy_fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_from_storage(ciphertext: str) -> str:
    return _legacy_fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")


def upgrade() -> None:
    bind = op.get_bind()

    # 1. Add temp column for the encrypted secret (nullable while we backfill).
    with op.batch_alter_table("webhook_subscriptions") as batch:
        batch.add_column(sa.Column("secret_encrypted", sa.Text(), nullable=True))

    # 2. Encrypt every existing plaintext into the temp column.
    rows = bind.execute(
        sa.text("SELECT id, secret FROM webhook_subscriptions")
    ).fetchall()
    for row in rows:
        bind.execute(
            sa.text(
                "UPDATE webhook_subscriptions SET secret_encrypted = :ciphertext WHERE id = :id"
            ),
            {"ciphertext": encrypt_for_storage(row.secret), "id": row.id},
        )

    # 3. Drop the old plaintext column, drop secret_hash, then rename temp -> secret
    #    and tighten to NOT NULL. Done inside one batch so SQLite rewrites the
    #    table once.
    with op.batch_alter_table("webhook_subscriptions") as batch:
        batch.drop_column("secret_hash")
        batch.drop_column("secret")
        batch.alter_column("secret_encrypted", new_column_name="secret", nullable=False)


def downgrade() -> None:
    bind = op.get_bind()

    # 1. Add temp plaintext column + the secret_hash column back.
    with op.batch_alter_table("webhook_subscriptions") as batch:
        batch.add_column(sa.Column("secret_plain", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("secret_hash", sa.String(length=128), nullable=True))

    # 2. Decrypt each row's secret and backfill both columns.
    rows = bind.execute(
        sa.text("SELECT id, secret FROM webhook_subscriptions")
    ).fetchall()
    for row in rows:
        plaintext = decrypt_from_storage(row.secret)
        hashed = hashlib.sha256(plaintext.encode("utf-8")).hexdigest()
        bind.execute(
            sa.text(
                "UPDATE webhook_subscriptions "
                "SET secret_plain = :plain, secret_hash = :hashed "
                "WHERE id = :id"
            ),
            {"plain": plaintext, "hashed": hashed, "id": row.id},
        )

    # 3. Drop the encrypted column, rename plaintext back to `secret`, tighten
    #    both columns to NOT NULL.
    with op.batch_alter_table("webhook_subscriptions") as batch:
        batch.drop_column("secret")
        batch.alter_column("secret_plain", new_column_name="secret", nullable=False)
        batch.alter_column("secret_hash", nullable=False)
