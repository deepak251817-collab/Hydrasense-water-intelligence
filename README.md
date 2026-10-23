# HydraSense Water Intelligence

An AI-powered water quality intelligence and predictive response system. IoT sensor telemetry (pH, turbidity, TDS, temperature) flows over MQTT into a FastAPI backend, is persisted to PostgreSQL, enriched in-place with machine-learning results, and surfaced through a React dashboard for authorities and the public.

> [!IMPORTANT]
> **Data honesty policy**: ML outputs are model predictions, not laboratory confirmation. Simulator telemetry is for system development and stress testing — it is **not** scientific ground truth. A missing analysis is rendered as "Analysis unavailable", never as "Safe" or "Normal". See [Scientific Honesty & Limitations](#scientific-honesty--limitations).

---

## Key Features

- **IoT telemetry ingestion** — MQTT subscriber validates payloads (station, device, timestamp, pH, turbidity, TDS, temperature), rejects unknown stations, de-duplicates retries by `(device_id, timestamp)`, and commits readings to PostgreSQL before ML runs (ingestion is never blocked by ML).
- **Honest turbidity units** — every reading stores its turbidity unit: ESP32 hardware sends a **provisional relative index 0–100** (higher = cloudier, *not* NTU), the simulator sends NTU, and rows with no unit stay “unknown”. The dashboard labels each case explicitly and never mixes units on one chart.
- **Live ML inference on every reading** — Isolation Forest anomaly scoring + Random Forest Safe/Unsafe classification, written back to the same `sensor_readings` row. If ML fails or artifacts are missing, the reading is stored with NULL ML fields — **no fabricated predictions**.
- **Role-based access control** — JWT authentication (Argon2 password hashing) with two roles: `AUTHORITY` and `PRODUCT_USER`. ML analysis endpoints are authority-only; public endpoints expose no model internals.
- **Authority dashboard** — command center, live monitoring, water map, station detail with AI analysis, alerts, incidents, inspections, laboratory, and analytics views.
- **Public transparency pages** — water check, nearby sources, warnings, and QR/scannable source pages with no ML internals exposed.
- **Explainable AI** — SHAP explanations (global + local) for both tree models, with model-independence verification (predictions bit-identical before/after explanation).
- **Sensor simulator** — configurable scenarios (`normal`, `deteriorating`, `sudden_event`, `sensor_fault`) publishing to MQTT for end-to-end testing.

---

## Architecture

```
Sensor Simulator (or real devices)
        │  MQTT  (topic: hydrasense/stations/<station_code>/telemetry)
        ▼
FastAPI backend — MQTT subscriber
        │  Phase 4 range validation → PostgreSQL commit (telemetry first)
        │  → ML inference (Isolation Forest → Random Forest)
        │  → ML columns updated on the same sensor_readings row
        ▼
REST API  (/api/auth, /api/public, /api/product, /api/authority)
        ▼
React frontend (Vite + TypeScript) — public pages, user portal, authority dashboard
```

---

## Tech Stack

| Layer     | Technologies |
|-----------|--------------|
| Backend   | Python, FastAPI, SQLAlchemy 2.0, Alembic, PostgreSQL, paho-mqtt, PyJWT, Argon2, Uvicorn |
| Frontend  | React 19, TypeScript, Vite, Tailwind CSS 4, shadcn/ui, react-router-dom 7, TanStack Query, Recharts, Vitest |
| ML        | pandas, scikit-learn 1.4.2, XGBoost, SHAP, joblib, matplotlib |
| Infra     | Mosquitto (or any MQTT 3.1.1 broker), PostgreSQL 14+ |

---

## Repository Layout

```
├── backend/
│   ├── app/
│   │   ├── api/v1/          # auth, public, product, authority routers
│   │   ├── core/            # config, database, security
│   │   ├── models/          # User, WaterSource/MonitoringStation/SensorReading, ProductDevice
│   │   ├── schemas/         # Pydantic schemas
│   │   └── services/        # mqtt_service (ingestion), ml_service (inference)
│   ├── alembic/             # migrations (ML columns, hardware source/diagnostics, turbidity units)
│   ├── scripts/             # seed_demo.py, seed_ml_readings.py
│   ├── simulator/           # sensor_simulator.py (MQTT telemetry generator)
│   └── tests/               # pytest suite (in-memory SQLite, no DB setup needed)
├── frontend/
│   └── src/
│       ├── pages/public/    # Home, WaterCheck, NearbySources, Warnings, MyChecks, PublicSource
│       ├── pages/user/      # Login, Register, Activate, Dashboard, Devices, History
│       ├── pages/authority/ # CommandCenter, LiveMonitoring, WaterMap, StationDetail, Alerts, …
│       └── lib/             # typed API client (incl. ML analysis), hooks
├── firmware/
│   ├── README.md            # ESP32 wiring, toolchain, calibration, dashboard checks
│   └── hydrasense_esp32/    # hydrasense_esp32.ino + config.example.h (config.h is git-ignored)
├── ml/
│   ├── preprocessing/       # cleaning, features, supervised & forecasting prep
│   ├── scripts/             # export → clean → split → train → evaluate → predict → explain
│   ├── models/              # persisted .joblib artifacts (served by the backend)
│   ├── data/                # raw / processed / external (USGS, benchmark datasets)
│   └── tests/               # 140+ ML tests (leakage, reproducibility, persistence)
├── requirements.txt         # backend dependencies
└── pytest.ini
```

---

## Getting Started

### Prerequisites

- Python 3.11+
- PostgreSQL 14+
- An MQTT broker (e.g. Mosquitto) on `localhost:1883`
- Node.js 20.19+ (Vite 8 requirement) and npm

### 1. Database

```bash
createdb hydrasense   # or: postgres -U postgres -c "CREATE DATABASE hydrasense"
```

### 2. Backend

```bash
pip install -r requirements.txt

cd backend
cp .env.example .env          # set DATABASE_URL, JWT_SECRET_KEY, etc.
alembic upgrade head          # create schema (incl. ML result columns)
python scripts/seed_demo.py   # demo authority account + water sources/stations
python run_server.py          # http://127.0.0.1:8000  (docs at /docs)
```

Demo account created by the seeder:

- **Authority**: `authority@hydrasense.local` / `DemoAuthority123!`

Backend environment variables (`backend/.env`):

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg2://postgres:postgres@localhost:5432/hydrasense` | PostgreSQL connection string |
| `JWT_SECRET_KEY` | — | Set a secure value in production |
| `JWT_ALGORITHM` | `HS256` | JWT signing algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | Token lifetime |
| `MQTT_BROKER_HOST` / `MQTT_BROKER_PORT` | `localhost` / `1883` | Broker address |
| `MQTT_TOPIC_PREFIX` | `hydrasense/stations` | Telemetry topic prefix |

### 3. MQTT broker

```bash
mosquitto          # default listener on localhost:1883
```

### 4. Sensor simulator (optional, for live telemetry)

```bash
python backend/simulator/sensor_simulator.py --scenario normal          # infinite loop, 5s interval
python backend/simulator/sensor_simulator.py --scenario deteriorating --count 20
# scenarios: normal | deteriorating | sudden_event | sensor_fault
```

### 5. ML models

The backend loads artifacts from `ml/models/` at startup (verified once, never retrained):

- `isolation_forest.joblib` — anomaly detection (`ph`, `turbidity`, `tds`, `temperature`)
- `random_forest_classifier.joblib` — Safe/Unsafe classification (`pH`, `tds`, `turbidity`, `temperature`)

If artifacts are missing, the API logs that ML is unavailable and **ingestion continues normally** with NULL ML fields. To (re)train them, follow [ml/README.md](ml/README.md).

### 6. Frontend

```bash
cd frontend
cp .env.example .env    # VITE_API_BASE_URL=http://127.0.0.1:8000/api
npm install
npm run dev             # Vite dev server (http://localhost:5173)
```

Frontend environment variables (`frontend/.env`):

| Variable | Default | Description |
|---|---|---|
| `VITE_API_BASE_URL` | `http://127.0.0.1:8000/api` | Backend API base URL |

### 7. ESP32 hardware station (optional)

Full wiring, toolchain and safety instructions: **[firmware/README.md](firmware/README.md)**.

- Board: ESP32 DevKit V1 + ADS1115 (I²C SDA=21, SCL=22, gain ±4.096 V) + DS18B20 on GPIO 4.
- Copy `firmware/hydrasense_esp32/config.example.h` → `config.h` (git-ignored) and fill in Wi-Fi/MQTT credentials, `STATION_CODE` (seeded: `ARK-001`, `ARK-002`, `ARK-003`) and `DEVICE_ID`.
- Never commit `config.h` — it holds Wi-Fi/MQTT secrets.
- Firmware publishes every 3 s, waits for NTP time before publishing, and reconnects Wi-Fi/MQTT non-blockingly with backoff (`WIFI_RETRY_MS`, `MQTT_RETRY_MS`).
- Turbidity is read from ADS1115 A2 through the 10 kΩ/20 kΩ divider, averaged over 10 samples, and published as a **provisional relative index 0–100** (not NTU).

---

## MQTT Telemetry Contract

**Topic:** `hydrasense/stations/<STATION_CODE>/telemetry` (subscriber uses `hydrasense/stations/+/telemetry`, QoS 1).

ESP32 payload (null = no honest measurement; `source` keeps hardware distinguishable from simulator rows):

```json
{
  "station_code": "ARK-001",
  "device_id": "ESP32-HS-001",
  "timestamp": "2026-10-24T10:00:00Z",
  "pH": 7.02,
  "turbidity": 68.2,
  "turbidity_status": "CLOUDIER",
  "turbidity_unit": "relative_index_0_100",
  "tds": 214.3,
  "temperature": 27.1,
  "source": "esp32",
  "diagnostics": {
    "turbidity": {
      "unit": "relative_index_0_100",
      "raw_adc": 8431,
      "voltage_v": 1.054,
      "sensor_output_v": 1.581,
      "relative_index": 68.2,
      "relative_status": "CLOUDIER",
      "calibration_status": "provisional_index"
    },
    "device": { "uptime_ms": 69112, "wifi_rssi_dbm": -41, "seq": 7, "errors": [] }
  }
}
```

Simulator payload (NTU-style values, unit stated explicitly, no diagnostics):

```json
{
  "station_code": "ARK-001",
  "device_id": "STATION-ARK-001",
  "timestamp": "2026-10-24T10:00:00+00:00",
  "pH": 7.1,
  "turbidity": 4.8,
  "turbidity_unit": "ntu",
  "tds": 210.0,
  "temperature": 26.5
}
```

Rules enforced by the subscriber:

- required: `station_code`, `device_id`, `timestamp` (ISO-8601 **with time**), `pH`, `turbidity`, `tds`, `temperature`;
- a sensor value may be `null` (uncalibrated/failed) but must be numeric otherwise; booleans/strings/objects are rejected;
- ranges: pH 0–14, TDS/turbidity ≥ 0, temperature −20–70 °C; relative-index turbidity additionally 0–100;
- `turbidity_unit` / `turbidity_status` may be top-level or inside `diagnostics.turbidity`; unknown units are stored as `NULL`, never assumed NTU;
- one row per `(device_id, timestamp)` — redeliveries are skipped;
- `source` is persisted so users can distinguish `esp32` from `simulator`.

---

## Machine Learning Pipeline

Full details, measured metrics, and phase-by-phase documentation live in **[ml/README.md](ml/README.md)**. Summary:

| Model | Task | Data | Status |
|---|---|---|---|
| Isolation Forest | Unsupervised anomaly scoring | Station telemetry (chronological 70/15/15 split) | **Live** (served by backend) |
| Random Forest | Safe/Unsafe classification | 100,800-row external benchmark (stratified splits) | **Live** (served by backend) |
| XGBoost | Future deterioration prediction | Real USGS time series (station USGS-01649190, 5-min interval) | Offline analysis only |
| SHAP | Model explainability (TreeExplainer) | Both tree models | Offline; no live explanation API yet |

The XGBoost model requires `specific_conductance` plus USGS lag/rolling features that live TDS telemetry does not provide, so it is deliberately **not** connected to live inference.

Run the ML pipeline (see ml/README.md for the full ordered command list):

```bash
python ml/scripts/export_sensor_data.py        # extract telemetry from PostgreSQL
python ml/scripts/train_isolation_forest.py
python ml/scripts/train_random_forest.py
python ml/scripts/explain_random_forest.py --verify-consistency
```

---

## Testing

```bash
# Backend (pytest, in-memory SQLite — no PostgreSQL or broker needed)
python -m pytest backend/tests -v

# ML pipeline (140+ tests: leakage, reproducibility, persistence, SHAP)
python -m pytest ml/tests -v

# Frontend (Vitest + Testing Library)
cd frontend && npm test

# Frontend production build + lint
cd frontend && npm run build && npm run lint
```

The backend suite exercises the real MQTT payload parser and subscriber callbacks (malformed JSON, non-object payloads, missing fields, null sensor values, retry de-duplication, relative-index validation, API responses). No broker, PostgreSQL instance, or physical device is required for it.

---

## API Overview

Base URL: `http://127.0.0.1:8000/api` — interactive docs at [`/docs`](http://127.0.0.1:8000/docs).

| Prefix | Access | Highlights |
|---|---|---|
| `/api/auth` | Public | register, login, token issuance |
| `/api/public` | Public | water sources, warnings, source pages — **no ML internals** |
| `/api/product` | `PRODUCT_USER` | product-user devices and checks |
| `/api/authority` | `AUTHORITY` | stations, readings, alerts, incidents, map, analytics |
| `/api/authority/readings/{id}/analysis` | `AUTHORITY` | reading + ML analysis (NULL fields if not analysed) |
| `/api/authority/stations/{code}/readings/latest/analysis` | `AUTHORITY` | latest reading + ML analysis for a station |

ML analysis responses contain `anomaly_label` (0 = normal, 1 = anomalous condition), `anomaly_score`, `water_quality_label` ("Safe"/"Unsafe" predicted), `safe_probability`/`unsafe_probability`, and `ml_processed_at`. Internal model paths and parameters are never exposed.

---

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| Backend log: `Rejected telemetry for unknown station_code` | Seed the station (`python scripts/seed_demo.py`) or use an existing code (`ARK-001`–`ARK-003`). |
| Backend log: `Invalid timestamp format` | Send full ISO-8601 with time, e.g. `2026-10-24T10:00:00Z`; a bare date is rejected. |
| Backend log: `Invalid or empty station_code` / `Missing required field` | Payload does not match the contract above. |
| Telemetry accepted but dashboard card says **No data** | No row for that station yet; check the selected station and `authority` login. |
| Card says **Unauthorized** | Log in with an authority account; raw hardware telemetry is authority-only. |
| Card says **Stale/Offline** | Last row older than 15 s / 5 min — check device power, Wi-Fi, broker (`mosquitto_sub -h localhost -t "hydrasense/stations/#" -v`). |
| Serial: `[ADS] ERROR: ADS1115 not found` | I²C wiring/address; analog values publish `null` with a `device.errors` entry instead of fake numbers. |
| Serial: `[TIME] NTP not synced yet` | Normal for the first seconds after boot; publishing starts once time is valid. |
| Dashboard shows `(unit unknown)` | Row predates unit tracking; it is intentionally not labelled NTU or relative index. |
| `alembic upgrade head` fails on diagnostics backfill | Run against PostgreSQL 12+ (JSON operators); the backfill is skipped on other dialects. |

---

## Scientific Honesty & Limitations

This project deliberately constrains its claims:

- **Anomaly ≠ contamination.** Isolation Forest flags readings unusual relative to its training telemetry; it does not confirm chemical contamination.
- **Predicted class ≠ potability.** The Random Forest reproduces the labeling rules of its benchmark dataset; it is not laboratory confirmation or a guarantee of safety.
- **Simulator data is not ground truth.** Scenario names exist for pipeline testing only and are never used as scientific labels.
- **Four sensors have limits.** Heavy metals, microplastics, pharmaceuticals, and microbial pathogens that do not affect pH/TDS/turbidity/temperature cannot be detected by these parameters alone.
- **Forecasting honesty.** The XGBoost deterioration target is a rule-based indicator on a single USGS station (~5 weeks synchronized); temporal performance drop from validation to test is documented, not tuned away.
- **No fabricated results.** Missing ML artifacts, failed inference, or pre-ML readings all produce NULL ML fields, rendered in the UI as "Analysis unavailable".
- **Turbidity is not always NTU.** ESP32 hardware reports a **provisional relative index 0–100** anchored to two sample-based sensor voltages (≈0.354 V clear, ≈0.273 V cloudy). It is a relative trend indicator, **not** a calibrated NTU measurement and **not** a safety verdict; converting it to NTU requires the two-point calibration in [firmware/README.md](firmware/README.md) §10.
- **Relative turbidity is excluded from ML.** The models were trained on NTU-style turbidity, so relative-index readings are stored and displayed but deliberately keep NULL ML fields.

---

## Project Phases (all complete)

| Phase | Deliverable |
|---|---|
| 4 | Backend API, MQTT ingestion, RBAC, sensor simulator |
| 5A–5B | ML data preparation + Isolation Forest anomaly detection |
| 5C | Supervised dataset prep + Random Forest classification |
| 5D | USGS time-series prep + XGBoost deterioration prediction |
| 5E | SHAP explainable AI |
| 6 | Backend ML inference integration (live models on telemetry) |
| 7 | Frontend ML integration (authority dashboard AI panels) |

---

## License

All rights reserved unless otherwise stated in individual files.
