# HydraSense Water Intelligence

An AI-powered water quality intelligence and predictive response system. IoT sensor telemetry (pH, turbidity, TDS, temperature) flows over MQTT into a FastAPI backend, is persisted to PostgreSQL, enriched in-place with machine-learning results, and surfaced through a React dashboard for authorities and the public.

> [!IMPORTANT]
> **Data honesty policy**: ML outputs are model predictions, not laboratory confirmation. Simulator telemetry is for system development and stress testing — it is **not** scientific ground truth. A missing analysis is rendered as "Analysis unavailable", never as "Safe" or "Normal". See [Scientific Honesty & Limitations](#scientific-honesty--limitations).

## Contents

[Quick start](#quick-start-copy-paste) ·
[Accounts, sign-in and what to do after login](#accounts-sign-in-and-what-to-do-after-login) ·
[Getting started](#getting-started) ·
[Datasets and metrics](#datasets-and-how-to-check-accuracy-f1-and-other-metrics) ·
[API overview](#api-overview) ·
[Testing](#testing) ·
[Troubleshooting](#troubleshooting) ·
[Scientific honesty & limitations](#scientific-honesty--limitations)

---

## Key Features

- **IoT telemetry ingestion** — MQTT subscriber validates payloads (station, device, timestamp, pH, turbidity, TDS, temperature), rejects unknown stations, de-duplicates retries by `(device_id, timestamp)`, and commits readings to PostgreSQL before ML runs (ingestion is never blocked by ML).
- **Honest turbidity units** — every reading stores its turbidity unit: both ESP32 hardware and the simulator send a **provisional relative index 0–100** (higher = cloudier, *not* NTU), and rows with no unit stay “unknown”. The dashboard labels each case explicitly and never mixes units on one chart.
- **Live ML inference on every reading** — Isolation Forest anomaly scoring + Random Forest Safe/Unsafe classification, written back to the same `sensor_readings` row. If ML fails or artifacts are missing, the reading is stored with NULL ML fields — **no fabricated predictions**.
- **Role-based access control** — JWT authentication (Argon2 password hashing) with two roles: `AUTHORITY` and `PRODUCT_USER`. ML analysis endpoints are authority-only; public endpoints expose no model internals.
- **Live four-sensor assessment** — Live Monitoring reads the real ESP32/MQTT window, waits for **10 valid samples over 20 s**, checks stability per parameter and runs one shared, explainable screening service for Drinking, Domestic Use, Irrigation or General Non-Potable Use. Stable readings are never treated as calibrated readings.
- **Private product-user tests** — a signed-in product user activates a product code, chooses a water source and intended use, and receives the same screening from their own device's live window (or clearly labelled SIMULATION values). Results are stored per account and are not visible to other users.
- **Authority dashboard** — command center, live monitoring, water map, station detail with AI analysis, alerts, incidents, inspections, laboratory, and analytics views.
- **Public transparency pages** — water check, nearby sources, warnings, and QR/scannable source pages with no ML internals exposed.
- **Explainable AI** — SHAP explanations (global + local) for both tree models, with model-independence verification (predictions bit-identical before/after explanation).
- **Sensor simulator** — configurable scenarios (`normal`, `deteriorating`, `sudden_event`, `sensor_fault`) publishing to MQTT for end-to-end testing, plus an in-app simulation panel (lease-guarded, `source=simulator`) that never mixes with hardware rows.
- **Incident + laboratory workflow** — raise incidents, move them through a forward-only, audited state machine, notify a laboratory and **email it the generated PDF report** (delivery state reported honestly as `sent` / `smtp_unconfigured` / `failed`), record the verbatim lab result and resolve with a summary.

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

## Quick start (copy-paste)

Prerequisites: **Python 3.11+**, **PostgreSQL 14+**, **Node.js 20.19+** and npm. An MQTT broker is
optional — it is only needed for real ESP32 telemetry or the CLI simulator; the in-app simulation
panel and the seeded readings work without one.

```bash
# 1) database
createdb hydrasense

# 2) backend
pip install -r requirements.txt
cd backend
cp .env.example .env            # then set DATABASE_URL and JWT_SECRET_KEY (table below)
python -c "import secrets; print(secrets.token_urlsafe(48))"   # paste as JWT_SECRET_KEY
alembic upgrade head
python scripts/seed_demo.py            # authority account + 3 rivers + stations + product codes
python scripts/seed_ml_readings.py     # optional: a few demo readings so the UI is not empty
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000    # API on :8000, docs at /docs
# `python run_server.py` starts the same server with --reload

# 3) frontend (second terminal)
cd frontend
cp .env.example .env            # VITE_API_BASE_URL=http://127.0.0.1:8000/api
npm install
npm run dev                     # http://localhost:5173
```

Open <http://localhost:5173/public>, click **Authority**, and sign in with the seeded account:

| Seeded account | Credentials |
|---|---|
| Authority | `authority@hydrasense.local` / `DemoAuthority123!` |
| Personal device | printed number `HSD-0001-K7M2Q9` — must be claimed first, see [Accounts](#accounts-sign-in-and-what-to-do-after-login) |

With the backend stopped the SPA still loads, but every API-backed page shows its
"unable to load" state — start the backend for real data.

---

## Documentation

Full audit and presentation material lives in [`docs/`](docs/):

| Document | What it covers |
|---|---|
| [docs/PROJECT_GUIDE.md](docs/PROJECT_GUIDE.md) | Architecture, data flow, ER model, ML pipeline, module walkthrough (Mermaid diagrams) |
| [docs/FEATURE_STATUS.md](docs/FEATURE_STATUS.md) | What is verified, partial, or UI-only — read before demoing |
| [docs/DATASET_CATALOG.md](docs/DATASET_CATALOG.md) | Every dataset with real row counts, ranges and provenance status |
| [docs/DATA_CLEANING_REPORT.md](docs/DATA_CLEANING_REPORT.md) | Exactly which cleaning operations ran, with verification |
| [docs/PRESENTATION_DEMO_GUIDE.md](docs/PRESENTATION_DEMO_GUIDE.md) | 10-minute demo script, pre-flight checks, failure fallbacks |
| [docs/PRESENTATION_QA.md](docs/PRESENTATION_QA.md) | Viva questions with honest technical answers |
| [docs/PROJECT_AUDIT_REPORT.md](docs/PROJECT_AUDIT_REPORT.md) | Audit findings, limitations and the five most urgent remaining tasks |
| [docs/PRE_DEPLOYMENT_REPORT.md](docs/PRE_DEPLOYMENT_REPORT.md) | Read-only pre-deployment audit against the spec: per-area verdict, blockers, should-fix, unable-to-verify |

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
├── docs/                    # audit report, project guide, dataset catalog, demo guide, Q&A
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
cp .env.example .env          # set DATABASE_URL, JWT_SECRET_KEY, CORS_ALLOW_ORIGINS, etc.
                              # JWT_SECRET_KEY is REQUIRED: generate one with
                              #   python -c "import secrets; print(secrets.token_urlsafe(48))"
alembic upgrade head          # create schema (incl. ML columns + rate_limit_counters)
python scripts/seed_demo.py   # demo authority account + water sources/stations
python run_server.py          # http://127.0.0.1:8000  (docs at /docs)
```

Demo account created by the seeder:

- **Authority**: `authority@hydrasense.local` / `DemoAuthority123!`

Backend environment variables (`backend/.env`):

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg2://postgres:postgres@localhost:5432/hydrasense` | PostgreSQL connection string |
| `APP_ENV` | `development` | `production` enables the strict security checks (CORS fail-closed, JWT secret enforced) |
| `JWT_SECRET_KEY` | — (required) | **No default in code.** Generate with `python -c "import secrets; print(secrets.token_urlsafe(48))"` and keep it out of git. Startup fails when unset; in production it also fails when shorter than 32 chars or a known placeholder. Rotating it invalidates all issued tokens. |
| `JWT_ALGORITHM` | `HS256` | JWT signing algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | Token lifetime |
| `CORS_ALLOW_ORIGINS` | empty | Comma-separated explicit frontend origins. Empty = local dev/preview origins outside production, deny-all cross-origin in production. `*` is rejected with credentials and in production. |
| `CORS_ALLOW_CREDENTIALS` | `true` | Must be `false` if you ever try a `*` origin (the API refuses the combination) |
| `RATE_LIMIT_ENABLED` | `true` | Database-backed limiter on `/api/auth/login` and `/api/auth/register` (429 + `Retry-After`) |
| `RATE_LIMIT_TRUST_PROXY_HEADERS` | `false` | Set `true` only behind a reverse proxy you control (uses `X-Forwarded-For`) |
| `RATE_LIMIT_LOGIN_MAX` / `RATE_LIMIT_LOGIN_WINDOW_SECONDS` | `10` / `300` | Login attempts per client per fixed window |
| `RATE_LIMIT_REGISTER_MAX` / `RATE_LIMIT_REGISTER_WINDOW_SECONDS` | `10` / `3600` | Registration attempts per client per fixed window |
| `RATE_LIMIT_ACTIVATE_MAX` / `RATE_LIMIT_ACTIVATE_WINDOW_SECONDS` | `10` / `3600` | Device activation attempts per client per fixed window (stops printed-code enumeration) |
| `MQTT_BROKER_HOST` / `MQTT_BROKER_PORT` | `localhost` / `1883` | Broker address |
| `MQTT_TOPIC_PREFIX` | `hydrasense/stations` | Telemetry topic prefix |
| `MQTT_USERNAME` / `MQTT_PASSWORD` | empty | Broker credentials. **Required in production** (startup refuses anonymous unless `MQTT_ALLOW_ANONYMOUS=true`). Never logged; keep them only in `.env`/the secret manager. |
| `MQTT_USE_TLS` / `MQTT_CA_CERT_PATH` | `false` / empty | Enable broker TLS; empty CA path uses the system trust store. TLS is required as soon as the broker is not loopback (the deployment checker fails otherwise). |
| `MQTT_ALLOW_ANONYMOUS` | `false` | Explicit, development-only opt-in for an anonymous local broker. The production checker always fails it. |
| `PUBLIC_BASE_URL` | `http://localhost:5173` | Public web origin encoded into printed station QR codes. Must be the real HTTPS origin before QR codes are used. |
| `DEMO_STRICT_TDS_RULE` | `true` | Enables the project-specific <200 mg/L drinking-water TDS target. Set `false` to disable it; it never affects domestic, irrigation or general non-potable use. |

### 3. MQTT broker

```bash
mosquitto          # anonymous default listener on localhost:1883 (development only)
```

For any shared or deployed broker, disable anonymous access and add ACLs so a device can only
publish its own station topic while the backend can only subscribe:

```conf
allow_anonymous false
password_file /etc/mosquitto/passwd
acl_file      /etc/mosquitto/acl
```

```conf
user hydrasense-backend
topic read hydrasense/stations/+/telemetry

user device-ark-001
topic write hydrasense/stations/ARK-001/telemetry
```

Set `MQTT_USERNAME` / `MQTT_PASSWORD` in `backend/.env` to match, enable `MQTT_USE_TLS` when the
broker leaves the host, and use a distinct credential per ESP32 station. Full reference and the
real-environment verification checklist: [docs/DEPLOYMENT_VERIFICATION.md](docs/DEPLOYMENT_VERIFICATION.md).

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

**Registering the hardware to ARK-001 — there is no pairing screen.** A station is identified by the `STATION_CODE`/`DEVICE_ID` it publishes, and the station row must already exist:

1. `ARK-001` is seeded by `python backend/scripts/seed_demo.py`; a fresh database needs that seed (or an equivalent `monitoring_stations` row) before any telemetry is accepted.
2. In `firmware/hydrasense_esp32/config.h` set `STATION_CODE "ARK-001"` and a unique `DEVICE_ID` (for example `ESP32-HS-001`), then flash. Unknown station codes are rejected; the device id is recorded on every row.
3. Start the broker and the backend. The firmware publishes to `hydrasense/stations/ARK-001/telemetry` every 3 s.
4. Verify ingestion: `curl http://127.0.0.1:8000/api/public/stations/ARK-001/readings/latest` must return `"source":"esp32"` and a timestamp seconds old. The Live Monitoring card reads the same stored rows.
5. The **Connected / Connecting / Offline** badge is derived from the newest stored reading, not from a pairing step: under 30 s = Connected, 30–120 s = Connecting, over 120 s = Offline. A sensor fault reported in `diagnostics` shows **Error** (and the exact device message) even while rows are arriving — the station is online, one probe is not.
6. A personal account that signs in with a printed `HSD-…` number additionally needs a `product_devices` row carrying that number and `station_code`, claimed with its product code. Without it, device-number login returns 404 even though the station telemetry is flowing.

---

## Accounts, sign-in and what to do after login

HydraSense has three distinct users. Only two of them have accounts.

| Role | How they sign in | Entry point | What they get |
|---|---|---|---|
| **Public / citizen** | no account | `/public` | live values, the use-based suitability result, “needs further testing” wording, QR pages — no ML internals |
| **Authority** | email + password | `/user/login` | monitoring, alerts, forecasts, QR codes, incidents, laboratory contacts and emailed lab reports, PDF reports |
| **Personal / product user** | device number *(API)* or email + password | `/user/login`, `POST /api/auth/device-login` | own device(s), private water checks, alerts, history, notification preferences |

### Signing in as Authority

1. Start the backend and frontend (see [Quick start](#quick-start-copy-paste)).
2. Open <http://localhost:5173/public> and click **Authority** — you land on `/user/login`.
3. Sign in with the seeded account:
   - email `authority@hydrasense.local`
   - password `DemoAuthority123!`

   The account is created by `backend/scripts/seed_demo.py`. It exists for local
demonstration only — rotate or disable it before any deployment.
4. On success the JWT is stored in `sessionStorage` and you are routed to the authority area.
   Opening any `/authority/...` URL while signed out redirects back to `/user/login`.

**What to do after logging in — a 5-minute tour**

| Step | Page | What to do / what to expect |
|---|---|---|
| 1 | **Command Center** `/authority` | Station cards with the latest readings and alert summary. Empty cards mean no readings yet — run the in-app simulation panel (step 7) or publish MQTT telemetry. |
| 2 | **Live Monitoring** `/authority/monitoring` | Pick a station; the stable-window assessment needs 10 samples over 20 s. Choose Drinking / Domestic / Irrigation / General Non-Potable and read the reasons, references and next steps. |
| 3 | **Alerts** `/authority/alerts` | Danger-level alerts with the measured value, the configured reference, the reason and the next step. Acknowledgement is local to the browser session. |
| 4 | **Incidents** `/authority/incidents` | Real incident queue (no mock data). Open an incident → select a laboratory → **Email report to lab**. The PDF report is attached and the delivery state is shown honestly: `Report emailed` / `Email not configured` / `Email failed`. **Download PDF** works even when email is not configured. |
| 5 | **QR Codes** `/authority/qr` | Per-station public URL plus PNG / SVG / PDF download. Set `PUBLIC_BASE_URL` (backend `.env`) to your LAN or deployed origin before scanning from a phone, otherwise the QR encodes `localhost`. |
| 6 | **Analytics** `/authority/analytics` | The forecast card (honest readiness/evaluation gate) and the **Model Health & Evaluation** card with the metrics described in [Datasets and metrics](#datasets-and-how-to-check-accuracy-f1-and-other-metrics). |
| 7 | **Simulation** (floating button, bottom-right on every authority page) | Pick a river and one of the five demo scenarios; generated rows are stored with `source=simulator`, carry the **SIMULATED DATA** label and never trigger real emails or lab messages. |

**Laboratory email requires SMTP.** The incident notification uses the backend SMTP settings; when
`SMTP_HOST` is empty the workflow still advances but records `smtp_unconfigured` and the UI tells
you nothing was emailed. Configure these in `backend/.env`:

| Variable | Purpose |
|---|---|
| `SMTP_HOST` / `SMTP_PORT` | Mail server (port 587 with STARTTLS is the default) |
| `SMTP_USER` / `SMTP_PASSWORD` | Credentials; never logged |
| `SMTP_FROM` | Sender address put on the lab email |
| `SMTP_USE_TLS` | `true` to call `STARTTLS` (default) |

### Signing in as a Personal (product) user

The normal path is email + password, because a printed device number alone must not create an
account:

1. `/user/register` — create the account.
2. `/user/activate` — enter the product code printed on the device. Seeded codes:
   `HS-KIT-000124` (unclaimed) and `HS-KIT-000125` (bound to device number
   `HSD-0001-K7M2Q9`, firmware device `ESP32-HS-001` at `ARK-001`).
3. `/user/dashboard` — the claimed device, alerts and notification preferences.
4. `/user/check-water` — run a screening; `/user/history` — private past checks.

**Device-number sign-in** is implemented as an API endpoint (the login screen currently offers
only email + password):

```bash
curl -s -X POST http://127.0.0.1:8000/api/auth/device-login \
  -H "Content-Type: application/json" \
  -d '{"device_number":"HSD-0001-K7M2Q9"}'
```

The number is case-insensitive. The token is issued to the account the device is **bound** to, so an
unclaimed device returns a generic `404` — activate it first (steps 1–2). Failures are rate-limited
per client and share the login budget, and the response never reveals whether a different number
exists.

### Using the app as the public (no login)

| Page | What it shows |
|---|---|
| `/public` | landing page: Scan QR, Check my water |
| `/public/source/<station_code>` | QR target: live values, turbidity index (never NTU), suitability for drinking / domestic / irrigation |
| `/public/check-water` | the use-based check with an explicit “needs further testing / insufficient data” state |

Nearby-sources and warnings pages still render demonstration records and are labelled accordingly —
do not treat them as live feeds.

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

Simulator payload (relative-index values, unit stated explicitly, no diagnostics):

```json
{
  "station_code": "ARK-001",
  "device_id": "STATION-ARK-001",
  "timestamp": "2026-10-24T10:00:00+00:00",
  "pH": 7.1,
  "turbidity": 22.5,
  "turbidity_unit": "relative_index_0_100",
  "turbidity_status": "CLEARER",
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
python ml/scripts/build_evaluation_report.py   # compute real metrics from saved artifacts
```

### Water Suitability Assessment (BIS IS 10500 / CPCB)

The standards-based assessment lives in `backend/app/services/water_suitability.py` and screens four intended uses: drinking water, domestic use, irrigation and industrial cooling. It compares **only** values that are genuinely comparable:

- physical hardware readings (`source = esp32`) with `calibration_status = calibrated`;
- turbidity only when stored as **NTU** (the ESP32 relative index is never compared);
- readings fresher than 5 minutes (older ones are reported as stale, never as a current conclusion).

Uncalibrated estimates, relative-index turbidity and simulated values are listed as **excluded**, never silently compared. Missing laboratory parameters (microbiology, nitrate, arsenic, DO/BOD/coliform, EC/SAR/boron) are reported as required tests, so the module never calls a sample safe to drink from pH/TDS/turbidity alone.

| Result code | Meaning |
|---|---|
| `preliminary_suitable` | every criterion for the use was measured and within its acceptable limit (never emitted for drinking water) |
| `treatment_required` | a measured value is within the relaxed/permissible limit, or treatment is required by the use |
| `outside_limits` | at least one measured value exceeds the applicable limit |
| `lab_confirmation_required` | measurable criteria pass, but required laboratory parameters are unavailable |
| `insufficient_data` | no comparable measurement, missing critical parameters, or stale data |

Assessments are persisted once per `(reading, use, ruleset version)` in `water_suitability_assessments` (migration `d4e5f6a7b8c9`, reversible). Original readings are never modified. The UI section (`WaterSuitabilitySection`) appears on authority Live Monitoring and on the public QR page.

### Live four-sensor assessment (Live Monitoring + Product User)

`backend/app/services/water_screening.py` is the single rule-based service used by
both `GET /api/authority/stations/{code}/live-assessment` and `POST /api/product/tests`.
It needs only the four existing measurements — pH, TDS, turbidity and temperature.
No extra sensor, dataset or trained model is required for the initial screening.

**Rolling-window stability** (`backend/app/services/sensor_stability.py`) uses the
station's real stored readings and never inserts synthetic values:

| Check | Development setting |
|---|---|
| Window | at least 10 valid samples spanning at least 20 s |
| pH | range ≤ 0.10 |
| TDS | range ≤ max(10 mg/L, 5% of median) |
| Relative turbidity index | range ≤ 5 index points |
| Calibrated NTU | range ≤ max(0.2 NTU, 10% of median) |
| Temperature | range ≤ 0.5 °C |
| Fresh sample | latest reading ≤ 30 s old (firmware publishes every 3 s) |
| Offline | latest reading > 120 s old |

A stable window means only that the values are consistent. **Stability is not
calibration**: the device's per-sensor `calibration_status` is read from telemetry
diagnostics and reported separately. A live test with unverified calibration
returns `INCONCLUSIVE`, never a green pass. Demo values are labelled `SIMULATION`.

**Reference profiles and overall states**

| Intended use | Configured references |
|---|---|
| Drinking | BIS IS 10500:2012: pH 6.5–8.5; TDS 500 mg/L acceptable / 2000 mg/L permissible; turbidity 1 NTU acceptable / 5 NTU permissible (calibrated NTU only). The project adds a **drinking-only** demo target of 200 mg/L. |
| Domestic Use | The same BIS values, with the strict 200 mg/L demo target deliberately **not** applied. Bathing, washing, cleaning and gardening can have different requirements. |
| Irrigation | FAO-style TDS salinity categories: <450 mg/L no restriction indicated, 450–2000 slight-to-moderate, >2000 severe; pH reference 6.5–8.4. TDS is a salinity proxy, not electrical conductivity. |
| General Non-Potable Use | BIS pH 6.5–8.5 as an advisory screening range; TDS and temperature carry **no** pass/fail limit for this use and are shown for context. Outcomes are phrased “Measured indicators are within the configured general (non-potable) screening ranges”, “Caution — further testing or treatment may be needed” or “Unfavourable measured indicators — investigation recommended”. The drinking-only strict TDS target is never applied here. |

Overall states are `WITHIN_PROJECT_TARGETS`, `REVIEW_RECOMMENDED`,
`NOT_RECOMMENDED_BY_SCREENING` and `INCONCLUSIVE`. Every state carries the exact
reasons, references and next steps; `WITHIN_PROJECT_TARGETS` explicitly says that
it does not certify that water is safe to drink.

**Project-specific strict TDS rule (drinking only)**

With `DEMO_STRICT_TDS_RULE=true` (default), a drinking-water TDS below 200 mg/L is
reported as `below_project_target`, and the result headline reads **“Not suitable
by the project's strict TDS target”**. When the same sample also has unverified
calibration or unstable data, the overall state stays `INCONCLUSIVE`, but the
headline and summary still say that TDS is below 200 ppm and why the sample does
not meet the project target — the low-TDS concern is never hidden behind a generic
“more data required” message. This is **not** an official BIS determination that
the water is unsafe. Values
from 200 to below 500 mg/L meet the project target; 500–2000 mg/L is above the
acceptable BIS reference (the permissible limit applies only when no alternate
source exists); above 2000 mg/L exceeds the permissible reference. The rule is
isolated to the drinking profile and can be disabled in the backend environment.

**Turbidity honesty.** The ESP32 reports a provisional relative 0–100 index, not
NTU. That value is shown with its real unit and is never compared with the 1 NTU
or 5 NTU limits. Only a calibrated NTU measurement is compared with the BIS
turbidity references. Temperature is displayed as context/trend only: there is no
invented universal drinking-water temperature pass/fail threshold.

The shared assessment returns the test ID/timestamp, device, source, intended use,
all four values and units, freshness/stability, calibration status, reference
profile and criteria version, per-parameter status, overall status, every reason
and next step, and `prediction.available = false` with
“Future prediction unavailable — forecasting model not configured.” No forecasting
model is fabricated for this feature.

Product-user tests are private (`ProductWaterTest.user_id`) and persist the full
assessment JSON plus the reading it used. The Live Monitoring polling path stores
one `live_water_assessments` row per stable `(reading, use, criteria_version)`
(migration `a8c9d0e1f2b3`, reversible); unstable/offline windows are not persisted.

### Three-river demonstration dataset

The demonstration system uses exactly **three rivers** — **Arkavathi**, **Cauvery**
and **Vrishabhavathi** — each with its own monitoring location(s). Unrelated sample
lakes, ponds and reservoirs were removed from the demo dataset, source selectors,
river cards, trends, alerts and detail pages. Run `python backend/scripts/seed_demo.py`
after the migrations to create the three sources and their stations
(`ARK-001..003`, `CAU-001`, `VRS-001`, `VRS-002`). Every demo location and reading
is labelled as simulated demonstration data — it is never presented as verified
real-world information.

### Turbidity index vs. NTU (`turbidity_index`)

Migration `b9c0d1e2f3a4` adds a dedicated `sensor_readings.turbidity_index` column
for the analog sensor's **relative 0–100 index (higher = cloudier)**. It is stored
separately from `turbidity` when that row's unit is NTU, backfilled only for rows
already tagged `relative_index_0_100`, and it is:

- displayed as **“Turbidity Index (0–100)”** (never labelled NTU),
- banded with the firmware's documented demo thresholds — CLEARER < 30,
  MODERATE 30–54, CLOUDIER ≥ 55,
- never compared with the 1 NTU / 5 NTU limits, and
- never converted to NTU.

Historical NTU rows keep their own `turbidity_unit = "ntu"` and stay untouched.

### Simulation mode (no ESP32 required)

Authority → **Simulation** (`/authority/simulation`) drives
`backend/app/services/simulation_service.py` through
`POST /api/simulation/start`, `/pause` and `/generate` (plus `GET
/api/simulation/state`):

- scenarios: `normal`, `rain_runoff` (turbidity up), `industrial_discharge` (TDS and pH jump),
  `sewage_like` (TDS up, pH down), `sensor_fault` (NULL readings), plus the legacy
  `gradual_deterioration` and `sudden_change` drifts. The floating panel offers the five demo
  scenarios; the API accepts all seven;
- optional **seed** for a reproducible sequence (used by the tests);
- samples cover exactly pH, TDS, temperature and turbidity index, are timestamped
  and linked to the selected river/station, and are stored with
  `source = "simulator"` and diagnostics label **“SIMULATED DATA — NOT LIVE SENSOR
  DATA”**;
- a sensor-fault sample stores **NULL** for the failing sensor — a missing reading
  is never replaced by zero or an invented value;
- generated rows use the same persistence path as hardware telemetry, so trends,
  screening results and alerts update from them while remaining distinguishable
  from real ESP32 readings.

State is **persistent and shared**: Start / Pause / Generate and the selected
scenario live in the `simulation_runs` singleton row (migration
`c1d2e3f4a5b6`, PostgreSQL), not in process memory, so the controls stay
consistent across API workers and frontend sessions and survive a restart. Only
the worker holding an unexpired generation lease (15 s, renewed on every
sample) produces samples, so multiple Uvicorn workers never run duplicate
simulation loops. A seeded run derives each step's RNG from `(seed, step)` and
is therefore identical in any process.

### Danger-level alerts (to the product user)

`backend/app/services/alerting.py` derives alerts from real data only:
`GET /api/product/alerts` combines the latest live reading of the user's own
device with their most recent saved tests. Each entry carries the parameter,
measured value + unit, the configured reference, the reason, the next step,
whether the source was live or simulated, and a severity:

- `critical` — pH < 6.0 or > 9.0, TDS > 2000 mg/L, turbidity index ≥ 80;
- `warning` — pH outside 6.5–8.5, TDS > 500 mg/L, turbidity index ≥ 55
  (CLOUDIER demo band), an unusual temperature, a stale reading, or a sensor
  that stopped reporting (NULL is reported as NULL).

The user dashboard shows these alerts prominently above the device cards.
Turbidity alerts always state that the index is not an NTU measurement.

Every number comes from one versioned source: `GET /api/product/alerts/profile`
returns the active **alert threshold profile** (`alert-thresholds-2026.10.2`)
from `backend/app/services/alert_thresholds.py`. Each entry carries its value,
unit, trigger condition, classification — `official_standard` (verified against
BIS IS 10500:2012 with Amendment 4, citation included) or
`project_configured` (an illustrative project setting that requires local
validation and is **never** presented as a BIS, WHO or government-approved
limit) — plus source and rationale, and the profile disclaimer is served with
it and rendered in the UI. Turbidity entries are **relative-index bands only**
and are never expressed in or compared with NTU.

### Standards reference dataset

`docs/standards_reference.csv` keeps official reference limits separate from
measurements: standard code, name, authority, edition/revision, parameter, unit,
threshold type/value, applicable use, whether this device can measure it, a source
URL, and notes. Sources: BIS IS 10500:2012 (Amd. 4), FAO Irrigation and Drainage
Paper 29 Rev. 1, CPCB Designated Best Use criteria, and the WHO Guidelines for
Drinking-water Quality, 4th edition (2022). Project-specific demo thresholds
(the <200 mg/L TDS target and the turbidity-index bands) are listed in the same
file but flagged as `PROJECT-*` rows so they can never be mistaken for an official
standard. NTU-based compliance cannot be established with the current analog
sensor without a validated conversion or a calibrated NTU instrument.

### Public QR codes

Each station's public page is `/public/source/<station_code>`; the QR card on Live Monitoring encodes that exact URL and offers an SVG download. Set `VITE_PUBLIC_BASE_URL` (frontend `.env`) to your LAN or deployed origin before scanning from a phone — otherwise the QR encodes `localhost` and only works on the presenting machine. The public page and its API endpoints require no login and expose no device diagnostics, credentials or private data.

### Model health & evaluation transparency

`python ml/scripts/build_evaluation_report.py` loads the saved model artifacts, scores the held-out test splits, and writes a machine-readable report to `ml/reports/evaluation_report.json` plus a human-readable `ml/reports/evaluation_report.md`. Every metric is computed at generation time from repository artifacts — nothing is hardcoded. The authority-only endpoint `GET /api/authority/ml/status` serves this report together with the live model load state, and the Analytics dashboard renders it in the **Model Health & Evaluation** card. If the report has not been generated, the API returns `evaluation_available: false` and the UI says so — no placeholder metrics are ever shown.

### Baseline forecasting (authority-only)

`GET /api/authority/stations/{code}/forecast?horizon_hours=1..168` (default 24)
returns a validated, honestly gated forecast per parameter:

- **Readiness gate.** Before any model runs, the stored history is inspected per
  parameter (≥ 96 valid samples spanning ≥ 7 days). Short history ⇒
  `status: "unavailable"` with observed-vs-required numbers — the data pipeline
  and UI state exist, but forecasting is not claimed.
- **Model + time-aware evaluation.** A transparent Ridge model (normalised time
  index + previous reading, forecast recursively) is trained per parameter on a
  chronological split (last 20% held out, one-step-ahead) and compared with a
  naive persistence forecast; MAE and RMSE for both are reported.
- **Evaluation gate.** Forecast points are returned only when the model's
  holdout MAE strictly beats persistence. Otherwise the parameter carries
  `model_not_better_than_baseline` with its metrics but **no forecast numbers**.
- **Uncertainty.** The band is the holdout MAE, labelled as a constant-width
  empirical approximation — not a probabilistic interval.
- **Traceability.** The response reports the data-source mix (`simulator` /
  `esp32`) of the training history and flags forecasts trained on simulated
  rows as demonstration output, not real-world evidence.
- **Units.** Turbidity is forecast in its dominant stored unit; a relative
  0–100 index is forecast as an index and never described as NTU.

The Analytics dashboard card (`PredictionCard`) renders this endpoint with a
configurable horizon (6/12/24/48 h), per-parameter readiness/metrics, an
explicit “Forecasting unavailable” state, and a fixed footer stating that
forecasts are model outputs, not measurements. Service:
`backend/app/services/forecasting.py`; tests:
`backend/tests/test_forecasting.py` and `frontend/src/test/forecast.test.tsx`.

---

## Datasets and how to check accuracy, F1 and other metrics

Every number in this section is computed from artifacts in this repository by
`ml/scripts/build_evaluation_report.py` and written to
[`ml/reports/evaluation_report.md`](ml/reports/evaluation_report.md) +
`evaluation_report.json`; the authority API serves the same file. Nothing here is hand-written.

### 1. How many rows are there in total?

| Dataset | Rows | What it actually is | Allowed use |
|---|---|---|---|
| `ml/data/external/water_quality_dataset1.csv` | **100,800** (Safe 30,240 / Unsafe 70,560) | External **benchmark**; the Safe/Unsafe label follows that file's own rule (roughly TDS ≲ 210 mg/L and turbidity ≲ 4.5), **not** laboratory potability | Pipeline + method testing and demo **only**. Its accuracy must never be quoted as real-world performance, and suitability is never trained on it |
| `ml/data/external/usgs_*.csv` (USGS-01649190, Jan–Feb 2024, 5-min) | **40,000** raw rows (pH, turbidity FNU, temperature, conductance — 10,000 each) | Real but **single-station, winter**, no TDS (conductance converted with a documented factor) | Anomaly + forecast method development only |
| `ml/data/raw/sensor_readings.csv` | **9** | Real device log, far too small | Replace with a calibrated multi-day log before drawing conclusions |
| **Total cleaned input** | **140,809** rows across 6 files, **0 removed** ([cleaning report](ml/reports/dataset_cleaning_report.md)) | | |

Derived splits used by the models:

| Artifact | Rows | Used by |
|---|---|---|
| `supervised_train.csv` / `_validation.csv` / `_test.csv` | 70,560 / 15,120 / 15,120 | Random Forest (stratified 70/15/15, `random_state=42`) |
| `forecast_train.csv` / `_validation.csv` / `_test.csv` | 5,321 / 1,140 / 1,139 | XGBoost deterioration analysis (chronological, single station) |
| `usgs_timeseries_combined.csv` | 7,601 | Synchronised USGS sensor series |

### 2. The measured metrics

Random Forest — Safe/Unsafe classification (held-out test split, **live in the backend**):

| Metric | Value |
|---|---|
| Test samples | 15,120 |
| Accuracy | **0.9999** |
| Balanced accuracy | 0.9998 |
| Macro precision / recall / F1 | 0.9998 / 0.9998 / **0.9998** |
| Weighted F1 | 0.9999 |
| ROC-AUC (Unsafe) | 1.0000 |

| Class | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| Safe | 0.9998 | 0.9998 | 0.9998 | 4,536 |
| Unsafe | 0.9999 | 0.9999 | 0.9999 | 10,584 |

Confusion matrix (rows = true, columns = `Safe`, `Unsafe`): `[[4535, 1], [1, 10583]]`.

Isolation Forest — anomaly screening (live in the backend): 15,120 readings scored,
**727 flagged (4.81 %)**, scores −0.1002 … 0.1582 (mean 0.0860). Precision/recall/F1 are
**not** reported: there are no ground-truth contamination labels, so an anomaly rate would be
descriptive only.

XGBoost — deterioration prediction (offline only): 1,139 test rows, accuracy 0.9438 but
balanced accuracy **0.5376**, macro F1 **0.5284**, ROC-AUC 0.6288, and on the minority `Unsafe`
class precision 0.0698 / recall 0.1111 / F1 0.0857 (27 samples). The high raw accuracy is an
imbalance artefact — this model is deliberately **not** wired to live inference.

Forecast model (live, authority-only): evaluated per parameter on a chronological holdout against
a **persistence baseline**; MAE and RMSE for both are returned, and forecast points are withheld
when the model does not strictly beat persistence (`model_not_better_than_baseline`). Populate a
station with enough history (≥ 96 samples over ≥ 7 days) before expecting points.

### 3. What the metrics mean here

- **Accuracy** — share of correct predictions. With a 70/30 class split, always guessing `Unsafe`
  already scores ≈ 0.70, so it is never reported alone.
- **Balanced accuracy** — mean of the per-class recalls; the first honest signal that a model is
  useful on the minority class.
- **Precision** — of the rows flagged `Unsafe`, how many were truly `Unsafe`.
- **Recall** — of the truly `Unsafe` rows, how many were caught.
- **F1** — harmonic mean of precision and recall; **macro** F1 averages both classes equally,
  **weighted** F1 weights by class size (and is therefore flattered by the majority class).
- **ROC-AUC** — ranking quality independent of a threshold.
- **Anomaly model** — no labels exist, so only the flag rate and score range are reported; an
  anomaly is an unusual sensor pattern, never confirmed pollution.

### 4. Reproduce / check them yourself

```bash
# rebuild the full report from the saved artifacts (writes ml/reports/evaluation_report.{md,json})
python ml/scripts/build_evaluation_report.py

# per-model views
python ml/scripts/evaluate_random_forest.py
python ml/scripts/evaluate_isolation_forest.py
python ml/scripts/evaluate_xgboost.py

# dataset audit: row counts, ranges, units, provenance, duplicates
python ml/scripts/inspect_datasets.py
python ml/preprocessing/clean_datasets.py     # rewrites ml/reports/dataset_cleaning_report.md

# the same metrics through the API / UI (authority token required)
curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/api/authority/ml/status
#   → Authority → Analytics → “Model Health & Evaluation”

# ML test suite (leakage, reproducibility, persistence, SHAP)
python -m pytest ml/tests -q
```

Honesty guardrails this project enforces: the benchmark dataset's label is not laboratory
potability; Random Forest metrics come from a static benchmark split, not these sensors; the
XGBoost model is offline-only; simulator rows are pipeline tests, not scientific ground truth;
ESP32 turbidity is a relative index (0–100) and never treated as NTU or fed to ML as NTU.

---

## Testing

```bash
# Backend (pytest, in-memory SQLite — no PostgreSQL or broker needed)
python -m pytest backend/tests -v

# Focused assessment tests (TDS/pH boundaries, stability, calibration, uses)
cd backend && python -m pytest tests/test_product_screening.py tests/test_product_tests.py -v

# Forecasting readiness/evaluation, simulation persistence, alert profile, ML availability
cd backend && python -m pytest tests/test_forecasting.py tests/test_simulation_and_alerts.py tests/test_ml_availability.py -v

# Incident + laboratory workflow (RBAC, status transitions, PDF report, lab email)
cd backend && python -m pytest tests/test_incidents.py -v

# ML pipeline (leakage, reproducibility, persistence, SHAP)
python -m pytest ml/tests -v

# Frontend (Vitest + Testing Library)
cd frontend && npm test

# Frontend production build + lint
cd frontend && npm run build && npm run lint
```

The backend suite exercises the real MQTT payload parser and subscriber callbacks (malformed JSON, non-object payloads, missing fields, null sensor values, retry de-duplication, relative-index validation, API responses). No broker, PostgreSQL instance, or physical device is required for it.

Last full run (2026-10-31, this checkout):

| Suite | Command | Result |
|---|---|---|
| Backend | `cd backend && python -m pytest -q` | **620 passed**, 4 warnings (≈6 min) |
| ML | `python -m pytest ml/tests -q` | **140 passed** (≈1 min) |
| Frontend | `cd frontend && npm test` | **83 passed** in 8 files |
| Lint | `cd frontend && npm run lint` | **0 errors**, 1 pre-existing warning (`components/ui/button.tsx`) |
| Build | `cd frontend && npm run build` | **ok** (2,474 modules) |

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
| `/api/authority/ml/status` | `AUTHORITY` | model load state + computed evaluation report |
| `/api/authority/stations/{code}/suitability` | `AUTHORITY` | BIS/CPCB suitability for the latest reading |
| `/api/authority/stations/{code}/live-assessment?use=drinking` | `AUTHORITY` | Stable four-sensor assessment for the selected use (`drinking`, `domestic`, `irrigation`, `general`) |
| `/api/authority/stations/{code}/forecast?horizon_hours=24` | `AUTHORITY` | Honest baseline forecast — points only when holdout evaluation beats persistence, otherwise `status: unavailable` + reason |
| `/api/simulation/start|pause|generate|state` | `AUTHORITY` | Persistent three-river simulation controls (PostgreSQL-backed, lease-guarded) |
| `/api/authority/incidents` | `AUTHORITY` | Incident queue and detail with the audit timeline (`POST`, `GET`, `GET /{id}`) |
| `/api/authority/incidents/{id}/notify-lab` | `AUTHORITY` | Records the laboratory notification and **emails the PDF report**; response carries `lab_notification_status` (`sent` / `smtp_unconfigured` / `failed`) |
| `/api/authority/incidents/{id}/report.pdf` | `AUTHORITY` | Download the generated report (works without SMTP) |
| `/api/authority/incidents/{id}/sample-collected`, `/lab-result`, `/resolve` | `AUTHORITY` | Rest of the forward-only workflow, including verbatim laboratory results |
| `/api/authority/lab-contacts` | `AUTHORITY` | Laboratories that can receive the report |
| `/api/product/alerts`, `/api/product/alerts/profile` | `PRODUCT_USER` | Danger-level alerts + the active versioned threshold profile (official vs project-configured) |
| `/api/product/devices`, `/api/product/activate` | `PRODUCT_USER` | Owned product devices and product-code activation |
| `POST /api/product/tests` | `PRODUCT_USER` | Run a live (stable window) or explicitly labelled demo test and persist it |
| `GET /api/product/tests`, `/api/product/tests/{id}` | `PRODUCT_USER` | Private test history and full saved assessment |
| `/api/public/stations/{code}/readings/latest` | Public | latest reading for the QR page (no diagnostics) |
| `/api/public/stations/{code}/readings` | Public | recent public-safe readings for the trend chart |
| `/api/public/stations/{code}/suitability` | Public | suitability assessment for the QR page |

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
| Station shows **Error** although rows keep arriving | The device reported a probe fault in its diagnostics (for example TDS null because the sensor voltage is near 0 V). The station is online; fix that probe. The message on the card names the sensor and the error. |
| Device-number login returns 404 | No `product_devices` row is bound to that `HSD-…` number. Station telemetry does not create one: register the device row and claim its product code first. |
| Serial: `[ADS] ERROR: ADS1115 not found` | I²C wiring/address; analog values publish `null` with a `device.errors` entry instead of fake numbers. |
| Serial: `[TIME] NTP not synced yet` | Normal for the first seconds after boot; publishing starts once time is valid. |
| Dashboard shows `(unit unknown)` | Row predates unit tracking; it is intentionally not labelled NTU or relative index. |
| Live Monitoring says **Reading unstable** | A parameter's range exceeds the configured tolerance in `sensor_stability.py`; keep the probe submerged until 10 valid samples over 20 s are within tolerance. Do not bypass stability to force a pass. |
| Product test returns `unstable_reading` (409) | The device has fewer than 10 valid samples, under 20 s of data, a stale latest sample, or a parameter outside tolerance. Wait and retry; only demo mode works without a stable live window. |
| Result is **Inconclusive** with “calibration is unverified” | The device's diagnostics report `pending`/provisional calibration. Calibrate the probes and record the calibration; stability alone is not calibration. |
| TDS below 200 mg/L shows **Below project strict target** | This is the project's demo rule, not an official BIS rule. Set `DEMO_STRICT_TDS_RULE=false` in the backend environment to disable it for drinking water only. |
| `alembic upgrade head` fails on diagnostics backfill | Run against PostgreSQL 12+ (JSON operators); the backfill is skipped on other dialects. |

---

## Production Configuration & Deployment Verification

**Local static checks** (these inspect configuration only — they never reach a deployed
environment):

```bash
cd backend
python scripts/verify_production_config.py   # PASS/FAIL/REVIEW checklist, exit 1 on any FAIL
```

It runs the application's own fail-fast checks (JWT secret present, strong and not a known
placeholder; production-like `APP_ENV`; CORS allowlist populated; MQTT credentials present and
anonymous access refused) plus static settings checks (rate limits configured, broker TLS for
any non-loopback host, HTTPS `PUBLIC_BASE_URL`, finite ingestion bounds, proxy-header trust off,
HS256, token lifetime, non-default database URL, and a `git ls-files` scan for tracked secret
files). Against a development `.env` it intentionally reports FAILs — that is correct: those
checks are meant to be run with the *production* environment variables. The same checks are
covered by `backend/tests/test_production_config.py`.

The canonical checklist, with the exact real-environment steps and their current status, is
[docs/DEPLOYMENT_VERIFICATION.md](docs/DEPLOYMENT_VERIFICATION.md). Every item there is still
unrun.

> **Deployment security is UNVERIFIED.** The script is a local, static check. It cannot probe a
> real deployment, so nothing below may be claimed as verified until this checklist has been
> exercised against the actual environment:

**Deployment verification checklist (run on the real environment):**

1. `APP_ENV=production` and a freshly generated `JWT_SECRET_KEY` (≥ 32 chars, e.g.
   `python -c "import secrets; print(secrets.token_urlsafe(48))"`) supplied through the
   environment/secret manager — **never** committed, never logged, never echoed in an API
   response. Rotate by redeploying with a new value (all sessions invalidate).
2. `python scripts/verify_production_config.py` exits 0 with the production environment loaded.
3. `alembic upgrade head` applied to the production database; `alembic current` = `head`.
4. CORS: `CORS_ALLOW_ORIGINS` lists only the real frontend origin(s); verify from a real browser
   that the frontend origin is allowed and an arbitrary origin receives no CORS headers.
5. Auth round-trip on the real host: register → login → authorized call → logout; confirm
   unauthenticated calls to `/api/authority/*` return 401 and product users get 403.
6. Rate limiting observed live: hammer `POST /api/auth/login` and confirm **429** with
   `Retry-After` (and that no password/token ever appears in logs).
7. TLS terminated at the proxy, `RATE_LIMIT_TRUST_PROXY_HEADERS=true` only behind a proxy you
   control, and no secrets in logs, error pages or the OpenAPI schema.
8. MQTT: anonymous connections refused, per-station ACLs enforced, TLS certificate validated
   when the broker is remote, and implausible payloads (TDS > 50 000 ppm, NTU > 4 000) rejected.
9. Device activation observed returning 429 after `RATE_LIMIT_ACTIVATE_MAX` attempts.
10. Seeded demo credentials changed before any real users exist.

### Database schema drift (intentional, verified — no drops)

`alembic check` reports drift because the deployed database still contains **legacy tables and
columns that the SQLAlchemy models intentionally no longer map to**. Verified on 2026-10-28:

| Drift | What it is | Why it is kept |
|---|---|---|
| Tables `water_tests`, `water_test_assessments`, `water_test_predictions` (+ their indexes) | The original product water-test schema, superseded by `product_water_tests` (migration `f6a7b8c9d0e1`) | They hold historical records; a grep of `backend/app` finds **no reference** to them (only `product_water_tests` is used). Dropping would destroy data to silence a warning. |
| Columns `product_devices.device_name`, `product_devices.expires_at` | Earlier device columns; the API now serves a constant `DEVICE_NAME` and stores activation/expiry elsewhere | The `ProductDevice` model has no such attributes, so nothing reads them; harmless and reversible only by a dedicated migration. |

No migration drops or rewrites any of this: migration history is untouched and `alembic
upgrade head` still lands on `b8c9d0e1f2a3` (chain: … `a9b0c1d2e3f4` overall-state →
`f1e2d3c4b5a6` device-number registry → `a7b8c9d0e1f2` notifications → `b8c9d0e1f2a3`
incidents/labs). If you ever want to reclaim the space, write an
explicit, reviewed migration after confirming the rows are expendable — do not run
`alembic revision --autogenerate` output that contains `drop_table`/`drop_column` blindly.

---

## Scientific Honesty & Limitations

This project deliberately constrains its claims:

- **Anomaly ≠ contamination.** Isolation Forest flags readings unusual relative to its training telemetry; it does not confirm chemical contamination.
- **Predicted class ≠ potability.** The Random Forest reproduces the labeling rules of its benchmark dataset; it is not laboratory confirmation or a guarantee of safety.
- **Simulator data is not ground truth.** Scenario names exist for pipeline testing only and are never used as scientific labels.
- **Four sensors have limits.** Heavy metals, microplastics, pharmaceuticals, and microbial pathogens that do not affect pH/TDS/turbidity/temperature cannot be detected by these parameters alone. A `WITHIN_PROJECT_TARGETS` result means only that no *monitored* concern was detected; it is not a potability certificate.
- **Low TDS is a project preference, not a safety verdict.** The <200 mg/L drinking-water flag is a demo rule. Low TDS alone does not make water unsafe, and high TDS alone does not identify which contaminants are present.
- **Stability ≠ calibration.** A stable rolling window can still come from provisional sensors; live results with unverified calibration are reported as `INCONCLUSIVE`.
- **Forecasting honesty.** The XGBoost deterioration target is a rule-based indicator on a single USGS station (~5 weeks synchronized); temporal performance drop from validation to test is documented, not tuned away.
- **Security posture.** The code enforces an explicit CORS allowlist, requires an environment-supplied JWT secret, throttles login/registration/device activation with shared database counters, requires MQTT broker credentials in production, rejects anonymous brokers, and blocks privilege escalation at registration — but **no production deployment has been verified**, so production security must still be confirmed on the real environment ([checklist](docs/DEPLOYMENT_VERIFICATION.md)).
- **No fabricated results.** Missing ML artifacts, failed inference, or pre-ML readings all produce NULL ML fields, rendered in the UI as "Analysis unavailable".
- **Turbidity is not always NTU.** ESP32 hardware reports a **provisional relative index 0–100** anchored to two sample-based sensor voltages (≈0.354 V clear, ≈0.273 V cloudy). It is a relative trend indicator, **not** a calibrated NTU measurement and **not** a safety verdict; converting it to NTU requires the two-point calibration in [firmware/README.md](firmware/README.md) §10.
- **Relative turbidity is excluded from ML.** The models were trained on NTU-style turbidity, so relative-index readings are stored and displayed but deliberately keep NULL ML fields — reported as “ML prediction unavailable for Turbidity Index readings.” rather than a silent gap. Data requirements for a future index-trained model are documented in [docs/TURBIDITY_INDEX_ML.md](docs/TURBIDITY_INDEX_ML.md).

**Resolved in this pass**

- **Security hardening (CORS, JWT secret, rate limiting, privilege escalation).** CORS is an explicit env-driven allowlist (`CORS_ALLOW_ORIGINS`) with no wildcard-plus-credentials combination and a fail-closed production default; `JWT_SECRET_KEY` has no code default and startup fails when it is missing (production also rejects short or known-insecure values, and no secret is ever auto-generated); login and registration are throttled by database-backed fixed-window counters (migration `e7f8a9b0c1d2`) returning 429 + `Retry-After`; public registration rejects any role other than `PRODUCT_USER`. Regression tests: `backend/tests/test_security_hardening.py` (30 tests).
- **Validation pass — dashboard honesty.** The authority **Alerts** page threshold card no longer claims dissolved-oxygen, NTU or "AI risk" triggers: it shows the four-sensor project-configured tiers (turbidity index bands, TDS references, pH range), links `GET /api/product/alerts/profile` as the sourced authority, states that no SMS/webhook dispatch exists, and says explicitly that unmeasured parameters are never part of the tiers. The public **My Checks** page no longer shows fabricated lake/reservoir history quoted in NTU — it shows clearly-labelled demonstration entries for the three rivers with relative-index wording.
- **One central four-parameter suitability engine.** Every suitability decision now flows through `backend/app/services/suitability_engine.py`, which accepts **exactly** pH, TDS, temperature and turbidity (any other key raises `ValueError`, so dissolved oxygen, ML scores, rainfall, history or location can never influence a result), delegates to the per-purpose threshold profiles in `water_screening.py`, and emits one canonical four-state vocabulary — `within_configured_ranges` / `caution` / `outside_configured_ranges` / `insufficient_data` — defined in `screening_states.py` and shared with the station engine (`water_suitability.py`). Product tests persist it in a new `overall_state` column (migration `a9b0c1d2e3f4`, backfilled from stored assessments) and serve it next to the unchanged legacy `overall_status`, so existing screens keep working. Invalid, stale, unstable or non-finite readings always collapse to `insufficient_data` — never a positive result. Tests: `backend/tests/test_suitability_engine.py` (49 tests).

- **Rule-based recommendations derived from triggered rules.** `backend/app/services/recommendations.py`
  attaches advice to every non-passing assessment, keyed by `(use, parameter, direction)` and built
  only from the parameter entries the engine actually evaluated. Causes are worded as *possible*,
  never asserted; drinking advice always ends with laboratory confirmation and the explicit statement
  that these four sensors cannot confirm the water is safe; temperature carries no advice because no
  temperature threshold is configured; unmeasured quantities (EC/SAR, microbiology, dissolved oxygen,
  heavy metals, rainfall, ML outputs) appear only in `missing_assessments`, each phrased "not measured
  by these sensors". Public and product responses carry consumer advice only — the incident workflow
  steps (grab sample, upstream inspection, notify the pollution control authority, track the lab
  result) are added exclusively on authority routes. Tests: `backend/tests/test_recommendations.py`
  (206 tests, one per rule plus behaviour and API-surface checks).

- **Turbidity-unvalidated results can no longer read as a full pass.** In the product screening
  engine (`water_screening.py`) any use whose profile rates turbidity (drinking, domestic,
  general) now caps its best possible result at `REVIEW_RECOMMENDED` (canonical
  `caution`) when turbidity is a relative index without NTU calibration or is missing, and the
  assessment carries an explicit warning: *pH and TDS passing their screening rules is reported
  as a caution — not as a full pass*. Regression tests in
  `tests/test_product_tests.py` / `tests/test_product_screening.py`.
- **The authority Alerts page is served by the backend.** New `GET /api/authority/alerts`
  (authority-role only) derives danger-level alerts from each active station's latest stored
  reading through the shared alerting service and versioned threshold profile — no fabricated
  entries, simulated rows keep their labels, stations without readings produce no alerts.
  `frontend/src/pages/authority/Alerts.tsx` now shows loading, empty, error and
  unauthorized/expired states instead of `mockAlerts`.
- **Prototype authority pages are labelled.** Incidents, Inspections and Laboratory carry a
  visible `PrototypeBanner` that states the records are demonstration data. Incidents and
  Laboratory now say precisely that the backend workflow exists (endpoints, audit trail, PDF)
  while these pages are not wired to it yet; Inspections states it has no backend at all. No
  screen implies that its demonstration records are genuine operational entries.
- **Production configuration can be checked locally.** `backend/scripts/verify_production_config.py`
  plus `backend/tests/test_production_config.py` implement the static checklist above; deployment
  itself remains UNVERIFIED until the checklist runs against the real environment.
- **Schema drift is documented, not dropped.** The legacy `water_tests` / `water_test_assessments`
  / `water_test_predictions` tables and the two retired `product_devices` columns are inventoried
  above with the verification that no application code references them; no table or row was
  deleted and migration history was not rewritten.
- **Simulation state is persistent and shared.** The previous per-process in-memory state was replaced by the `simulation_runs` singleton row (migration `c1d2e3f4a5b6`) with a per-worker generation lease: controls stay consistent across API workers and restarts, and no duplicate simulation loops can run.
- **Alert thresholds are transparent.** Every alert number comes from one versioned, sourced profile that separates `official_standard` (BIS-cited) from `project_configured` (illustrative, requires local validation), served by `GET /api/product/alerts/profile` and shown in the UI; turbidity-index alerts are never compared with NTU limits.
- **ML availability is explicit per reading.** Relative-index readings report “ML prediction unavailable for Turbidity Index readings.” with the reason, and stale labels are never surfaced next to an “unavailable” status.
- **Forecasting exists as a validated baseline capability** with readiness gates, time-aware holdout evaluation against persistence, and honest unavailable states (see *Baseline forecasting* above).
- **Device-number login.** `POST /api/auth/device-login` resolves a printed device number
  (`HSD-0001-K7M2Q9`) to its bound account with generic errors and its own rate-limit bucket
  (migration `f1e2d3c4b5a6` seeds the registry); one device binds to one account.
- **Notification service.** Alerts can now be delivered: `notifications` table + migration
  `a7b8c9d0e1f2` with severity, dedup key, cooldown window, per-user category preferences and a
  delivery log. With no SMTP configured the outcome is recorded as `skipped_unconfigured` —
  never silently "sent", and never breaking ingestion or alerting.
- **Incident + laboratory workflow (backend).** AUTHORITY-only endpoints under
  `/api/authority/incidents` implement `raised → lab_notified → sample_collected →
  result_received → resolved` with an audit event per step, lab contacts, verbatim lab results
  (fixed `source=laboratory`, never derived from the four sensors) and a generated PDF report
  (migration `b8c9d0e1f2a3`). The Incidents and Laboratory **pages** are still labelled
  demonstrations until they are wired to these endpoints.
- **Station QR generation (backend).** `GET /api/authority/stations/{code}/qr[.png|.svg|.pdf]`
  encodes `PUBLIC_BASE_URL` per station; the authority QR page shows a live preview and
  downloads from these endpoints.
- **Anomaly model retrained and versioned.** The 9-row Isolation Forest was replaced with a
  model trained on the cleaned real distributions; artifacts carry `model_manifest.json` and
  `ml/reports/evaluation_report.md` recomputes metrics from the artifacts. External datasets are
  audited by `ml/scripts/inspect_datasets.py` (`ml/reports/dataset_inspection.md`).
- **Public WaterCheck uses the backend.** The public suitability page now renders
  `GET /api/public/stations/{code}/suitability` instead of computing verdicts in the browser
  from mock data; the sidebar's fabricated probe count was removed and every remaining
  demonstration screen is explicitly labelled.
- **MQTT and ingestion hardening.** Production startup refuses anonymous MQTT (credentials
  required unless `MQTT_ALLOW_ANONYMOUS=true`), TLS is required for any non-loopback broker,
  telemetry is bounded to TDS ≤ 50 000 ppm / turbidity ≤ 4 000 NTU / index ≤ 100 (non-finite
  rejected), and `POST /product/activate` is throttled. See
  [docs/DEPLOYMENT_VERIFICATION.md](docs/DEPLOYMENT_VERIFICATION.md).

**Remaining limitations**

- **No probabilistic or trained forecasting model.** Only the Ridge baseline is implemented; there are no confidence intervals (the band is the holdout MAE), no exogenous inputs (e.g. rainfall), and parameters with short or non-predictable history report `unavailable` rather than numbers. Stations without enough stored history (currently `CAU-001`, `VRS-001`) show the readiness state instead of a forecast.
- **No ML for turbidity-index readings.** No representative labelled index dataset exists yet, so the exclusion is retained by design; the training workflow is documented in [docs/TURBIDITY_INDEX_ML.md](docs/TURBIDITY_INDEX_ML.md).
- **Incident/inspection UI is not wired; Inspections has no backend.** The incident and
  laboratory *backend* is complete and tested, but the Incidents and Laboratory pages still
  render labelled demonstration records; Inspections has no endpoints at all. Rate limiting
  now covers login, registration, device login and device activation, but not every public or
  authority route, and there is no account lockout. See
  [docs/FEATURE_STATUS.md](docs/FEATURE_STATUS.md) §6 for the full open-findings table.
- **Production security is still UNVERIFIED.** The static checker and its tests only prove the code fails closed; the deployment checklist above has not been exercised on a real environment.
- **Intentional schema drift remains open** — the legacy tables/columns listed above are still in the database by design (no drops); `alembic check` will keep flagging them until a reviewed migration is written.

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
