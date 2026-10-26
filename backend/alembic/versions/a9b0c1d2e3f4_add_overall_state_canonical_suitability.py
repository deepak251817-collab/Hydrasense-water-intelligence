"""add canonical overall_state to product and live assessments

Revision ID: a9b0c1d2e3f4
Revises: e7f8a9b0c1d2
Create Date: 2026-10-26

Adds the canonical four-state suitability vocabulary column
(within_configured_ranges | caution | outside_configured_ranges |
insufficient_data) to ``product_water_tests`` and ``live_water_assessments``
and backfills it from each row's stored assessment JSON so historical records
stay readable with the same vocabulary as new ones. The original
``overall_status`` column is preserved unchanged.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a9b0c1d2e3f4"
down_revision: Union[str, Sequence[str], None] = "e7f8a9b0c1d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Legacy overall_status -> canonical state (mirrors services/screening_states.py).
_STATUS_TO_STATE = {
    "WITHIN_PROJECT_TARGETS": "within_configured_ranges",
    "REVIEW_RECOMMENDED": "caution",
    "NOT_RECOMMENDED_BY_SCREENING": "outside_configured_ranges",
    "INCONCLUSIVE": "insufficient_data",
}


def _backfill(table: str) -> None:
    for legacy, state in _STATUS_TO_STATE.items():
        op.execute(
            sa.text(
                f"UPDATE {table} SET overall_state = :state "
                "WHERE overall_status = :legacy AND overall_state IS NULL"
            ).bindparams(state=state, legacy=legacy)
        )
    # Anything unexpected stays NULL rather than being guessed.
    op.execute(
        sa.text(
            f"UPDATE {table} SET overall_state = 'insufficient_data' "
            "WHERE overall_status NOT IN :statuses AND overall_state IS NULL"
        ).bindparams(statuses=tuple(_STATUS_TO_STATE))
    )


def upgrade() -> None:
    for table in ("product_water_tests", "live_water_assessments"):
        op.add_column(
            table,
            sa.Column("overall_state", sa.String(length=40), nullable=True),
        )
        op.create_index(
            op.f(f"ix_{table}_overall_state"), table, ["overall_state"]
        )
        _backfill(table)


def downgrade() -> None:
    for table in ("live_water_assessments", "product_water_tests"):
        op.drop_index(op.f(f"ix_{table}_overall_state"), table_name=table)
        op.drop_column(table, "overall_state")
