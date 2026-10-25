# HydraSense — Feature Status Matrix

> **Purpose.** A single honest table of what works, what is partially wired, and what is a UI
> prototype. Use it before demoing anything and before claiming a feature in the report or viva.
>
> **Status vocabulary**
> - **Verified** — implemented in backend + frontend and exercised by automated tests or a live
>   HTTP check during this audit.
> - **Implemented (manual check)** — code exists and is consistent, but this audit did not exercise
>   it live (e.g. it needs hardware or an external service).
> - **Partial** — real data in some places, mock or simulated data in others on the same screen.
> - **UI-only** — renders from `frontend/src/data/mockData.ts` or hard-coded arrays; no backend.
> - **Not implemented** — no code path exists.

---

## 1. Summary counts

| Status | Scope | Examples |
|---|---|---|
| **Verified** | backend contracts, public QR page, auth, suitability, ML serving, evaluation transparency | MQTT handler, RBAC, ingestion-time assessment, `/public/*`, `/authority/ml/status` |
| **Implemented (manual check)** | 3 | ESP32 firmware, simulator scenarios, QR scanned from a phone over LAN |
| **Partial** | 5 screens | command center, live monitoring board, station detail, analytics, water map |
| **UI-only** | 12 screens | alerts, incidents, inspections, laboratory, water sources, nearby sources, warnings, public water check, my checks, user check-water, user history, device activation |
| **Not implemented** | 6 backends | alert engine/notifications, incident workflow, inspection workflow, lab-record store, personal-device reading submission, device activation API (the map canvas is a placeholder, not a backend) |

---

## 2. Backend

| Capability | Where | Evidence | Status |
|---|---|---|---|
| JWT auth (register/login, HS256, 60 min) | `app/api/v1/auth.py`, `app/core/security.py` | tests in `tests/test_auth.py`; login exercised in audit | **Verified** |
| Role-based access (PRODUCT_USER / AUTHORITY) | `app/api/deps.py` | `tests/test_rbac.py` (403 both directions) | **Verified** |
| Product-code binding at registration | `auth.py` (`ProductDevice` lookup, owner binding) | tests for duplicate/invalid code | **Verified** |
| Station catalogue + water source join | `GET /authority/stations`, `GET /public/stations/{code}` | `tests/test_public.py`, `tests/test_authority.py`; live `/openapi.json` | **Verified** |
| Latest reading + history (authority) | `authority.py` | `tests/test_telemetry.py` | **Verified** |
| Public safe reading + history | `public.py` + `PublicLatestReading` schema | tests assert `diagnostics` absent | **Verified** |
| MQTT ingestion topic `hydrasense/stations/+/telemetry` | `mqtt_service.py` | `tests/test_telemetry.py` calls `process_telemetry_payload` directly | **Implemented (manual check)** — broker delivery not exercised in this audit |
| Payload validation (ranges, types, timestamp) | `validate_telemetry_payload` | unit tests for every rejection branch | **Verified** |
| NULL-tolerant ingestion (uncalibrated sensors) | `SensorReading.ph/turbidity/tds/temperature` nullable | tests for NULL payloads | **Verified** |
| Duplicate guard on `(station, device, timestamp)` | `mqtt_service.process_telemetry_payload` | test asserts "Skipped duplicate" and single row | **Verified** |
| Provenance `source` + `diagnostics` blob (8 KiB cap) | `mqtt_service.py`, `models/water.py` | tests for invalid source / oversized diagnostics | **Verified** |
| Turbidity unit contract (`ntu` vs `relative_index_0_100`) | `parse_turbidity_meta`, `c3d4e5f6a7b8` migration | tests + `tests/test_turbidity` equivalents in backend | **Verified** |
| ML inference at ingestion (Isolation Forest + Random Forest) | `attach_ml_results` | `tests/test_ml_service.py`, `tests/test_telemetry.py`; live rows carry `ml_processed_at` | **Verified** |
| ML skipped (NULL fields) for relative-index or incomplete readings | `mqtt_service.py` | explicit tests | **Verified** |
| Reading + ML analysis endpoints | `/authority/readings/{id}/analysis`, `/latest/analysis` | `tests/test_ml_api.py`; frontend integration tests | **Verified** |
| Model health + evaluation report endpoint | `/authority/ml/status`, `ml_status_service.py` | `tests/test_ml_status.py`; `ModelHealthCard` frontend test | **Verified** |
| Standards-based suitability (6 uses, BIS/CPCB) | `water_suitability.py` (685 lines) | `tests/test_water_suitability.py` (96 targeted tests) | **Verified** |
| Suitability persisted as derived rows | `water_suitability_assessments`, unique constraint | migration + persistence tests | **Verified** |
| Suitability computed at ingestion | `mqtt_service.py` lines ~313-328 | code read; covered indirectly by `test_telemetry` | **Verified (code)** |
| Public suitability endpoint | `GET /public/stations/{code}/suitability` | `test_water_suitability` public cases | **Verified** |
| Password hashing (argon2 via `pwdlib`) | `core/security.py` | login tests | **Verified** |
| Alert generation / notification | — | no model, no route, no service | **Not implemented** |
| Incident / inspection / lab-record APIs | — | no model, no route | **Not implemented** |
| Product-user reading submission (personal device → API) | — | only `GET /product/*` exists | **Not implemented** |
| Device activation endpoint (`POST /product/activate`) | — | activation only happens as a side effect of registration with `product_code` | **Not implemented** |
| Rate limiting / account lockout | — | absent | **Not implemented** |

