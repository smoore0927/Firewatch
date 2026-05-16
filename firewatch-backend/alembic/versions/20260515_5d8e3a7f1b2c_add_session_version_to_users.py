"""add session_version to users

Revision ID: 5d8e3a7f1b2c
Revises: 7b2e9a4c5d3f
Create Date: 2026-05-15 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic
revision: str = '5d8e3a7f1b2c'
down_revision: Union[str, None] = '7b2e9a4c5d3f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'session_version',
                sa.Integer(),
                nullable=False,
                server_default='1',
            )
        )
    op.execute("UPDATE users SET session_version = 1 WHERE session_version IS NULL")


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('session_version')
