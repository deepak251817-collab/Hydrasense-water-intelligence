"""add_turbidity_unit_and_status

Revision ID: c3d4e5f6a7b8
Revises: b7e6f0a1c2d3
Create Date: 2026-10-24

Turbidity means two different things in this system:

- simulator readings carry NTU-style values (the simulator models NTU);
- ESP32 hardware readings carry a PROVISIONAL RELATIVE INDEX 0-100
  (higher = cloudier), which is NOT NTU.

Storing both in one numeric column without a unit invites silent
misinterpretation, so each row now records the unit it was published with.

Adds (nullable, non-destructive — existing rows keep every value):
- turbidity_unit    -> 'relative_index_0_100' | 'ntu' | NULL (unknown)
- turbidity_status  -> CLEARER | MODERATE | CLOUDIER | NULL

Historical attribution (only where it can be derived honestly):
- source='simulator' with a turbidity value -> 'ntu' (the simulator explicitly
  models NTU-style turbidity);
- source='esp32' rows whose diagnostics JSON carries
  diagnostics.turbidity.unit -> that unit, and relative_status -> status.

Anything else stays NULL = unit unknown. No value is re-interpreted as a
relative index, and no row is deleted or rewritten numerically.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b7e6f0a1c2d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('sensor_readings', sa.Column(
        'turbidity_unit', sa.String(length=32), nullable=True))
    op.add_column('sensor_readings', sa.Column(
        'turbidity_status', sa.String(length=16), nullable=True))

    # The Python simulator explicitly models NTU-style turbidity, so its rows
    # can be attributed honestly.
    op.execute(
        "UPDATE sensor_readings SET turbidity_unit = 'ntu' "
        "WHERE source = 'simulator' AND turbidity IS NOT NULL"
    )

    # Hardware rows: only adopt a unit the device itself tagged in diagnostics.
    # JSON operators differ between backends (tests use SQLite in-memory tables
    # created by SQLAlchemy, so this migration only runs on a real database).
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        op.execute(
            "UPDATE sensor_readings "
            "SET turbidity_unit = diagnostics->'turbidity'->>'unit', "
            "    turbidity_status = diagnostics->'turbidity'->>'relative_status' "
            "WHERE source <> 'simulator' "
            "  AND turbidity IS NOT NULL "
            "  AND diagnostics->'turbidity'->>'unit' = 'relative_index_0_100'"
        )


def downgrade() -> None:
    """Remove the unit/status columns (numeric values are untouched)."""
    op.drop_column('sensor_readings', 'turbidity_status')
    op.drop_column('sensor_readings', 'turbidity_unit')
