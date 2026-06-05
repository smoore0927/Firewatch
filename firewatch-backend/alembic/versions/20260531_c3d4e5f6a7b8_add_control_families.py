"""add control_families table

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-05-31 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'control_families',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('framework_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('display_label', sa.String(length=255), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['framework_id'], ['control_frameworks.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('framework_id', 'name', name='uq_control_families_framework_name'),
    )
    with op.batch_alter_table('control_families', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_control_families_framework_id'), ['framework_id'], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table('control_families', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_control_families_framework_id'))
    op.drop_table('control_families')
