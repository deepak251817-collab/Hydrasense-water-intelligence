"""add rate_limit_counters table

Revision ID: e7f8a9b0c1d2
Revises: c1d2e3f4a5b6
Create Date: 2026-10-25

Shared fixed-window counters for API rate limiting. Stored in PostgreSQL so
every API worker and every restart observes the same limits.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "e7f8a9b0c1d2"
down_revision: Union[str, Sequence[str], None] = "c1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "rate_limit_counters",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("bucket_key", sa.String(length=255), nullable=False, index=True),
        sa.Column("window_start", sa.Integer(), nullable=False),
        sa.Column("hits", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.UniqueConstraint(
            "bucket_key", "window_start", name="uq_rate_limit_bucket_window"
        ),
    )


def downgrade() -> None:
    op.drop_table("rate_limit_counters")
