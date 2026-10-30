from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Notification(Base):
    """Delivery log for one user notification.

    Every row records what was composed, why (category + dedup key), the
    requested severity, and the delivery outcome. Email is the only implemented
    channel; other channels remain pluggable and are not pretended to exist.

    ``status``:
      - ``sent``                 — delivered by the configured channel
      - ``skipped_unconfigured`` — no channel configured (SMTP_HOST empty)
      - ``failed``               — channel configured but delivery raised
      - ``deduped``              — suppressed by the cooldown/dedup window
                                   (kept for the delivery log)
    """

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    channel: Mapped[str] = mapped_column(String(30), nullable=False, default="email")
    category: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="warning")
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    # Identical dedup_key + user inside the cooldown window is suppressed.
    dedup_key: Mapped[Optional[str]] = mapped_column(String(200), index=True, nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="skipped_unconfigured")
    payload_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship("User")  # noqa: F821


class NotificationPreference(Base):
    """Per-user opt-out per notification category (row absent = enabled)."""

    __tablename__ = "notification_preferences"

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    channel: Mapped[str] = mapped_column(String(30), nullable=False, default="email")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        UniqueConstraint("user_id", "category", "channel", name="uq_notification_pref"),
    )
