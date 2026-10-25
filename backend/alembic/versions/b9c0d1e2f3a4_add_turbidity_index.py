"""add_turbidity_index

Revision ID: b9c0d1e2f3a4
Revises: a8c9d0e1f2b3
Create Date: 2026-10-24

Adds a DEDICATED `turbidity_index` column for the analog turbidity sensor's
relative 0-100 index (higher = cloudier), kept strictly separate from
`turbidity` when that row's unit is NTU (`turbidity_unit = 'ntu'`).

Backfill: every existing row whose `turbidity_unit` is
'relative_index_0_100' gets its value copied into `turbidity_index`.
NTU rows and rows with unknown unit (NULL) stay NULL — a relative index
is never invented from an NTU reading.

Reversible: drops the column only.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b9c0d1e2f3a4'
down_revision: Union[str, Sequence[str], None] = 'a8c9d0e1f2b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'sensor_readings',
        sa.Column('turbidity_index', sa.Float(), nullable=True),
    )
    # Backfill ONLY rows already tagged as the relative 0-100 index.
    op.execute(
        "UPDATE sensor_readings "
        "SET turbidity_index = turbidity "
        "WHERE turbidity_unit = 'relative_index_0_100' AND turbidity IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_column('sensor_readings', 'turbidity_index')
