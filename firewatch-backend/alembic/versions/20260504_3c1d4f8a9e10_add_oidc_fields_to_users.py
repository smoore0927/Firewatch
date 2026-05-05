"""add oidc fields to users

Revision ID: 3c1d4f8a9e10
Revises: 2a5bb2f15c49
Create Date: 2026-05-04 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic
revision: str = '3c1d4f8a9e10'
down_revision: Union[str, None] = '2a5bb2f15c49'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # batch_alter_table works on both SQLite (which can't ALTER COLUMN) and Postgres
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column(
                "auth_provider",
                sa.String(length=20),
                nullable=False,
                server_default="local",
            )
        )
        batch_op.add_column(
            sa.Column("external_id", sa.String(length=255), nullable=True)
        )
        batch_op.alter_column("hashed_password", existing_type=sa.String(length=255), nullable=True)
    op.create_index(op.f("ix_users_external_id"), "users", ["external_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_users_external_id"), table_name="users")
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column("hashed_password", existing_type=sa.String(length=255), nullable=False)
        batch_op.drop_column("external_id")
        batch_op.drop_column("auth_provider")
