"""Per-station QR generation tests.

Rendering is verified structurally: real PNG signature + IHDR dimensions, SVG
geometry matching the module matrix, and a PDF whose xref is valid.
"""

import re
import struct

from app.services import qr_service


def test_qr_metadata_requires_authority(client, seeded_water_data, product_token_headers):
    station = seeded_water_data["station"]
    path = f"/api/authority/stations/{station.station_code}/qr"
    assert client.get(path).status_code == 401
    assert client.get(path, headers=product_token_headers).status_code == 403


def test_qr_metadata_uses_configured_public_base(
    client, seeded_water_data, authority_token_headers, monkeypatch
):
    import app.core.config as config

    monkeypatch.setattr(
        config.settings, "PUBLIC_BASE_URL", "https://water.example.gov/", raising=False
    )
    station = seeded_water_data["station"]
    response = client.get(
        f"/api/authority/stations/{station.station_code}/qr",
        headers=authority_token_headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["station_code"] == station.station_code
    assert (
        body["public_url"]
        == f"https://water.example.gov/public/source/{station.station_code}"
    )
    assert set(body["formats"]) == {"png", "svg", "pdf"}


def test_qr_unknown_station_returns_404(client, authority_token_headers):
    response = client.get(
        "/api/authority/stations/NOPE-1/qr", headers=authority_token_headers
    )
    assert response.status_code == 404


def _png_size(data: bytes) -> tuple:
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    assert data[12:16] == b"IHDR"
    width, height = struct.unpack(">II", data[16:24])
    return width, height


def test_qr_png_is_a_valid_scaled_png(
    client, seeded_water_data, authority_token_headers, monkeypatch
):
    import app.core.config as config

    monkeypatch.setattr(
        config.settings, "PUBLIC_BASE_URL", "https://water.example.gov", raising=False
    )
    station = seeded_water_data["station"]
    url = qr_service.public_station_url(station.station_code)
    matrix = qr_service.qr_matrix(url)

    response = client.get(
        f"/api/authority/stations/{station.station_code}/qr.png?module_size=8",
        headers=authority_token_headers,
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "image/png"
    width, height = _png_size(response.content)
    assert width == height == len(matrix) * 8

    smaller = client.get(
        f"/api/authority/stations/{station.station_code}/qr.png?module_size=4",
        headers=authority_token_headers,
    )
    assert _png_size(smaller.content) == (len(matrix) * 4, len(matrix) * 4)


def test_qr_svg_modules_match_matrix(
    client, seeded_water_data, authority_token_headers
):
    station = seeded_water_data["station"]
    matrix = qr_service.qr_matrix(
        qr_service.public_station_url(station.station_code)
    )
    dark = sum(1 for row in matrix for cell in row if cell)

    response = client.get(
        f"/api/authority/stations/{station.station_code}/qr.svg",
        headers=authority_token_headers,
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")
    body = response.text
    assert body.startswith('<?xml version="1.0"')
    assert body.count("<rect ") == dark + 1  # modules + white background
    expected_size = len(matrix) * 8
    assert f'width="{expected_size}"' in body


def test_qr_pdf_is_structurally_valid(
    client, seeded_water_data, authority_token_headers, monkeypatch
):
    import app.core.config as config

    monkeypatch.setattr(
        config.settings, "PUBLIC_BASE_URL", "https://water.example.gov", raising=False
    )
    station = seeded_water_data["station"]
    response = client.get(
        f"/api/authority/stations/{station.station_code}/qr.pdf",
        headers=authority_token_headers,
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    text = response.content.decode("latin-1")
    assert text.startswith("%PDF-1.4")

    xref = int(re.search(r"startxref\n(\d+)\n%%EOF", text).group(1))
    tail = text[xref:].splitlines()
    assert tail[0] == "xref"
    assert tail[1] == "0 " + tail[1].split()[1]
    count = int(tail[1].split()[1])
    for number in range(1, count):
        offset = int(tail[2 + number].split()[0])
        assert text[offset:].split("\n", 1)[0] == f"{number} 0 obj"

    assert station.station_code in text
    assert "public/source/" in text


def test_different_stations_produce_different_codes():
    a = qr_service.qr_matrix("https://example.gov/public/source/AAAA-1")
    b = qr_service.qr_matrix("https://example.gov/public/source/BBBB-2")
    assert a != b
    assert len(a[0]) == len(b[0])  # same version for equal-length payloads


def test_svg_escapes_module_geometry_only_and_contains_no_scripts():
    from app.services.qr_service import render_svg

    svg = render_svg(qr_service.qr_matrix("https://example.gov/x"))
    assert "<script" not in svg
    assert "javascript:" not in svg
