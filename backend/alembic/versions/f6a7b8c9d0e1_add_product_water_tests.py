"""add_product_water_tests

Revision ID: f6a7b8c9d0e1
Revises: d4e5f6a7b8c9
Create Date: 2026-10-24

Adds private product-user water tests: the four measured values, reading
provenance (live ESP32 vs. explicitly labelled simulation), the selected water
source/intended use and the complete rule-based assessment with its criteria
version.

Reversible: downgrade drops only this table.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'product_water_tests',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('device_id', sa.String(length=100), nullable=False),
        sa.Column('sensor_reading_id', sa.Integer(), nullable=True),
        sa.Column('water_source', sa.String(length=32), nullable=False),
        sa.Column('intended_use', sa.String(length=32), nullable=False),
        sa.Column('reading_mode', sa.String(length=16), nullable=False),
        sa.Column('reading_source', sa.String(length=20), nullable=False),
        sa.Column('ph', sa.Float(), nullable=True),
        sa.Column('tds', sa.Float(), nullable=True),
        sa.Column('turbidity', sa.Float(), nullable=True),
        sa.Column('turbidity_unit', sa.String(length=32), nullable=True),
        sa.Column('temperature', sa.Float(), nullable=True),
        sa.Column('reading_timestamp', sa.DateTime(timezone=True), nullable=True),
        sa.Column('overall_status', sa.String(length=40), nullable=False),
        sa.Column('criteria_version', sa.String(length=40), nullable=False),
        sa.Column('assessment', sa.JSON(), nullable=False),
        sa.Column('summary_text', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['sensor_reading_id'], ['sensor_readings.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_product_water_tests_id'),
                    'product_water_tests', ['id'])
    op.create_index(op.f('ix_product_water_tests_user_id'),
                    'product_water_tests', ['user_id'])
    op.create_index(op.f('ix_product_water_tests_device_id'),
                    'product_water_tests', ['device_id'])
    op.create_index(op.f('ix_product_water_tests_intended_use'),
                    'product_water_tests', ['intended_use'])
    op.create_index(op.f('ix_product_water_tests_reading_timestamp'),
                    'product_water_tests', ['reading_timestamp'])
    op.create_index(op.f('ix_product_water_tests_overall_status'),
                    'product_water_tests', ['overall_status'])
    op.create_index('ix_product_water_tests_user_created',
                    'product_water_tests', ['user_id', 'created_at'])


def downgrade() -> None:
    op.drop_index('ix_product_water_tests_user_created',
                  table_name='product_water_tests')
    op.drop_index(op.f('ix_product_water_tests_overall_status'),
                  table_name='product_water_tests')
    op.drop_index(op.f('ix_product_water_tests_reading_timestamp'),
                  table_name='product_water_tests')
    op.drop_index(op.f('ix_product_water_tests_intended_use'),
                  table_name='product_water_tests')
    op.drop_index(op.f('ix_product_water_tests_device_id'),
                  table_name='product_water_tests')
    op.drop_index(op.f('ix_product_water_tests_user_id'),
                  table_name='product_water_tests')
    op.drop_index(op.f('ix_product_water_tests_id'),
                  table_name='product_water_tests')
    op.drop_table('product_water_tests')
