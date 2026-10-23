"""add_hardware_telemetry_source_and_diagnostics

Revision ID: b7e6f0a1c2d3
Revises: a1b2c3d4e5f6
Create Date: 2026-10-22

ESP32 hardware integration. Physical stations report RAW analog values that
cannot be honestly converted to pH/NTU/ppm before calibration, so the four
sensor columns become nullable (NULL = "no honest measurement", never "safe").
Existing rows are unaffected (they already carry full values).

Adds:
- source        -> 'simulator' (default; covers all existing rows and the
                    Python simulator) or 'esp32' (physical hardware), keeping
                    simulated and physical readings distinguishable.
- diagnostics   -> optional JSON blob with raw ADC counts, measured voltages,
                    calibration status per sensor, and device health data
                    (uptime, Wi-Fi RSSI, error list).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7e6f0a1c2d3'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Sensor values nullable + provenance/diagnostics columns."""
    op.alter_column('sensor_readings', 'ph',
                    existing_type=sa.Float(), nullable=True)
    op.alter_column('sensor_readings', 'turbidity',
                    existing_type=sa.Float(), nullable=True)
    op.alter_column('sensor_readings', 'tds',
                    existing_type=sa.Float(), nullable=True)
    op.alter_column('sensor_readings', 'temperature',
                    existing_type=sa.Float(), nullable=True)

    op.add_column('sensor_readings', sa.Column(
        'source', sa.String(length=20), nullable=False, server_default='simulator'))
    op.add_column('sensor_readings', sa.Column(
        'diagnostics', sa.JSON(), nullable=True))


def downgrade() -> None:
    """Remove new columns; restore NOT NULL (fails if NULLs exist — by design)."""
    op.drop_column('sensor_readings', 'diagnostics')
    op.drop_column('sensor_readings', 'source')
    op.alter_column('sensor_readings', 'temperature',
                    existing_type=sa.Float(), nullable=False)
    op.alter_column('sensor_readings', 'tds',
                    existing_type=sa.Float(), nullable=False)
    op.alter_column('sensor_readings', 'turbidity',
                    existing_type=sa.Float(), nullable=False)
    op.alter_column('sensor_readings', 'ph',
                    existing_type=sa.Float(), nullable=False)
