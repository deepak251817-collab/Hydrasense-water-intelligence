"""Authority-only QR generation for station public pages."""

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_authority
from app.core.database import get_db
from app.models.user import User
from app.services import qr_service
from app.services.incident_service import get_station

router = APIRouter(prefix="/authority", tags=["Authority QR"])


@router.get("/stations/{station_code}/qr")
def get_station_qr_metadata(
    station_code: str,
    current_user: User = Depends(get_current_authority),
    db: Session = Depends(get_db),
):
    """Stable public URL + available download formats for one station."""

    station = get_station(db, station_code)
    return qr_service.station_qr_payload(station.station_code, station.station_name)


@router.get("/stations/{station_code}/qr.png")
def download_station_qr_png(
    station_code: str,
    module_size: int = Query(8, ge=2, le=24),
    current_user: User = Depends(get_current_authority),
    db: Session = Depends(get_db),
):
    station = get_station(db, station_code)
    matrix = qr_service.qr_matrix(
        qr_service.public_station_url(station.station_code)
    )
    return Response(
        content=qr_service.render_png(matrix, module_size=module_size),
        media_type="image/png",
        headers={
            "Content-Disposition": f'attachment; filename="{station.station_code}-qr.png"'
        },
    )


@router.get("/stations/{station_code}/qr.svg")
def download_station_qr_svg(
    station_code: str,
    module_size: int = Query(8, ge=2, le=24),
    current_user: User = Depends(get_current_authority),
    db: Session = Depends(get_db),
):
    station = get_station(db, station_code)
    matrix = qr_service.qr_matrix(
        qr_service.public_station_url(station.station_code)
    )
    return Response(
        content=qr_service.render_svg(matrix, module_size=module_size),
        media_type="image/svg+xml",
        headers={
            "Content-Disposition": f'attachment; filename="{station.station_code}-qr.svg"'
        },
    )


@router.get("/stations/{station_code}/qr.pdf")
def download_station_qr_pdf(
    station_code: str,
    current_user: User = Depends(get_current_authority),
    db: Session = Depends(get_db),
):
    station = get_station(db, station_code)
    pdf = qr_service.render_pdf_label(
        station_code=station.station_code,
        station_name=station.station_name,
        public_url=qr_service.public_station_url(station.station_code),
    )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{station.station_code}-qr.pdf"'
        },
    )
