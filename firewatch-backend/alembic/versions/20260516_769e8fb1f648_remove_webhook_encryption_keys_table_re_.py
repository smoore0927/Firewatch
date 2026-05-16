"""remove webhook encryption keys table; re-encrypt webhook secrets directly with kek

Revision ID: 769e8fb1f648
Revises: fb2cd4af0651
Create Date: 2026-05-16 18:12:15.483568

The DEK layer duplicated work the chosen external KMS (Vault / Key Vault / AWS)
already provides (rotation, versioning, audit). This migration:
  1. Unwraps the active DEK with the KEK and decrypts every webhook_subscriptions.secret.
  2. Re-encrypts each secret directly with the KEK and writes it back.
  3. Drops the webhook_encryption_keys table.

`downgrade` is the inverse — recreates the table, mints a fresh DEK, and
re-wraps every subscription secret under it so prior revision code can read them.
"""
import base64
from datetime import datetime, timezone
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


# revision identifiers, used by Alembic
revision: str = "769e8fb1f648"
down_revision: Union[str, None] = "fb2cd4af0651"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Inlined KEK helper — matches the prior app/core/crypto.py exactly so the
# unwrap path keeps working even after the application code stops shipping it.
_KEK_CONTEXT = b"firewatch.webhook.kek.v1"


def _kek() -> Fernet:
    from app.core.config import settings

    if settings.WEBHOOK_KEK:
        return Fernet(settings.WEBHOOK_KEK.encode("utf-8"))
    hkdf = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=_KEK_CONTEXT)
    derived = hkdf.derive(settings.SECRET_KEY.encode("utf-8"))
    return Fernet(base64.urlsafe_b64encode(derived))


def upgrade() -> None:
    bind = op.get_bind()
    kek = _kek()

    # 1. Resolve the active DEK; bail cleanly if the table is empty (fresh DB).
    active_row = bind.execute(
        sa.text(
            "SELECT ciphertext_dek FROM webhook_encryption_keys "
            "WHERE is_active = 1 LIMIT 1"
        )
    ).fetchone()

    if active_row is not None:
        dek_plaintext = kek.decrypt(active_row.ciphertext_dek.encode("utf-8"))
        dek = Fernet(dek_plaintext)

        # 2. Re-encrypt every subscription secret directly under the KEK.
        rows = bind.execute(
            sa.text("SELECT id, secret FROM webhook_subscriptions")
        ).fetchall()
        for row in rows:
            plaintext = dek.decrypt(row.secret.encode("utf-8"))
            new_ct = kek.encrypt(plaintext).decode("utf-8")
            bind.execute(
                sa.text(
                    "UPDATE webhook_subscriptions SET secret = :s WHERE id = :id"
                ),
                {"s": new_ct, "id": row.id},
            )

    # 3. Drop the now-redundant table (and its index).
    with op.batch_alter_table("webhook_encryption_keys", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_webhook_encryption_keys_is_active"))
    op.drop_table("webhook_encryption_keys")


def downgrade() -> None:
    op.create_table(
        "webhook_encryption_keys",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ciphertext_dek", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rotated_by_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["rotated_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("webhook_encryption_keys", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_webhook_encryption_keys_is_active"),
            ["is_active"],
            unique=False,
        )

    bind = op.get_bind()
    kek = _kek()

    # Mint a fresh DEK, wrap it with the KEK, install it as the active row.
    dek_plaintext = Fernet.generate_key()
    dek_ciphertext = kek.encrypt(dek_plaintext).decode("utf-8")
    bind.execute(
        sa.text(
            "INSERT INTO webhook_encryption_keys "
            "(ciphertext_dek, is_active, created_at) "
            "VALUES (:ct, :active, :now)"
        ),
        {
            "ct": dek_ciphertext,
            "active": True,
            "now": datetime.now(timezone.utc),
        },
    )

    # Decrypt each subscription with the KEK and re-encrypt with the new DEK.
    dek = Fernet(dek_plaintext)
    rows = bind.execute(
        sa.text("SELECT id, secret FROM webhook_subscriptions")
    ).fetchall()
    for row in rows:
        plaintext = kek.decrypt(row.secret.encode("utf-8"))
        new_ct = dek.encrypt(plaintext).decode("utf-8")
        bind.execute(
            sa.text("UPDATE webhook_subscriptions SET secret = :s WHERE id = :id"),
            {"s": new_ct, "id": row.id},
        )
