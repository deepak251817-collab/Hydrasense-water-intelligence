"""Per-station public QR codes.

The stable public URL is ``{PUBLIC_BASE_URL}/public/source/{station_code}`` —
the same QR-page route the React app serves, so a printed code keeps working
as long as the station code and public origin do.

Rendering avoids an imaging dependency:

- ``qrcode`` produces the module matrix (the only third-party dependency);
- SVG is generated directly from the matrix;
- PNG is written with the standard library (zlib + struct, 8-bit grayscale);
- PDF reuses ``incident_pdf`` and draws the modules as vector rectangles.
"""

from __future__ import annotations

import struct
import zlib
from typing import Dict, List, Sequence
from urllib.parse import quote

import qrcode

from app.core.config import settings
from app.services.incident_pdf import PAGE_WIDTH, render_pdf

QR_ERROR_CORRECTION = qrcode.constants.ERROR_CORRECT_M
QUIET_ZONE_MODULES = 4


def public_station_url(station_code: str) -> str:
    """Stable public page URL for a station code (never a signed/one-off link)."""

    base = (settings.PUBLIC_BASE_URL or "").strip().rstrip("/")
    return f"{base}/public/source/{quote(station_code, safe='')}"


def qr_matrix(data: str, *, border: int = QUIET_ZONE_MODULES) -> List[List[bool]]:
    qr = qrcode.QRCode(
        version=None,
        error_correction=QR_ERROR_CORRECTION,
        box_size=1,
        border=border,
    )
    qr.add_data(data)
    qr.make(fit=True)
    return qr.get_matrix()


def render_svg(matrix: Sequence[Sequence[bool]], *, module_size: int = 8) -> str:
    size = len(matrix) * module_size
    rects: List[str] = []
    for y, row in enumerate(matrix):
        for x, cell in enumerate(row):
            if cell:
                rects.append(
                    f'<rect x="{x * module_size}" y="{y * module_size}" '
                    f'width="{module_size}" height="{module_size}"/>'
                )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 {size} {size}" shape-rendering="crispEdges">'
        '<desc>HydraSense public station page QR code</desc>'
        f'<rect width="100%" height="100%" fill="#ffffff"/>'
        f'<g fill="#000000">{"".join(rects)}</g>'
        "</svg>\n"
    )


def render_png(matrix: Sequence[Sequence[bool]], *, module_size: int = 8) -> bytes:
    """8-bit grayscale PNG from the module matrix, standard library only."""

    width = len(matrix[0]) * module_size
    height = len(matrix) * module_size

    raw = bytearray()
    for row in matrix:
        line = bytearray()
        for cell in row:
            line.extend((0 if cell else 255).to_bytes(1, "big") * module_size)
        for _ in range(module_size):
            raw.append(0)  # filter type 0 (None)
            raw.extend(line)

    def chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    header = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + chunk(b"IEND", b"")
    )


def _pdf_overlay(matrix: Sequence[Sequence[bool]], module_pt: float) -> List[str]:
    size = len(matrix) * module_pt
    x0 = (PAGE_WIDTH - size) / 2
    y0 = 170.0
    commands: List[str] = []
    for y, row in enumerate(matrix):
        for x, cell in enumerate(row):
            if not cell:
                continue
            px = x0 + x * module_pt
            py = y0 + (len(matrix) - 1 - y) * module_pt
            commands.append(
                "%.2f %.2f %.2f %.2f re f" % (px, py, module_pt, module_pt)
            )
    return commands


def render_pdf_label(
    *, station_code: str, station_name: str, public_url: str, module_pt: float = 5.0
) -> bytes:
    """Printable label: station identity, public URL and the QR code."""

    matrix = qr_matrix(public_url)
    paragraphs = [
        ("HydraSense public water-quality page", "title"),
        (station_name, "heading"),
        (f"Station {station_code}", "body"),
        ("Scan to open:", "body"),
        (public_url, "body"),
        (
            "The public page shows the four measured parameters (pH, TDS, "
            "temperature, relative turbidity index), data freshness and "
            "rule-based suitability screening for drinking, domestic, swimming "
            "and agricultural uses. It is a preliminary screening, not a "
            "laboratory safety certification.",
            "small",
        ),
    ]
    return render_pdf(
        paragraphs,
        title=f"HydraSense QR — {station_code}",
        footer=(
            "HydraSense — public screening page. Not a laboratory safety "
            "certification."
        ),
        overlay_commands=_pdf_overlay(matrix, module_pt),
    )


def station_qr_payload(station_code: str, station_name: str) -> Dict[str, object]:
    return {
        "station_code": station_code,
        "station_name": station_name,
        "public_url": public_station_url(station_code),
        "formats": {"png": "image/png", "svg": "image/svg+xml", "pdf": "application/pdf"},
    }
