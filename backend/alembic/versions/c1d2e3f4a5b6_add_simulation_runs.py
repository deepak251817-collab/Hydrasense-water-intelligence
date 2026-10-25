"""add_simulation_runs

Revision ID: c1d2e3f4a5b6
Revises: b9c0d1e2f3a4
Create Date: 2026-10-25

Persistent, shared simulation state: one singleton row (id = 1) stores the
simulation configuration, status, counters and the worker generation lease, so
Start/Pause/Generate stay consistent across API workers and survive restarts.

Reversible: drops only this table (no data owned elsewhere is touched).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c1d2e3f4a5b6'
down_revision: Union[str, Sequence[str], None] = 'b9c0d1e2f3a4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'simulation_runs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('station_code', sa.String(length=100), nullable=True),
        sa.Column('source_code', sa.String(length=100), nullable=True),
        sa.Column('scenario', sa.String(length=40), nullable=False),
        sa.Column('seed', sa.Integer(), nullable=True),
        sa.Column('interval_seconds', sa.Float(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('step', sa.Integer(), nullable=False),
        sa.Column('samples_generated', sa.Integer(), nullable=False),
        sa.Column('worker_id', sa.String(length=64), nullable=True),
        sa.Column('lease_expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_sample_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('simulation_runs')
