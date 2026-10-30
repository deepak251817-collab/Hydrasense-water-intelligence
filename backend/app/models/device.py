from datetime import datetime
from typing import TYPE_CHECKING, Optional
from sqlalchemy import String, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class ProductDevice(Base):
    __tablename__ = "product_devices"

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    product_code: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    device_id: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    # Human-readable number printed on the physical device (e.g. HSD-0001-K7M2Q9).
    # Unique so a printed number can act as a login/activation identifier.
    device_number: Mapped[Optional[str]] = mapped_column(String(64), unique=True, index=True, nullable=True)
    # Station the personal device is installed at (e.g. ARK-001), if any.
    station_code: Mapped[Optional[str]] = mapped_column(String(50), index=True, nullable=True)
    device_type: Mapped[str] = mapped_column(String(100), nullable=False, default="PERSONAL_WATER_TESTER")
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="PENDING_ACTIVATION")
    owner_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    activated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    owner: Mapped[Optional["User"]] = relationship("User", back_populates="devices")
