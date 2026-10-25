"""add_water_suitability_assessments

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-10-24

Adds derived, standards-based suitability assessments (BIS IS 10500 and CPCB
Designated Best Use criteria). Original readings are untouched; one row per
(reading, intended use, ruleset version).

Reversible: downgrade drops only this table.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'water_suitability_assessments',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('station_id', sa.Integer(), nullable=False),
        sa.Column('reading_id', sa.Integer(), nullable=True),
        sa.Column('use_code', sa.String(length=40), nullable=False),
        sa.Column('standard_code', sa.String(length=60), nullable=False),
        sa.Column('standard_version', sa.String(length=20), nullable=False),
        sa.Column('result_code', sa.String(length=40), nullable=False),
        sa.Column('result_label', sa.String(length=255), nullable=False),
        sa.Column('summary', sa.Text(), nullable=False),
        sa.Column('parameters', sa.JSON(), nullable=True),
        sa.Column('missing_parameters', sa.JSON(), nullable=True),
        sa.Column('measured_values', sa.JSON(), nullable=True),
        sa.Column('data_quality', sa.JSON(), nullable=True),
        sa.Column('limitations', sa.JSON(), nullable=True),
        sa.Column('reading_timestamp', sa.DateTime(timezone=True), nullable=True),
        sa.Column('assessed_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['station_id'], ['monitoring_stations.id']),
        sa.ForeignKeyConstraint(['reading_id'], ['sensor_readings.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('reading_id', 'use_code', 'standard_version',
                            name='uq_suitability_reading_use_version'),
    )
    op.create_index(op.f('ix_water_suitability_assessments_id'),
                    'water_suitability_assessments', ['id'])
    op.create_index(op.f('ix_water_suitability_assessments_station_id'),
                    'water_suitability_assessments', ['station_id'])
    op.create_index(op.f('ix_water_suitability_assessments_reading_id'),
                    'water_suitability_assessments', ['reading_id'])
    op.create_index(op.f('ix_water_suitability_assessments_use_code'),
                    'water_suitability_assessments', ['use_code'])
    op.create_index(op.f('ix_water_suitability_assessments_result_code'),
                    'water_suitability_assessments', ['result_code'])


def downgrade() -> None:
    op.drop_index(op.f('ix_water_suitability_assessments_result_code'),
                  table_name='water_suitability_assessments')
    op.drop_index(op.f('ix_water_suitability_assessments_use_code'),
                  table_name='water_suitability_assessments')
    op.drop_index(op.f('ix_water_suitability_assessments_reading_id'),
                  table_name='water_suitability_assessments')
    op.drop_index(op.f('ix_water_suitability_assessments_station_id'),
                  table_name='water_suitability_assessments')
    op.drop_index(op.f('ix_water_suitability_assessments_id'),
                  table_name='water_suitability_assessments')
    op.drop_table('water_suitability_assessments')
