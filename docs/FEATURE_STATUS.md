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
| **Verified** | backend contracts, public QR page, auth, suitability, ML serving, evaluation transparency, product alerts + threshold profile, forecast readiness gates | MQTT handler, RBAC, ingestion-time assessment, `/public/*`, `/authority/ml/status`, `alerting.py`, `forecasting.py` |
| **Implemented (manual check)** | 3 | ESP32 firmware, simulator scenarios, QR scanned from a phone over LAN |
| **Partial** | 5 screens | command center, live monitoring board, station detail, analytics, water map |
| **UI-only** | 9 screens | authority alerts/incidents/inspections/laboratory, water sources, nearby sources, warnings, public water check, public saved checks |
| **Not implemented** | 4 backends | incident workflow, inspection workflow, lab-record store, GIS map backend (the map canvas is a placeholder, not a backend) |

> **Resolved since this audit** (see README *Scientific Honesty & Limitations* →
> *Resolved in this pass*): product alerts + versioned threshold profile,
> `POST /product/activate`, the product-user check-water/history flow (now
> API-backed), persistent multi-worker simulation state, per-reading ML
> availability messages, and the validated baseline forecast endpoint. The
> security findings in §6 remain open.

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
| Alert generation / notification | `app/services/alerting.py`, `alert_thresholds.py`, `GET /product/alerts`, `/product/alerts/profile` | `tests/test_simulation_and_alerts.py` (danger levels, index-vs-NTU, profile classification) | **Verified** |
| Incident / inspection / lab-record APIs | — | no model, no route | **Not implemented** |
| Persistent simulation controls | `app/services/simulation_service.py`, `simulation_runs` (migration `c1d2e3f4a5b6`), `POST /simulation/start|pause|generate` | `tests/test_simulation_and_alerts.py` (restart-safe singleton, lease, seeded reproducibility) | **Verified** |
| Baseline forecasting with readiness + evaluation gates | `app/services/forecasting.py`, `GET /authority/stations/{code}/forecast` | `tests/test_forecasting.py` (11 tests: insufficient data, holdout gate, horizon bounds, auth) | **Verified** |
| Per-reading ML availability (index exclusion message) | `app/services/ml_availability.py`, analysis endpoints | `tests/test_ml_availability.py` | **Verified** |
| Product-user reading submission (`POST /product/tests`, live window) | `app/api/v1/product.py`, `product_test_service.py` | `tests/test_product_tests.py` (stability, calibration, strict TDS rule) | **Verified** |
| Device activation endpoint (`POST /product/activate`) | `app/api/v1/product.py` | `tests/test_product_tests.py::test_activate_unowned_product_code` + cases | **Verified** |
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
| Device activation page | `/user/activate` | **Yes** — `productApi.activateProduct` → `POST /product/activate` with real error handling | Backend rejects unowned/invalid codes (tested) | **Verified** |
| Personal water check | `/user/check-water` | **Yes** — `productApi.startTest` → `POST /product/tests` (stable live window or labelled demo) | Result screen reads the saved assessment from the API | **Verified** (frontend + backend tests) |
| Personal check history | `/user/history` | **Yes** — `productApi.getTests` → `GET /product/tests` | Private, server-side per-user history | **Verified** |
| Authority command center | `/authority` | **Partial** | Station list (`authorityApi.getAllStations`) and `MlSummaryCard` are real. KPI cards, water-source cards, alert panel, trend chart, prediction card and `SensorHealth` use `mockData` | **Partial** |
| Live IoT monitoring | `/authority/monitoring` | **Partial** | Backend station selector, `TelemetryStatusCard`, `MlIndicator`, `PublicPageQrCard`, `WaterSuitabilitySection` are real. The upper probe/source board is `mockData` | **Partial** |
| Station detail | `/authority/stations/:stationId` | **Partial (broken join)** | Page is keyed by mock ids (`source-tg-halli`), so `MlLatestCard` calls the real API with a mock id and gets 404 → "unavailable". Telemetry cards are not present here; `LiveMonitoring` is the real station view | **Partial** |
| Water map | `/authority/map` | **Yes (data)** / placeholder (visual) | Fetches real stations; the map canvas is a styled placeholder ("Interactive GIS Placeholder — Mapbox Ready") | **Partial** |
| Analytics | `/authority/analytics` | **Partial** | Source selector and trend chart are `mockData`; `ModelHealthCard` is real; `PredictionCard` is now a real forecast card (reads `GET /authority/stations/{code}/forecast`); the old fabricated SHAP grid was replaced by an honest evaluation explainer | **Partial** |
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
| Turbidity-index model (0–100 inputs) | no labelled dataset exists; index readings deliberately report “ML prediction unavailable for Turbidity Index readings.” | **Limitation (documented)** — requirements + workflow in `docs/TURBIDITY_INDEX_ML.md` |
| Baseline forecasting (Ridge vs persistence, holdout-gated) | `app/services/forecasting.py`; points only when holdout MAE beats persistence | **Verified** (`tests/test_forecasting.py`) — no probabilistic model claimed |

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

