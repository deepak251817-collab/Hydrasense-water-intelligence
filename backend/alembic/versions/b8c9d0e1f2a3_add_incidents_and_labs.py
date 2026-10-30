"""incidents, incident_events, lab_contacts and lab_results tables

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-10-30

Authority incident workflow with an append-only audit trail and laboratory
results entered verbatim by authorised users. Laboratory values are never
derived from the four hardware sensors; ``lab_results.results`` stores the
reported measurements as JSON with fixed laboratory provenance.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b8c9d0e1f2a3"
down_revision: Union[str, Sequence[str], None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "lab_contacts",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("organization", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("phone", sa.String(length=60), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("accreditation", sa.String(length=120), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
    )

    op.create_table(
        "incidents",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("reference", sa.String(length=30), nullable=True, unique=True, index=True),
        sa.Column(
            "station_id", sa.Integer(), sa.ForeignKey("monitoring_stations.id"),
            nullable=False, index=True,
        ),
        sa.Column(
            "reading_id", sa.Integer(), sa.ForeignKey("sensor_readings.id"),
            nullable=True, index=True,
        ),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("priority", sa.String(length=20), nullable=False, server_default="medium"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="raised", index=True),
        sa.Column("origin", sa.String(length=20), nullable=False, server_default="manual"),
        sa.Column("alert_reason", sa.Text(), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("explanation_source", sa.String(length=40), nullable=False, server_default="none"),
        sa.Column("time_window_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("time_window_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raised_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column(
            "raised_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column("lab_contact_id", sa.Integer(), sa.ForeignKey("lab_contacts.id"), nullable=True),
        sa.Column(
            "lab_notification_status", sa.String(length=30),
            nullable=False, server_default="not_notified",
        ),
        sa.Column("lab_notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sample_id", sa.String(length=120), nullable=True),
        sa.Column("sample_collected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result_received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_summary", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
    )

    op.create_table(
        "incident_events",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column(
            "incident_id",
            sa.Integer(),
            sa.ForeignKey("incidents.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("from_status", sa.String(length=30), nullable=True),
        sa.Column("to_status", sa.String(length=30), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
    )

    op.create_table(
        "lab_results",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column(
            "incident_id",
            sa.Integer(),
            sa.ForeignKey("incidents.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("lab_contact_id", sa.Integer(), sa.ForeignKey("lab_contacts.id"), nullable=True),
        sa.Column("received_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("sample_id", sa.String(length=120), nullable=False),
        sa.Column("reported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("results", sa.JSON(), nullable=True),
        sa.Column("document_reference", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("lab_results")
    op.drop_table("incident_events")
    op.drop_table("incidents")
    op.drop_table("lab_contacts")
