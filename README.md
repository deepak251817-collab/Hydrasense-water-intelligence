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
- **Live four-sensor assessment** — Live Monitoring reads the real ESP32/MQTT window, waits for **10 valid samples over 20 s**, checks stability per parameter and runs one shared, explainable screening service for Drinking, Domestic Use, Irrigation, Swimming/Recreation or Aquaculture. Stable readings are never treated as calibrated readings.
- **Private product-user tests** — a signed-in product user activates a product code, chooses a water source and intended use, and receives the same screening from their own device's live window (or clearly labelled SIMULATION values). Results are stored per account and are not visible to other users.
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
| `MQTT_BROKER_HOST` / `MQTT_BROKER_PORT` | `localhost` / `1883` | Broker address |
| `MQTT_TOPIC_PREFIX` | `hydrasense/stations` | Telemetry topic prefix |
| `DEMO_STRICT_TDS_RULE` | `true` | Enables the project-specific <200 mg/L drinking-water TDS target. Set `false` to disable it; it never affects domestic, irrigation, swimming or aquaculture. |

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
python ml/scripts/build_evaluation_report.py   # compute real metrics from saved artifacts
```

### Water Suitability Assessment (BIS IS 10500 / CPCB)

The standards-based assessment lives in `backend/app/services/water_suitability.py` and screens six intended uses: drinking water, domestic use, outdoor bathing, irrigation, industrial cooling and aquatic life. It compares **only** values that are genuinely comparable:

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
| Swimming / Recreation | pH 6.5–8.5 and calibrated-NTU turbidity where available. Microbiology and site-specific criteria are required, so the best possible state is `REVIEW_RECOMMENDED`. |
| Aquaculture | The four values are displayed, but without species-specific criteria and measured dissolved oxygen/ammonia/nitrite/salinity the result is `INCONCLUSIVE`. |

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

- scenarios: `normal`, `gradual_deterioration`, `sudden_change`, `sensor_fault`;
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
returns the active **alert threshold profile** (`alert-thresholds-2026.10.1`)
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

## Testing

```bash
# Backend (pytest, in-memory SQLite — no PostgreSQL or broker needed)
python -m pytest backend/tests -v

# Focused assessment tests (TDS/pH boundaries, stability, calibration, uses)
cd backend && python -m pytest tests/test_product_screening.py tests/test_product_tests.py -v

# Forecasting readiness/evaluation, simulation persistence, alert profile, ML availability
cd backend && python -m pytest tests/test_forecasting.py tests/test_simulation_and_alerts.py tests/test_ml_availability.py -v

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
| `/api/authority/ml/status` | `AUTHORITY` | model load state + computed evaluation report |
| `/api/authority/stations/{code}/suitability` | `AUTHORITY` | BIS/CPCB suitability for the latest reading |
| `/api/authority/stations/{code}/live-assessment?use=drinking` | `AUTHORITY` | Stable four-sensor assessment for the selected use (`drinking`, `domestic`, `irrigation`, `swimming`, `aquaculture`) |
| `/api/authority/stations/{code}/forecast?horizon_hours=24` | `AUTHORITY` | Honest baseline forecast — points only when holdout evaluation beats persistence, otherwise `status: unavailable` + reason |
| `/api/simulation/start|pause|generate|state` | `AUTHORITY` | Persistent three-river simulation controls (PostgreSQL-backed, lease-guarded) |
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
| Serial: `[ADS] ERROR: ADS1115 not found` | I²C wiring/address; analog values publish `null` with a `device.errors` entry instead of fake numbers. |
| Serial: `[TIME] NTP not synced yet` | Normal for the first seconds after boot; publishing starts once time is valid. |
| Dashboard shows `(unit unknown)` | Row predates unit tracking; it is intentionally not labelled NTU or relative index. |
| Live Monitoring says **Reading unstable** | A parameter's range exceeds the configured tolerance in `sensor_stability.py`; keep the probe submerged until 10 valid samples over 20 s are within tolerance. Do not bypass stability to force a pass. |
| Product test returns `unstable_reading` (409) | The device has fewer than 10 valid samples, under 20 s of data, a stale latest sample, or a parameter outside tolerance. Wait and retry; only demo mode works without a stable live window. |
| Result is **Inconclusive** with “calibration is unverified” | The device's diagnostics report `pending`/provisional calibration. Calibrate the probes and record the calibration; stability alone is not calibration. |
| TDS below 200 mg/L shows **Below project strict target** | This is the project's demo rule, not an official BIS rule. Set `DEMO_STRICT_TDS_RULE=false` in the backend environment to disable it for drinking water only. |
| `alembic upgrade head` fails on diagnostics backfill | Run against PostgreSQL 12+ (JSON operators); the backfill is skipped on other dialects. |

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
- **Security posture.** The code enforces an explicit CORS allowlist, requires an environment-supplied JWT secret, throttles login/registration with shared database counters, and blocks privilege escalation at registration — but **no production deployment has been verified**, so production security must still be confirmed on the real environment.
- **No fabricated results.** Missing ML artifacts, failed inference, or pre-ML readings all produce NULL ML fields, rendered in the UI as "Analysis unavailable".
- **Turbidity is not always NTU.** ESP32 hardware reports a **provisional relative index 0–100** anchored to two sample-based sensor voltages (≈0.354 V clear, ≈0.273 V cloudy). It is a relative trend indicator, **not** a calibrated NTU measurement and **not** a safety verdict; converting it to NTU requires the two-point calibration in [firmware/README.md](firmware/README.md) §10.
- **Relative turbidity is excluded from ML.** The models were trained on NTU-style turbidity, so relative-index readings are stored and displayed but deliberately keep NULL ML fields — reported as “ML prediction unavailable for Turbidity Index readings.” rather than a silent gap. Data requirements for a future index-trained model are documented in [docs/TURBIDITY_INDEX_ML.md](docs/TURBIDITY_INDEX_ML.md).

