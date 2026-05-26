"""add notifications table

Revision ID: b8e62d2cace1
Revises: 769e8fb1f648
Create Date: 2026-05-22 15:16:15.326747

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic
revision: str = 'b8e62d2cace1'
down_revision: Union[str, None] = '769e8fb1f648'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('notifications',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('type', sa.Enum('risk_assigned', 'review_overdue', 'response_overdue', 'risk_changed', name='notificationtype'), nullable=False),
    sa.Column('risk_id', sa.Integer(), nullable=True),
    sa.Column('payload', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('dedup_key', sa.String(length=255), nullable=True),
    sa.ForeignKeyConstraint(['risk_id'], ['risks.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('notifications', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_notifications_dedup_key'), ['dedup_key'], unique=False)
        batch_op.create_index('ix_notifications_user_created', ['user_id', 'created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_notifications_user_id'), ['user_id'], unique=False)
        batch_op.create_index('ix_notifications_user_read', ['user_id', 'read_at'], unique=False)
        batch_op.create_index('uq_notifications_user_dedup', ['user_id', 'dedup_key'], unique=True, sqlite_where=sa.text('dedup_key IS NOT NULL'), postgresql_where=sa.text('dedup_key IS NOT NULL'))


def downgrade() -> None:
    with op.batch_alter_table('notifications', schema=None) as batch_op:
        batch_op.drop_index('uq_notifications_user_dedup', sqlite_where=sa.text('dedup_key IS NOT NULL'), postgresql_where=sa.text('dedup_key IS NOT NULL'))
        batch_op.drop_index('ix_notifications_user_read')
        batch_op.drop_index(batch_op.f('ix_notifications_user_id'))
        batch_op.drop_index('ix_notifications_user_created')
        batch_op.drop_index(batch_op.f('ix_notifications_dedup_key'))

    op.drop_table('notifications')
    # Drop the enum type so postgres downgrades cleanly. SQLite ignores this.
    sa.Enum(name='notificationtype').drop(op.get_bind(), checkfirst=True)
