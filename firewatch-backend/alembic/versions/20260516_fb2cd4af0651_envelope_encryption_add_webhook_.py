"""envelope encryption: add webhook_encryption_keys + bootstrap first dek

Revision ID: fb2cd4af0651
Revises: 3b4f84399a47
Create Date: 2026-05-16 11:14:12.377739

Switches webhook secrets from a single KEY-derived-from-SECRET_KEY scheme to
envelope encryption. A new `webhook_encryption_keys` table holds KEK-wrapped
DEKs; one DEK is active at a time and rotated via the admin API.
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
revision: str = 'fb2cd4af0651'
down_revision: Union[str, None] = '3b4f84399a47'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Crypto helpers inlined so this migration is self-contained and remains
# runnable even if app/core/crypto.py keeps evolving.
_LEGACY_CONTEXT = b"firewatch.webhook.secret.v1"
_KEK_CONTEXT = b"firewatch.webhook.kek.v1"


def _legacy_fernet() -> Fernet:
    from app.core.config import settings

    hkdf = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=_LEGACY_CONTEXT)
    key = hkdf.derive(settings.SECRET_KEY.encode("utf-8"))
    return Fernet(base64.urlsafe_b64encode(key))


def _kek() -> Fernet:
    from app.core.config import settings

    if settings.WEBHOOK_KEK:
        return Fernet(settings.WEBHOOK_KEK.encode("utf-8"))
    hkdf = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=_KEK_CONTEXT)
    derived = hkdf.derive(settings.SECRET_KEY.encode("utf-8"))
    return Fernet(base64.urlsafe_b64encode(derived))


def upgrade() -> None:
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

    # Bootstrap the first DEK.
    bind = op.get_bind()
    kek = _kek()
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

    # Re-encrypt every existing webhook subscription secret under the new DEK.
    dek = Fernet(dek_plaintext)
    legacy = _legacy_fernet()
    rows = bind.execute(
        sa.text("SELECT id, secret FROM webhook_subscriptions")
    ).fetchall()
    for row in rows:
        plaintext = legacy.decrypt(row.secret.encode("utf-8"))
        new_ct = dek.encrypt(plaintext).decode("utf-8")
        bind.execute(
            sa.text("UPDATE webhook_subscriptions SET secret = :s WHERE id = :id"),
            {"s": new_ct, "id": row.id},
        )


def downgrade() -> None:
    bind = op.get_bind()

    # Decrypt every subscription with the active DEK and re-encrypt under the
    # legacy SECRET_KEY-derived Fernet so the prior revision can keep reading them.
    active_row = bind.execute(
        sa.text(
            "SELECT ciphertext_dek FROM webhook_encryption_keys "
            "WHERE is_active = 1 LIMIT 1"
        )
    ).fetchone()
    if active_row is not None:
        kek = _kek()
        dek_plaintext = kek.decrypt(active_row.ciphertext_dek.encode("utf-8"))
        dek = Fernet(dek_plaintext)
        legacy = _legacy_fernet()
        rows = bind.execute(
            sa.text("SELECT id, secret FROM webhook_subscriptions")
        ).fetchall()
        for row in rows:
            plaintext = dek.decrypt(row.secret.encode("utf-8"))
            legacy_ct = legacy.encrypt(plaintext).decode("utf-8")
            bind.execute(
                sa.text("UPDATE webhook_subscriptions SET secret = :s WHERE id = :id"),
                {"s": legacy_ct, "id": row.id},
            )

    with op.batch_alter_table("webhook_encryption_keys", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_webhook_encryption_keys_is_active"))
    op.drop_table("webhook_encryption_keys")