---

## 3. Frontend

| Screen / component | Route | Real data? | Notes | Status |
|---|---|---|---|---|
| Public QR water-body page | `/public/source/:code` | **Yes** — `publicApi.getStationByCode`, `getLatestReading`, `getReadingHistory`, `getSuitability` | Shows provenance ("physical station hardware" vs "simulated"), relative-index badge, trend chart, 6-use suitability | **Verified** (frontend tests + live API) |
| Public QR code generation | `PublicPageQrCard` | Yes | Encodes `${VITE_PUBLIC_BASE_URL or origin}/public/source/<code>`; warns when the URL is localhost-only | **Verified** (test asserts encoded URL) |
| Login / Register | `/user/login`, `/user/register` | **Yes** — `authApi` | Token in `localStorage` via `lib/auth.ts` | **Verified** |
| Product dashboard | `/user/dashboard` | **Yes** — `productApi.getProfile` | Device tiles come from `/product/devices` on the devices page | **Verified** |
| Product devices | `/user/devices` | **Yes** — `productApi.getDevices` | Shows bound device + status | **Verified** |
| Device activation page | `/user/activate` | **No** | Form accepts any code and navigates to the dashboard; no API call. Binding actually happens in `/auth/register` | **UI-only** |
| Personal water check | `/user/check-water` | **No** | 3-second `setTimeout`, then a hard-coded result screen | **UI-only** |
| Personal check history | `/user/history` | **No** | `HISTORY` array of 5 rows | **UI-only** |
| Authority command center | `/authority` | **Partial** | Station list (`authorityApi.getAllStations`) and `MlSummaryCard` are real. KPI cards, water-source cards, alert panel, trend chart, prediction card and `SensorHealth` use `mockData` | **Partial** |
| Live IoT monitoring | `/authority/monitoring` | **Partial** | Backend station selector, `TelemetryStatusCard`, `MlIndicator`, `PublicPageQrCard`, `WaterSuitabilitySection` are real. The upper probe/source board is `mockData` | **Partial** |
| Station detail | `/authority/stations/:stationId` | **Partial (broken join)** | Page is keyed by mock ids (`source-tg-halli`), so `MlLatestCard` calls the real API with a mock id and gets 404 → "unavailable". Telemetry cards are not present here; `LiveMonitoring` is the real station view | **Partial** |
| Water map | `/authority/map` | **Yes (data)** / placeholder (visual) | Fetches real stations; the map canvas is a styled placeholder ("Interactive GIS Placeholder — Mapbox Ready") | **Partial** |
| Analytics | `/authority/analytics` | **Partial** | Source selector is `mockData`; `ModelHealthCard` is real; SHAP section is an explicit placeholder | **Partial** |
| Alerts / Incidents / Inspections / Laboratory | `/authority/*` | **No** | `mockAlerts`, `mockIncidents`, `mockInspections`, `mockLabRecords`; acknowledge/reset is local state only | **UI-only** |
| Water sources list | `/authority/sources` | **No** | `mockWaterSources` | **UI-only** |
| Nearby sources / Warnings | `/public/sources`, `/public/warnings` | **No** | `mockWaterSources` | **UI-only** |
| Public water check | `/public/check-water` | **No** | Client-side text generation from mock source risk; the `setTimeout` simulates analysis | **UI-only** |
| Public saved checks | `/public/my-checks` | **No** | Hard-coded `mockSavedChecks` | **UI-only** |

---

## 4. Machine learning

