"""device_number registry columns and the first personal device

Revision ID: f1e2d3c4b5a6
Revises: a9b0c1d2e3f4
Create Date: 2026-10-30

Adds printable device numbers (``device_number``, unique) and the installed
``station_code`` to ``product_devices``, backfills existing rows
deterministically, and seeds the first personal device
(HSD-0001-K7M2Q9 -> device ESP32-HS-001 at station ARK-001) when it is absent.
The seed insert is guarded so it never duplicates on re-runs and never
violates the ``device_id``/``product_code`` uniqueness constraints.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import hashlib


revision: str = "f1e2d3c4b5a6"
down_revision: Union[str, Sequence[str], None] = "a9b0c1d2e3f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 5 alphanumerics derived from the product_code so backfill is deterministic
# and collision-free (id-zero-padded + truncated hash).
_SUFFIX_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _device_number_for(row_id: int, product_code: str) -> str:
    digest = hashlib.sha256(product_code.strip().upper().encode("utf-8")).hexdigest()
    suffix = "".join(
        _SUFFIX_ALPHABET[int(digest[i : i + 2], 16) % len(_SUFFIX_ALPHABET)]
        for i in range(0, 8, 2)
    )
    return f"HSD-{row_id:04d}-{suffix}"


def upgrade() -> None:
    conn = op.get_bind()
    op.add_column(
        "product_devices",
        sa.Column("device_number", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "product_devices",
        sa.Column("station_code", sa.String(length=50), nullable=True),
    )
    op.create_index("ix_product_devices_device_number", "product_devices", ["device_number"])
    op.create_index("ix_product_devices_station_code", "product_devices", ["station_code"])

    # Unique index on the printable device number (NULLs may repeat in SQL, but
    # a printed number must be globally unique once assigned).
    rows = conn.execute(
        sa.text(
            "SELECT id, product_code FROM product_devices WHERE device_number IS NULL"
        )
    ).fetchall()
    for row_id, product_code in rows:
        conn.execute(
            sa.text(
                "UPDATE product_devices SET device_number = :num WHERE id = :id"
            ),
            {"num": _device_number_for(row_id, product_code), "id": row_id},
        )
    op.create_unique_constraint(
        "uq_product_devices_device_number", "product_devices", ["device_number"]
    )

    conn.execute(
        sa.text(
            """
            INSERT INTO product_devices
                (product_code, device_id, device_number, station_code,
                 device_type, status, owner_id, activated_at)
            SELECT
                :product_code, :device_id, :device_number, :station_code,
                'PERSONAL_WATER_TESTER', 'PENDING_ACTIVATION', NULL, NULL
            WHERE NOT EXISTS (
                SELECT 1 FROM product_devices
                WHERE device_id = :device_id OR product_code = :product_code
                   OR device_number = :device_number
            )
            """
        ),
        {
            "product_code": "HS-KIT-000125",
            "device_id": "ESP32-HS-001",
            "device_number": "HSD-0001-K7M2Q9",
            "station_code": "ARK-001",
        },
    )


def downgrade() -> None:
    op.drop_constraint("uq_product_devices_device_number", "product_devices", type_="unique")
    op.drop_index("ix_product_devices_station_code", "product_devices")
    op.drop_index("ix_product_devices_device_number", "product_devices")
    # Keep the seeded device row (data preservation); only drop the columns.
    op.drop_column("product_devices", "device_number")
    op.drop_column("product_devices", "station_code")
