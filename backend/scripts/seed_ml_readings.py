"""Seed demo sensor readings for the Phase 7 manual UI verification.

Creates a handful of realistic readings per station and runs the REAL Phase 6
ML service on each (Isolation Forest + Random Forest) before storing — exactly
the path MQTT telemetry takes. No fabricated ML values: probabilities and
labels come from the trained models.

Readings are chosen so the UI verification can exercise:
- normal readings   -> Safe + normal condition
- turbidity spike   -> different model outputs, visible in the UI
- one station left without readings (ARK-003) so the "no data" state is real
"""
import os
import sys

sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))

from datetime import datetime, timedelta, timezone

from app.core.database import SessionLocal
from app.models.water import MonitoringStation, SensorReading
from app.services.ml_service import ml_service as svc_module


def main() -> None:
    db = SessionLocal()
    try:
        svc = svc_module if svc_module.is_available or svc_module.load_models() else None
        if svc is None:
            print("[ERROR] ML service unavailable — models could not be loaded.")
            sys.exit(1)
        print("[*] ML service ready: models loaded.")

        stations = {s.station_code: s for s in db.query(MonitoringStation).all()}
        if not stations:
            print("[ERROR] No monitoring stations found. Run scripts/seed_demo.py first.")
            sys.exit(1)

        now = datetime.now(timezone.utc)
        base = now - timedelta(hours=3)

        # (station_code, minutes_after_base, ph, turbidity, tds, temperature)
        readings_spec = [
            ("ARK-001", 0,   7.2,  2.1, 210.0, 25.4),
            ("ARK-001", 60,  7.15, 2.4, 215.0, 25.6),
            ("ARK-001", 120, 7.1,  2.2, 212.0, 25.5),
            ("ARK-001", 180, 7.18, 2.6, 218.0, 25.7),
            ("ARK-002", 0,   6.8,  14.0, 520.0, 27.9),
            ("ARK-002", 60,  6.7,  28.0, 640.0, 28.4),
            ("ARK-002", 120, 6.6,  45.0, 780.0, 28.9),
            ("ARK-002", 180, 6.4,  60.0, 900.0, 29.3),
        ]

        created = 0
        for code, offset, ph, turb, tds, temp in readings_spec:
            station = stations.get(code)
            if station is None:
                print(f"[!] Station {code} not found — skipping.")
                continue
            result = svc.predict(ph=ph, turbidity=turb, tds=tds, temperature=temp)
            reading = SensorReading(
                station_id=station.id,
                device_id=f"SIM-{code}",
                timestamp=base + timedelta(minutes=offset),
                ph=ph,
                turbidity=turb,
                tds=tds,
                temperature=temp,
                anomaly_label=result.anomaly_label,
                anomaly_score=result.anomaly_score,
                water_quality_label=result.water_quality_label,
                safe_probability=result.safe_probability,
                unsafe_probability=result.unsafe_probability,
                ml_processed_at=now,
            )
            db.add(reading)
            created += 1
            print(
                f"  [+] {code} ph={ph} turb={turb} tds={tds} temp={temp} -> "
                f"anomaly={result.anomaly_label} score={result.anomaly_score:.3f} "
                f"quality={result.water_quality_label} "
                f"(safe={result.safe_probability:.3f}/unsafe={result.unsafe_probability:.3f})"
            )

        db.commit()
        print(f"[SUCCESS] Seeded {created} readings with real ML inference.")
        print("[NOTE] ARK-003 intentionally left with no readings (no-data state).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