| Item | Reality | Status |
|---|---|---|
| Isolation Forest artifact | `ml/models/isolation_forest.joblib`, 137,625 bytes, sha256 `54697d04…` | **Verified** present, loads |
| Random Forest artifact | `ml/models/random_forest_classifier.joblib`, 302,761 bytes, sha256 `c3c66281…` | **Verified** present, loads |
| XGBoost artifact | `ml/models/xgboost_deterioration.joblib`, 616,031 bytes, sha256 `e4fc5402…` | **Verified** present, **not served** |
| RF evaluation | 15,120 held-out rows, accuracy 0.999868, macro F1 0.999843, ROC-AUC 1.0 | **Verified** (rebuilt) |
| IF evaluation | 9 readings scored, 4 flagged (44.4 %), scores −0.0225…0.1032 | **Verified** (rebuilt) — descriptive only |
| XGB evaluation | 1,139 test rows, accuracy 0.9438, balanced accuracy 0.5376, Unsafe recall 0.111 | **Verified** (rebuilt) |
| SHAP explainability | CSVs + PNGs in `ml/data/processed/` | **Verified artifacts**, not exposed by any API |
| Live inference feature contract | 4 features, named DataFrame, fixed order | **Verified** (`ml_service.py` + tests) |
| Model retraining in production | — | **Not implemented / by design** |
| Drift detection, monitoring, scheduled retraining | — | **Not implemented** |

---

## 5. Data engineering

| Item | Reality | Status |
|---|---|---|
| 5 source datasets | 4 USGS CSVs + 1 benchmark table | **Verified** |
| Cleaned copies | `ml/data/processed/cleaned/cleaned_*.csv`, 6 files, sources unmodified (sha256 re-checked) | **Verified** (`clean_datasets.py` run) |
| Cleaning report | `ml/reports/dataset_cleaning_report.{json,md}` | **Verified** generated |
| Leakage-safe splits | stratified 70/15/15 (seed 42) for supervised; chronological 70/15/15 with global timestamp boundaries for forecasting | **Verified** (`ml/tests/test_data_leakage.py`) |
| Telemetry split usability | 9 rows → 6 train / 0 validation / 3 test. **Too small to train a meaningful model**; the shipped Isolation Forest is a pipeline demonstration | **Limitation** |
| Dataset provenance record | No source URL, license or collection date is stored for `water_quality_dataset1.csv`; the USGS files carry station id + timestamps but no download script | **Gap** |

---

## 6. Security and operations findings

These are real issues found by reading the code; they belong in the "limitations / future work"
slide rather than being discovered by an examiner.

| Finding | Severity | Detail | Fix direction |
|---|---|---|---|
| Self-service role selection | **High** | `UserRegisterRequest.role` accepts `AUTHORITY`; anyone can `POST /api/auth/register` with `"role":"AUTHORITY"` and receive authority access | Force `PRODUCT_USER` in the endpoint; promote authorities via seed/DB only |
| Permissive CORS | Medium | `allow_origins=["*"]` together with `allow_credentials=True` | Restrict to the real frontend origins |
| Default JWT secret in code | Medium | `JWT_SECRET_KEY` defaults to a literal in `core/config.py`; tests trigger `InsecureKeyLengthWarning` | Require the env var in non-dev; fail fast when unset |
| Public GET has a write side effect | Low | `/public/stations/{code}/suitability` persists assessment rows | Acceptable (idempotent unique constraint) but worth stating |
| No rate limiting | Low | Login and public endpoints unthrottled | Add a gateway/limiter before any real deployment |
| Tokens in `localStorage` | Low | XSS-exfiltratable | httpOnly cookie or short-lived tokens + refresh |
| Demo credentials documented | Low | `authority@hydrasense.local / DemoAuthority123!` is seeded | Change before any deployment |

---

## 7. What to say in one sentence per area

- **Sensing:** "The ESP32 station publishes validated JSON telemetry; uncalibrated sensors send
  `null`, never fake numbers."
- **Ingestion:** "The backend validates, de-duplicates and stores each reading, then derives a
  suitability assessment and, when all four values exist, an ML analysis."
- **ML:** "Two scikit-learn models run live; a third XGBoost experiment is offline only. The report
  publishes both the suspiciously high benchmark accuracy and the realistic imbalanced-series
  metrics."
- **Standards:** "Suitability is BIS IS 10500 / CPCB based, excludes simulated and relative-index
  data, and can never call drinking water 'safe' without lab tests."
- **Public access:** "Every station has a QR-linked public page that shows real readings and the
  six-use suitability assessment."
- **Product user:** "Accounts, device binding and the device list are real; the personal water-check
  flow is still a UI prototype."
- **Authority dashboard:** "Telemetry, ML analysis, model health and suitability panels are live;
  the operational workflow screens (alerts, incidents, inspections, lab) are prototypes."