**Resolved in this pass**

- **Security hardening (CORS, JWT secret, rate limiting, privilege escalation).** CORS is an explicit env-driven allowlist (`CORS_ALLOW_ORIGINS`) with no wildcard-plus-credentials combination and a fail-closed production default; `JWT_SECRET_KEY` has no code default and startup fails when it is missing (production also rejects short or known-insecure values, and no secret is ever auto-generated); login and registration are throttled by database-backed fixed-window counters (migration `e7f8a9b0c1d2`) returning 429 + `Retry-After`; public registration rejects any role other than `PRODUCT_USER`. Regression tests: `backend/tests/test_security_hardening.py` (30 tests).
- **Validation pass — dashboard honesty.** The authority **Alerts** page threshold card no longer claims dissolved-oxygen, NTU or "AI risk" triggers: it shows the four-sensor project-configured tiers (turbidity index bands, TDS references, pH range), links `GET /api/product/alerts/profile` as the sourced authority, states that no SMS/webhook dispatch exists, and says explicitly that unmeasured parameters are never part of the tiers. The public **My Checks** page no longer shows fabricated lake/reservoir history quoted in NTU — it shows clearly-labelled demonstration entries for the three rivers with relative-index wording.
- **One central four-parameter suitability engine.** Every suitability decision now flows through `backend/app/services/suitability_engine.py`, which accepts **exactly** pH, TDS, temperature and turbidity (any other key raises `ValueError`, so dissolved oxygen, ML scores, rainfall, history or location can never influence a result), delegates to the per-purpose threshold profiles in `water_screening.py`, and emits one canonical four-state vocabulary — `within_configured_ranges` / `caution` / `outside_configured_ranges` / `insufficient_data` — defined in `screening_states.py` and shared with the station engine (`water_suitability.py`). Product tests persist it in a new `overall_state` column (migration `a9b0c1d2e3f4`, backfilled from stored assessments) and serve it next to the unchanged legacy `overall_status`, so existing screens keep working. Invalid, stale, unstable or non-finite readings always collapse to `insufficient_data` — never a positive result. Tests: `backend/tests/test_suitability_engine.py` (49 tests).

- **Simulation state is persistent and shared.** The previous per-process in-memory state was replaced by the `simulation_runs` singleton row (migration `c1d2e3f4a5b6`) with a per-worker generation lease: controls stay consistent across API workers and restarts, and no duplicate simulation loops can run.
- **Alert thresholds are transparent.** Every alert number comes from one versioned, sourced profile that separates `official_standard` (BIS-cited) from `project_configured` (illustrative, requires local validation), served by `GET /api/product/alerts/profile` and shown in the UI; turbidity-index alerts are never compared with NTU limits.
- **ML availability is explicit per reading.** Relative-index readings report “ML prediction unavailable for Turbidity Index readings.” with the reason, and stale labels are never surfaced next to an “unavailable” status.
- **Forecasting exists as a validated baseline capability** with readiness gates, time-aware holdout evaluation against persistence, and honest unavailable states (see *Baseline forecasting* above).

**Remaining limitations**

- **No probabilistic or trained forecasting model.** Only the Ridge baseline is implemented; there are no confidence intervals (the band is the holdout MAE), no exogenous inputs (e.g. rainfall), and parameters with short or non-predictable history report `unavailable` rather than numbers. Stations without enough stored history (currently `CAU-001`, `VRS-001`) show the readiness state instead of a forecast.
- **No ML for turbidity-index readings.** No representative labelled index dataset exists yet, so the exclusion is retained by design; the training workflow is documented in [docs/TURBIDITY_INDEX_ML.md](docs/TURBIDITY_INDEX_ML.md).
- **No incident/inspection workflow or drift monitoring** — and rate limiting currently covers only the authentication endpoints (login/registration), not every public or authority route. See [docs/FEATURE_STATUS.md](docs/FEATURE_STATUS.md) §6 for the full open-findings table.

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
