"""add source_url and last_imported_at to control_frameworks

Revision ID: a1b2c3d4e5f6
Revises: 3f5a921133a6
Create Date: 2026-05-30 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '3f5a921133a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('control_frameworks', schema=None) as batch_op:
        batch_op.add_column(sa.Column('source_url', sa.String(length=1000), nullable=True))
        batch_op.add_column(sa.Column('last_imported_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('control_frameworks', schema=None) as batch_op:
        batch_op.drop_column('last_imported_at')
        batch_op.drop_column('source_url')
