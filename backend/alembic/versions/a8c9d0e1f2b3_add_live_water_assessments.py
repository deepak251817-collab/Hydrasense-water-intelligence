"""add_live_water_assessments

Revision ID: a8c9d0e1f2b3
Revises: f6a7b8c9d0e1
Create Date: 2026-10-24

Stores stable-reading assessments produced by the authority Live Monitoring
page. One row per (reading, intended use, criteria version); polling the page is
idempotent. Sensor readings themselves are never modified.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a8c9d0e1f2b3'
down_revision: Union[str, Sequence[str], None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'live_water_assessments',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('station_id', sa.Integer(), nullable=False),
        sa.Column('reading_id', sa.Integer(), nullable=True),
        sa.Column('device_id', sa.String(length=100), nullable=False),
        sa.Column('use_code', sa.String(length=32), nullable=False),
        sa.Column('overall_status', sa.String(length=40), nullable=False),
        sa.Column('criteria_version', sa.String(length=40), nullable=False),
        sa.Column('assessment', sa.JSON(), nullable=False),
        sa.Column('reading_timestamp', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['station_id'], ['monitoring_stations.id']),
        sa.ForeignKeyConstraint(['reading_id'], ['sensor_readings.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('reading_id', 'use_code', 'criteria_version',
                            name='uq_live_assessment_reading_use_version'),
    )
    op.create_index(op.f('ix_live_water_assessments_id'),
                    'live_water_assessments', ['id'])
    op.create_index(op.f('ix_live_water_assessments_station_id'),
                    'live_water_assessments', ['station_id'])
    op.create_index(op.f('ix_live_water_assessments_reading_id'),
                    'live_water_assessments', ['reading_id'])
    op.create_index(op.f('ix_live_water_assessments_use_code'),
                    'live_water_assessments', ['use_code'])
    op.create_index(op.f('ix_live_water_assessments_overall_status'),
                    'live_water_assessments', ['overall_status'])


def downgrade() -> None:
    op.drop_index(op.f('ix_live_water_assessments_overall_status'),
                  table_name='live_water_assessments')
    op.drop_index(op.f('ix_live_water_assessments_use_code'),
                  table_name='live_water_assessments')
    op.drop_index(op.f('ix_live_water_assessments_reading_id'),
                  table_name='live_water_assessments')
    op.drop_index(op.f('ix_live_water_assessments_station_id'),
                  table_name='live_water_assessments')
    op.drop_index(op.f('ix_live_water_assessments_id'),
                  table_name='live_water_assessments')
    op.drop_table('live_water_assessments')