## 6. Security and operations

### Resolved in this pass (security hardening, 2026-10-25)

| Finding | Severity (before) | Resolution | Evidence |
|---|---|---|---|
| Self-service role selection | **High** | `register()` rejects any role other than `PRODUCT_USER` with 403; authority accounts only via seed/admin path | `tests/test_product_tests.py::test_public_registration_cannot_create_an_authority`, `tests/test_security_hardening.py::test_registration_cannot_escalate_to_authority` |
| Permissive CORS | Medium | `allow_origins=["*"]` + credentials removed; explicit allowlist from `CORS_ALLOW_ORIGINS` (`app/core/cors.py`). Empty = local dev/preview origins outside production, deny-all in production. `*` rejected when credentials are enabled and in production | `tests/test_security_hardening.py` (7 CORS tests incl. trusted/untrusted middleware checks) |
| Default JWT secret in code | Medium | `JWT_SECRET_KEY` has **no default**; startup raises when it is missing. Production also refuses short (<32 char) or known-insecure values; development only warns. Never generates a replacement key | `tests/test_security_hardening.py` (JWT tests incl. app-startup failure) |
| No rate limiting | Low | Database-backed fixed-window limiter on `POST /api/auth/login` and `POST /api/auth/register`, returning **429 + `Retry-After`**. Counters live in the `rate_limit_counters` table (migration `e7f8a9b0c1d2`) so limits hold across workers and restarts | `tests/test_security_hardening.py` (within/beyond limit, disabled mode, shared-row persistence) |

Configuration lives in `backend/.env.example` (`CORS_*`, `RATE_LIMIT_*`, `JWT_SECRET_KEY`).
Run `alembic upgrade head` to create the rate-limit table.

### Resolved in this pass (validation pass, `feature/software-hardening-and-validation`, 2026-10-26)

| Area | What was wrong | Resolution | Evidence |
|---|---|---|---|
| Alerts page threshold card | Claimed unmeasured inputs: “Turbidity > 25 NTU, DO < 3.5 mg/L, or AI Risk > 90%”, plus an automated SMS/webhook dispatch claim | Rewritten to the four monitored sensors (turbidity **index** bands 55/85, TDS 500/2000 mg/L references, pH 6.5–8.5), labelled project-configured (not BIS/WHO), linked to `GET /api/product/alerts/profile`, with an explicit “no SMS/webhook dispatch implemented” note and a statement that DO/microbial/chemical parameters are never part of the tiers | `frontend/src/pages/authority/Alerts.tsx`; `npm run build`, `npm run lint` clean |
| Public “My Checks” page | Fabricated history for unrelated water bodies (Hebbal Lake, Thippagondanahalli, Jakkur) with turbidity quoted **in NTU** and “Safe” verdicts | Replaced with labelled demonstration entries for the three rivers, turbidity shown as a relative index (NTU calibration called out), verdicts phrased as screening outcomes, and a visible banner that public history is not persisted yet | `frontend/src/pages/public/MyChecks.tsx` |
| Three-river demo scope | — (verified, no change needed) | DB `water_sources` contains exactly ARKAVATHI / CAUVERY / VRISHABHAVATHI; seed script and `mockData.ts` list only those three | `select source_code,name from water_sources` → 3 rows; `backend/scripts/seed_demo.py`; `frontend/src/data/mockData.ts` |
| Sensor/alert honesty | — (verified, no change needed) | Alerts never trigger on missing/stale readings (warning/freshness instead), missing values are never replaced by zero, simulated rows are labelled, and turbidity index is never compared with NTU | `tests/test_simulation_and_alerts.py`, `tests/test_telemetry.py`, `tests/test_product_screening.py` |

Verification run in this pass: backend `342 passed`, ML `140 passed`, frontend `vitest 70 passed`,
`npm run build` exit 0, `npm run lint` 0 errors, `alembic current` = `e7f8a9b0c1d2` (head).

