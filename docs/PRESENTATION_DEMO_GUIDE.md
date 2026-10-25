# HydraSense — Presentation & Demo Guide

> **Goal:** a demo that shows only what actually works, survives a dead broker or missing data, and
> leaves you with honest answers when something fails on stage.
>
> Read [FEATURE_STATUS.md](FEATURE_STATUS.md) before choosing screens. Several authority pages are
> UI prototypes built on `mockData`; clicking them during a technical viva invites questions the code
> cannot answer.

---

## 1. The 10-minute demo (recommended)

| # | Time | What you show | What you say |
|---|---|---|---|
| 1 | 0:00–1:00 | Slide: architecture diagram from [PROJECT_GUIDE.md](PROJECT_GUIDE.md#3-system-architecture) | "Four layers: ESP32 station, MQTT, FastAPI + PostgreSQL + ML, React SPA with three surfaces." |
| 2 | 1:00–2:30 | **Public QR page** — open `http://localhost:5173/public/source/ARK-001` (no login) | "Anyone who scans the station QR sees the latest reading, provenance, trend and the six-use suitability assessment. No credentials, and diagnostics are excluded by the response schema." |
| 3 | 2:30–4:00 | **Authority login** → `/authority/monitoring` | "Real backend station list, telemetry link state, provenance badge, ML analysis, suitability and the station QR." |
| 4 | 4:00–5:30 | **Telemetry card**: point at the "Uncalibrated / Sensor failed / Simulated" states | "NULL means no honest measurement. The schema, API and UI all preserve that; nothing is defaulted to 'safe'." |
| 5 | 5:30–7:00 | **ML analysis card + model health** (`/authority/analytics`, Model Health card is real) | "Two models run live at ingestion; a third is offline only. The health card reads the evaluation report, including the 99.99 % benchmark accuracy *and* the XGBoost balanced accuracy of 0.5376." |
| 6 | 7:00–8:30 | **Live ingestion** — run the simulator or publish a payload, then refresh | "New reading → validation → duplicate guard → assessment → ML → visible in the API and the card." |
| 7 | 8:30–10:00 | **Proof of verification** — terminal: `python -m pytest ml/tests -q` or show `ml/reports/evaluation_report.md` | "140 ML tests, 152 backend tests, 61 frontend tests. Every metric in the report is recomputed from artifacts, not typed in." |

---

## 2. Pre-flight checklist (do this 30 minutes before)

Run every command from the repository root.

### 2.1 Services

```bash
# 1. PostgreSQL running and migrated
cd backend
alembic upgrade head
python scripts/seed_demo.py          # ARK-001..003, authority user, product device HS-KIT-000124
python scripts/seed_ml_readings.py   # demo readings that already carry ML results

# 2. Backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

```bash
# 3. Frontend (second terminal)
cd frontend
npm run dev            # http://localhost:5173
```

```bash
# 4. Broker (only needed for live telemetry)
# Windows service installed by Mosquitto; confirm with:
netstat -ano | grep :1883
```

> **Never** start the backend with `python run_server.py` — it refuses to serve without an import
> string. Always `python -m uvicorn app.main:app`.

### 2.2 Smoke checks (each should return 200 / expected JSON)

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/
# 200

curl -s http://127.0.0.1:8000/api/public/stations/ARK-001 | head -c 300
# station JSON including water_source

curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/api/authority/stations
# 401 — RBAC is live (this is the correct answer without a token)
```

Login and keep the token:

```bash
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"authority@hydrasense.local","password":"DemoAuthority123!"}' \
  | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

curl -s -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8000/api/authority/stations/ARK-001/readings/latest/analysis | head -c 600
# reading + ml block (anomaly_label, water_quality_label, probabilities)
```

If the `ml` block is all `null`, that reading was stored without inference — see §5.

### 2.3 Open these tabs in advance

1. `http://localhost:5173/public/source/ARK-001`
2. `http://localhost:5173/user/login`
3. `http://localhost:5173/authority/monitoring`
4. `http://127.0.0.1:8000/docs` (FastAPI swagger — proves the API surface)
5. A terminal with `ml/reports/evaluation_report.md` open

---

## 3. Live ingestion segment (the part that impresses)

### Option A — simulator (needs Mosquitto)

```bash
python backend/simulator/sensor_simulator.py --scenario sudden_event --interval 5
```

Expected backend log:

```
Ingested SensorReading id=... for station='ARK-001' source='simulator' (pH=..., turbidity=..., unit=ntu, ...)
Suitability assessments stored for SensorReading id=... (6 uses)
ML results stored for SensorReading id=...
```

Then refresh `/authority/monitoring` (or re-call the latest-analysis endpoint) and point at the new
timestamp.

### Option B — one manual MQTT packet (no hardware)

```bash
mosquitto_pub -h localhost -t "hydrasense/stations/ARK-001/telemetry" -m \
'{"station_code":"ARK-001","device_id":"DEMO-ESP32-01","timestamp":"2026-10-24T10:15:30Z","pH":7.1,"turbidity":4.0,"tds":200.0,"temperature":25.0,"source":"esp32"}'
```

Note: `source:"esp32"` makes it **hardware-like**, so suitability will actually compare it (if the
payload is treated as calibrated — for a strict demo prefer the simulator, which is explicitly
non-comparable).

### Option C — no broker at all

Show the ingestion path in code (`backend/app/services/mqtt_service.py: process_telemetry_payload`)
and run the ingestion tests instead:

```bash
cd backend && python -m pytest tests/test_telemetry.py -v
```

This is honest: "the broker is not running in this room, so I'm showing the contract tests that
exercise the same function the subscriber calls."

---

## 4. Talking track for the two numbers everyone asks about

**"99.99 % accuracy?"**

> "That is the Random Forest reconstructing the benchmark dataset's own label rule on a held-out
> split of the same static table — two errors in 15,120 rows. It is not evidence of field accuracy,
> and the report says so. The realistic number in the same report is the XGBoost deterioration model:
> 94 % accuracy but balanced accuracy 0.54 and Unsafe recall 0.11, because the series is 91 % one
> class. We publish both."

**"Is the anomaly model trained on real data?"**

> "No. It is trained on six telemetry rows exported from the simulator — a pipeline demonstration.
> The artifact loads, serves and stores results correctly, but its anomaly rate (4 of 9) is
> descriptive, not a validated detection rate. That is the top item in our remaining-work list."

---

## 5. Failure modes and what to say

| Symptom | Likely cause | Recovery line |
|---|---|---|
| Public page shows "Station not found" | Backend not seeded, or wrong station code | `python scripts/seed_demo.py`; use `ARK-001`/`ARK-002`/`ARK-003` |
| Login fails | Backend down or DB not migrated | Check `http://127.0.0.1:8000/`; `alembic upgrade head`; reseed |
| Telemetry card says "No data" | No readings for that station | Run `seed_ml_readings.py` or publish a packet |
| ML card says "Analysis unavailable" | Reading stored without inference (NULL input, relative-index turbidity, or ML artifacts missing) | "This is the designed behaviour — the API refuses to fabricate a prediction." Then show a reading that has `ml_processed_at` set |
| `/authority/ml/status` reports `evaluation_available: false` | `ml/reports/evaluation_report.json` missing | `python ml/scripts/build_evaluation_report.py` |
| Simulator logs nothing | Mosquitto not running / wrong host | `netstat -ano \| grep :1883`; start the service; check `MQTT_BROKER_HOST` in `backend/.env` |
| Authority pages look empty | You opened a mock page (Alerts, Incidents, Inspections, Laboratory, Sources, Analytics) | Switch to Monitoring / Command Center / Map; those have real API calls |
| QR points at localhost | `VITE_PUBLIC_BASE_URL` unset | Set it to your LAN URL (`http://192.168.x.x:5173`) and restart Vite if you want a phone to open it |

**Never** debug live by editing code. Switch to the fallback demo below.

---

## 6. Five-minute fallback demo (no services)

If the backend, database or broker refuses to cooperate:

1. **Show the contract** — `backend/app/schemas/water.py` (NULL semantics, `turbidity_unit`) and
   `backend/app/services/water_suitability.py` (BIS/CPCB criteria, result codes).
2. **Show the proof** — terminal:
   ```bash
   python -m pytest backend/tests -q      # 152 passed
   python -m pytest ml/tests -q           # 140 passed
   ```
3. **Show the metrics** — `ml/reports/evaluation_report.md`, including the limitations block.
4. **Show the cleaning audit** — `ml/reports/dataset_cleaning_report.md`: 140,809 rows, sources
   unmodified, zero rows needed removal, and why that is the honest result.
5. **Show the UI with a static preview** — `cd frontend && npm run build && npm run preview`, or the
   screenshots you captured beforehand.

---

## 7. Do / Don't

| Do | Don't |
|---|---|
| Say "predicted class on the benchmark dataset" | Say "the AI says the water is safe" |
| Say "unusual pattern" for anomalies | Say "contamination detected" |
| Say "provisional relative turbidity index 0–100" for ESP32 | Say "turbidity in NTU" for hardware readings |
| Say "specific conductance" for USGS parameter 95 | Say "TDS from USGS" |
| Say "firmware implemented and contract-tested" | Claim a hardware deployment you did not run |
| Show Model Health, Telemetry, ML, Suitability, Map, Public page | Wander into Alerts/Incidents/Inspections/Lab during the technical demo |
| Mention 353 passing tests | Claim "95 % test coverage" (no coverage report exists) |
| Quote the cleaning run's real numbers | Claim "we cleaned thousands of dirty records" (0 were removed) |

---

## 8. Suggested slide order (12 slides)

1. Problem + one-sentence solution
2. Architecture (Mermaid diagram from the project guide)
3. Hardware + MQTT contract (show one real JSON packet)
4. Ingestion pipeline (validation → dedupe → store → assess → infer)
5. Database schema (ER diagram)
6. Standards-based suitability (BIS/CPCB table + result codes)
7. ML pipeline (three datasets → three models)
8. Metrics **with the honesty frame** (table: accuracy vs balanced accuracy vs recall)
9. Public QR workflow (screenshot of `ARK-001` page)
10. Product-user workflow (account, device binding, device list — mark the check flow as prototype)
11. Verification evidence (353 tests, 6-dataset cleaning audit, reproducible evaluation report)
12. Limitations + five remaining tasks (from the audit report)
