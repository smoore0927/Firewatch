"""add api_keys table

Revision ID: 4f1b2c3d8e9a
Revises: 8a4f1c9d2e7b
Create Date: 2026-05-13 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic
revision: str = '4f1b2c3d8e9a'
down_revision: Union[str, None] = '8a4f1c9d2e7b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'api_keys',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('prefix', sa.String(length=16), nullable=False),
        sa.Column('hashed_key', sa.String(length=128), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('CURRENT_TIMESTAMP'),
            nullable=False,
        ),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ['user_id'], ['users.id'], ondelete='CASCADE'
        ),
    )
    op.create_index(
        op.f('ix_api_keys_user_id'), 'api_keys', ['user_id'], unique=False
    )
    op.create_index(
        op.f('ix_api_keys_prefix'), 'api_keys', ['prefix'], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_api_keys_prefix'), table_name='api_keys')
    op.drop_index(op.f('ix_api_keys_user_id'), table_name='api_keys')
    op.drop_table('api_keys')