### Resolved in this pass (central four-parameter suitability engine, 2026-10-26)

| Area | What was enforced | Resolution | Evidence |
|---|---|---|---|
| Single central engine | Suitability decisions were computed in two engines with different status vocabularies and no pinned input contract | `app/services/suitability_engine.py` is the enforced façade: it accepts **exactly** `ph`, `tds`, `temperature`, `turbidity` (any other key raises `ValueError` — DO, ML scores, rainfall, history, location can never influence a decision), delegates to the per-purpose profiles, and declares its inputs/exclusions in every response | `tests/test_suitability_engine.py` (input-contract, exclusion and rejection tests) |
| Canonical result vocabulary | Two legacy vocabularies (product/live `WITHIN_PROJECT_TARGETS…`, station `preliminary_suitable…`) | One four-state vocabulary in `app/services/screening_states.py`: `within_configured_ranges` / `caution` / `outside_configured_ranges` / `insufficient_data`, mapped from both engines with unknown codes rejected rather than guessed | `screening_states.py`; station assessments now carry `state` + `state_label` |
| Persistence & API | Canonical state was not stored or served | `overall_state` column on `product_water_tests` and `live_water_assessments` (migration `a9b0c1d2e3f4`, backfilled from stored JSON), served next to the unchanged legacy `overall_status` so existing UI keeps working | `models/water_test.py`, `schemas/product_test.py`, migration run at head |
| Precedence (never a false positive) | Invalid temperature/turbidity could ride along with a green result | Invalid, stale, unstable or non-finite readings of any of the four sensors now collapse the whole assessment to `insufficient_data` | `water_screening._overall_status` + boundary tests (pH/TDS/temperature/missing/NaN/stale/unstable/calibration) |
| Turbidity honesty | — (verified and pinned) | Relative index 0–100 is `not_comparable` and never judged against 1/5 NTU limits; only a genuinely NTU-calibrated measurement uses the NTU references | index-vs-NTU tests in both engines |

Verification: backend `391 passed` (342 + 49 new), frontend `vitest 70 passed`, `npm run build` exit 0,
`npm run lint` 0 errors, `alembic current` = `a9b0c1d2e3f4` (head).

### Remaining limitations

| Finding | Severity | Detail | Fix direction |
|---|---|---|---|
| Tokens in `localStorage` | Low | XSS-exfiltratable | httpOnly cookie or short-lived tokens + refresh |
| Demo credentials documented | Low | `authority@hydrasense.local / DemoAuthority123!` is seeded | Change before any deployment |
| Public GET has a write side effect | Low | `/public/stations/{code}/suitability` persists assessment rows | Acceptable (idempotent unique constraint) but worth stating |
| Rate limiting covers auth only | Low | `/auth/login` and `/auth/register` are throttled; public and authority endpoints are not, and no global gateway limit exists | Extend `rate_limit(...)` dependencies or add an edge/WAF rule before real deployment |
| Rate-limit storage is PostgreSQL-only | Info | Counters use `SELECT ... FOR UPDATE` row locks; a non-PostgreSQL store would need its own atomic backend | Keep PostgreSQL, or swap in Redis if the stack ever moves |
| Production configuration not verified | Info | The production CORS allowlist, `APP_ENV=production` secret, and proxy settings are code-verified only — no production deployment has been exercised | Verify on the real deployment before claiming production security |
| Authority prototype pages still mock | Medium | Incidents, Inspections and Laboratory render demonstration content with no backend endpoints; Command Center, Live Monitoring's top board, Water Sources and parts of Station Detail still mix mock data | Wire them to the existing endpoints or label each page "prototype" in the UI |
| Public check history not persisted | Low | The public (unauthenticated) My Checks page shows clearly-labelled demonstration entries — there is no endpoint storing public check history | Persist public checks or drop the page from navigation |
| No index-trained ML model / no probabilistic forecast | Info | Holdout MAE is an evaluation measure, not a prediction interval; turbidity-index readings keep the explicit "ML prediction unavailable" status | Paired index + reference-labelled data required before an index model; more history before stronger forecasts |

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
- **Product user:** "Accounts, device binding, activation, the live water-check
  flow and the private test history are all API-backed and tested; alerts come
  from the real threshold profile."
- **Authority dashboard:** "Telemetry, ML analysis, model health, suitability,
  alerts and the gated forecast are live; the operational workflow screens
  (incidents, inspections, lab) are still prototypes."
