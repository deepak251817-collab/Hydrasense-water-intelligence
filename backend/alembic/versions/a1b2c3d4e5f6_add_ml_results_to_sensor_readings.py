"""add_ml_results_to_sensor_readings

Revision ID: a1b2c3d4e5f6
Revises: 579c2249f273
Create Date: 2026-09-13

Phase 6 — ML Backend Integration. Adds nullable ML result columns to
sensor_readings so ML outputs stay associated with the reading that produced
them. Existing rows keep NULL ML fields (no backfilled fabrications).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '579c2249f273'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add ML result columns (all nullable: readings may predate ML or fail inference)."""
    op.add_column('sensor_readings', sa.Column('anomaly_label', sa.Integer(), nullable=True))
    op.add_column('sensor_readings', sa.Column('anomaly_score', sa.Float(), nullable=True))
    op.add_column('sensor_readings', sa.Column('water_quality_label', sa.String(length=20), nullable=True))
    op.add_column('sensor_readings', sa.Column('safe_probability', sa.Float(), nullable=True))
    op.add_column('sensor_readings', sa.Column('unsafe_probability', sa.Float(), nullable=True))
    op.add_column('sensor_readings', sa.Column('ml_processed_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Remove ML result columns."""
    op.drop_column('sensor_readings', 'ml_processed_at')
    op.drop_column('sensor_readings', 'unsafe_probability')
    op.drop_column('sensor_readings', 'safe_probability')
    op.drop_column('sensor_readings', 'water_quality_label')
    op.drop_column('sensor_readings', 'anomaly_score')
    op.drop_column('sensor_readings', 'anomaly_label')
