"""rename treatment to response

Rename the domain concept "treatment" to "response":
  - table:  risk_treatments -> risk_responses
  - column: risk_responses.treatment_type -> response_type
  - index:  ix_risk_treatments_risk_id -> ix_risk_responses_risk_id

The four enum values (mitigate/accept/transfer/avoid) and the four status
values (planned/in_progress/completed/deferred) are left untouched — they
are domain-standard NIST terminology, not the part that needed renaming.
The PostgreSQL enum *type names* (treatmenttype / treatmentstatus) are also
intentionally preserved on disk to avoid touching PG enum types; the ORM
declares them explicitly via Enum(..., name=...).

This migration deliberately does NOT touch the audit_log table. Historical
audit rows containing "risk.treatment.*" action strings remain intact for
audit-trail completeness; only newly emitted events use "risk.response.*".

Revision ID: 7b2e9a4c5d3f
Revises: 4f1b2c3d8e9a
Create Date: 2026-05-12 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic
revision: str = '7b2e9a4c5d3f'
down_revision: Union[str, None] = '4f1b2c3d8e9a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop the old index first; recreate under the new name after the table is
    # renamed. batch_alter_table is required for the column rename so that
    # SQLite (which lacks ALTER COLUMN) can recreate the table via copy.
    op.drop_index(
        op.f('ix_risk_treatments_risk_id'),
        table_name='risk_treatments',
    )
    op.rename_table('risk_treatments', 'risk_responses')

    with op.batch_alter_table('risk_responses') as batch_op:
        batch_op.alter_column(
            'treatment_type',
            new_column_name='response_type',
        )

    op.create_index(
        op.f('ix_risk_responses_risk_id'),
        'risk_responses',
        ['risk_id'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f('ix_risk_responses_risk_id'),
        table_name='risk_responses',
    )

    with op.batch_alter_table('risk_responses') as batch_op:
        batch_op.alter_column(
            'response_type',
            new_column_name='treatment_type',
        )

    op.rename_table('risk_responses', 'risk_treatments')

    op.create_index(
        op.f('ix_risk_treatments_risk_id'),
        'risk_treatments',
        ['risk_id'],
        unique=False,
    )
