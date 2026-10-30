"""Dependency-free PDF report rendering.

The project does not ship a PDF library and adding one is unnecessary for a
plain text report, so this module writes a minimal, valid PDF 1.4 document
with the base-14 Helvetica fonts (WinAnsi encoding). It is deliberately small:

- ``render_pdf(paragraphs)`` takes ``(text, style)`` pairs and returns bytes;
- styles are ``title`` / ``heading`` / ``body`` / ``small``;
- long text is wrapped and pages break automatically;
- every page carries the supplied footer (the screening disclaimer).

No images, tables or fonts are embedded. Callers must pass text only; values
are copied from stored records and never synthesised here.
"""

from __future__ import annotations

import textwrap
from datetime import datetime, timezone
from io import BytesIO
from typing import Iterable, List, Sequence, Tuple

PAGE_WIDTH = 595.28
PAGE_HEIGHT = 841.89
MARGIN = 48.0
BODY_SIZE = 9.0

_STYLES = {
    "title": (15.0, "F2"),
    "heading": (10.5, "F2"),
    "body": (BODY_SIZE, "F1"),
    "small": (7.5, "F1"),
}

Line = Tuple[str, float, str]  # (text, font size, resource name)


def _safe_text(text: str) -> str:
    """Encode to the PDF font's WinAnsi repertoire and escape literals."""

    text = (
        str(text)
        .replace("\r", " ")
        .replace("\t", "    ")
        .encode("cp1252", "replace")
        .decode("cp1252")
    )
    return (
        text.replace("\\", "\\\\")
        .replace("(", "\\(")
        .replace(")", "\\)")
    )


def _wrap(paragraph: str, size: float) -> List[str]:
    width = max(20, int((PAGE_WIDTH - 2 * MARGIN) / (size * 0.5)))
    lines: List[str] = []
    for raw in str(paragraph).split("\n"):
        wrapped = textwrap.wrap(raw, width=width) or [""]
        lines.extend(wrapped)
    return lines


def _layout(paragraphs: Iterable[Tuple[str, str]]) -> List[Line]:
    lines: List[Line] = []
    for text, style in paragraphs:
        size, resource = _STYLES.get(style, _STYLES["body"])
        for chunk in _wrap(text, size):
            lines.append((chunk, size, resource))
        if style in ("title", "heading"):
            lines.append(("", BODY_SIZE, "F1"))
    return lines or [("", BODY_SIZE, "F1")]


def _paginate(lines: Sequence[Line]) -> List[List[Line]]:
    usable = PAGE_HEIGHT - 2 * MARGIN - 14  # leave room for the footer
    pages: List[List[Line]] = []
    current: List[Line] = []
    used = 0.0
    for line in lines:
        height = line[1] + 3.5
        if current and used + height > usable:
            pages.append(current)
            current = []
            used = 0.0
        current.append(line)
        used += height
    pages.append(current or [("", BODY_SIZE, "F1")])
    return pages


def _page_stream(page: Sequence[Line], page_number: int, total_pages: int, footer: str) -> bytes:
    commands: List[str] = []
    y = PAGE_HEIGHT - MARGIN
    for text, size, resource in page:
        y -= size + 3.5
        if text:
            commands.append(
                "BT /%s %.2f Tf 1 0 0 1 %.2f %.2f Tm (%s) Tj ET"
                % (resource, size, MARGIN, y, _safe_text(text))
            )

    footer_text = "%s — page %d of %d" % (footer, page_number, total_pages)
    commands.append(
        "BT /F1 7.5 Tf 1 0 0 1 %.2f 26 Tm (%s) Tj ET"
        % (MARGIN, _safe_text(footer_text))
    )
    return "\n".join(commands).encode("cp1252", "replace")


def render_pdf(
    paragraphs: Iterable[Tuple[str, str]],
    *,
    title: str = "HydraSense incident report",
    footer: str = "Preliminary screening, not a laboratory safety certification.",
) -> bytes:
    """Render ``(text, style)`` paragraphs to PDF bytes."""

    pages = _paginate(_layout(paragraphs))
    total_pages = len(pages)

    # Object numbering (1-based):
    #   1 catalog, 2 pages tree, 3 Helvetica, 4 Helvetica-Bold, 5 info,
    #   6 + 2*i page object, 7 + 2*i content stream.
    first_page_object = 6
    kids = " ".join(
        f"{first_page_object + 2 * i} 0 R" for i in range(total_pages)
    )

    objects: List[bytes] = []
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(
        ("<< /Type /Pages /Kids [%s] /Count %d >>" % (kids, total_pages)).encode("ascii")
    )
    objects.append(
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
        b"/Encoding /WinAnsiEncoding >>"
    )
    objects.append(
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold "
        b"/Encoding /WinAnsiEncoding >>"
    )

    created = datetime.now(timezone.utc).strftime("D:%Y%m%d%H%M%S+00'00'")
    info = (
        "<< /Title (%s) /Author (HydraSense) /Creator (HydraSense) "
        "/CreationDate (%s) >>" % (_safe_text(title), created)
    )
    objects.append(info.encode("cp1252", "replace"))

    for index, page in enumerate(pages):
        content_number = first_page_object + 2 * index + 1
        objects.append(
            (
                "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %.2f %.2f] "
                "/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> "
                "/Contents %d 0 R >>"
                % (PAGE_WIDTH, PAGE_HEIGHT, content_number)
            ).encode("ascii")
        )
        stream = _page_stream(page, index + 1, total_pages, footer)
        objects.append(
            b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream"
        )

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets: List[int] = [0] * (len(objects) + 1)
    for number, body in enumerate(objects, start=1):
        offsets[number] = len(out)
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"

    xref_position = len(out)
    out += b"xref\n0 %d\n" % (len(objects) + 1)
    out += b"0000000000 65535 f \n"
    for number in range(1, len(objects) + 1):
        out += b"%010d 00000 n \n" % offsets[number]

    out += (
        b"trailer\n<< /Size %d /Root 1 0 R /Info 5 0 R >>\n"
        b"startxref\n%d\n%%%%EOF\n"
        % (len(objects) + 1, xref_position)
    )
    return bytes(out)


def pdf_bytes_stream(data: bytes) -> BytesIO:
    """Wrap rendered bytes for ``StreamingResponse``/``Response`` callers."""

    return BytesIO(data)
