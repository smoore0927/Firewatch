"""add review cadence to risks

Revision ID: 2a5bb2f15c49
Revises: 2ab7dcc49a06
Create Date: 2026-05-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic
revision: str = '2a5bb2f15c49'
down_revision: Union[str, None] = '2ab7dcc49a06'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('risks', sa.Column('review_frequency_days', sa.Integer(), nullable=True))
    op.add_column('risks', sa.Column('next_review_date', sa.Date(), nullable=True))
    op.create_index(op.f('ix_risks_next_review_date'), 'risks', ['next_review_date'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_risks_next_review_date'), table_name='risks')
    op.drop_column('risks', 'next_review_date')
    op.drop_column('risks', 'review_frequency_days')
