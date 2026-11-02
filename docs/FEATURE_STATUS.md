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
| **UI-only** | 8 screens | incidents/inspections/laboratory (mock data, but banner-labelled prototypes), water sources, nearby sources, warnings, public water check, public saved checks |
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
| Standards-based suitability (4 uses, BIS/CPCB) | `water_suitability.py` (685 lines) | `tests/test_water_suitability.py` (96 targeted tests) | **Verified** |
| Suitability persisted as derived rows | `water_suitability_assessments`, unique constraint | migration + persistence tests | **Verified** |
| Suitability computed at ingestion | `mqtt_service.py` lines ~313-328 | code read; covered indirectly by `test_telemetry` | **Verified (code)** |
| Public suitability endpoint | `GET /public/stations/{code}/suitability` | `test_water_suitability` public cases | **Verified** |
| Password hashing (argon2 via `pwdlib`) | `core/security.py` | login tests | **Verified** |
| Alert generation / notification | `app/services/alerting.py`, `alert_thresholds.py`, `GET /product/alerts`, `/product/alerts/profile` | `tests/test_simulation_and_alerts.py` (danger levels, index-vs-NTU, profile classification) | **Verified** |
| Authority station alerts endpoint | `GET /api/authority/alerts` (`authority.py`, shared `alerting.py`) | `tests/test_authority.py` (auth required, real stations, simulated labelling) | **Verified** |
| Incident / inspection / lab-record APIs | — | no model, no route (pages banner-labelled as prototypes) | **Not implemented** |
| Persistent simulation controls | `app/services/simulation_service.py`, `simulation_runs` (migration `c1d2e3f4a5b6`), `POST /simulation/start|pause|generate` | `tests/test_simulation_and_alerts.py` (restart-safe singleton, lease, seeded reproducibility) | **Verified** |
| Baseline forecasting with readiness + evaluation gates | `app/services/forecasting.py`, `GET /authority/stations/{code}/forecast` | `tests/test_forecasting.py` (11 tests: insufficient data, holdout gate, horizon bounds, auth) | **Verified** |
| Per-reading ML availability (index exclusion message) | `app/services/ml_availability.py`, analysis endpoints | `tests/test_ml_availability.py` | **Verified** |
| Product-user reading submission (`POST /product/tests`, live window) | `app/api/v1/product.py`, `product_test_service.py` | `tests/test_product_tests.py` (stability, calibration, strict TDS rule) | **Verified** |
| Device activation endpoint (`POST /product/activate`) | `app/api/v1/product.py` | `tests/test_product_tests.py::test_activate_unowned_product_code` + cases | **Verified** |
| Rate limiting (auth endpoints) | `app/core/rate_limit.py`, `rate_limit_counters` (migration `e7f8a9b0c1d2`) | `tests/test_security_hardening.py` (429 within/beyond limit, disabled mode, shared-row persistence) | **Verified** — login/register only; no account lockout, no global gateway limit |

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
| Authority alerts | `/authority/alerts` | **Yes** — `authorityApi.getAlerts` → `GET /api/authority/alerts` | Real alerts derived from each station's latest reading via the shared alerting service; loading / empty / error / session-expired states; acknowledgement is local-only | **Verified** |
| Incidents / Inspections / Laboratory | `/authority/incidents`, `/authority/inspections`, `/authority/laboratory` | **No** — `mockIncidents`, `mockInspections`, `mockLabRecords` behind a visible `PrototypeBanner` naming the missing endpoints and stating lab records are not sensor measurements | Demonstration only | **UI-only (labelled prototype)** |
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

Verification: backend `462 passed`, ML `140 passed`, frontend `vitest 70 passed`, `npm run build` exit 0,
`npm run lint` 0 errors, `alembic heads` = `b8c9d0e1f2a3` (single head).

### Resolved in this pass (final remediation, `feature/final-remediation`, 2026-10-28)

| Area | What was enforced | Resolution | Evidence |
|---|---|---|---|
| Turbidity-unvalidated downgrade | pH and TDS passing could still surface a clean `WITHIN_PROJECT_TARGETS` verdict while turbidity was an uncalibrated relative index or missing | Any use whose profile rates turbidity (drinking, domestic, general) now caps the best result at `REVIEW_RECOMMENDED` (canonical `caution`) with an explicit warning naming the reason; `not_comparable`/`not_measured` turbidity can never read as a full pass | `water_screening._overall_status` + `assess()` warning; regression tests in `tests/test_product_tests.py`, `tests/test_product_screening.py`, `tests/test_simulation_and_alerts.py` |
| Authority alerts were mock | `/authority/alerts` rendered `mockAlerts` with no backend | New `GET /api/authority/alerts` (authority-role, `get_current_authority`) derives alerts from each active station's latest stored reading via the shared `reading_alerts`/`alert_response` service, ordered newest-first, `limit` capped; frontend `Alerts.tsx` wired with loading/empty/error/unauthorized states and simulated labels preserved | `backend/app/api/v1/authority.py`; `tests/test_authority.py` (401 unauthenticated, real data, shape); frontend `npm run build`/`npm run lint` clean |
| Prototype authority pages unlabelled | Incidents/Inspections/Laboratory rendered demonstration records with no indication they are not real workflows | Visible `PrototypeBanner` on all three pages naming the missing endpoints, marking records as demonstration, and stating laboratory entries are not four-sensor measurements | `frontend/src/components/authority/PrototypeBanner.tsx`; `Incidents.tsx`, `Inspections.tsx`, `Laboratory.tsx` |
| Production configuration only hand-checked | No way to prove the fail-fast settings behave under a production-like config | `backend/scripts/verify_production_config.py` runs the static checklist (APP_ENV, JWT secret strength/uniqueness, CORS allowlist, rate limits, proxy trust, HS256, token lifetime, DB URL) with PASS/FAIL/REVIEW; paired with `tests/test_production_config.py`; README gained the deployment verification checklist | `python scripts/verify_production_config.py` runs and exits 1 on a dev `.env` (expected); `python -m pytest tests/test_production_config.py` |
| Legacy schema drift undocumented | `alembic check` fails on legacy tables/columns with no written analysis | Exact drift inventoried in README (*Database schema drift*): tables `water_tests`, `water_test_assessments`, `water_test_predictions` + indexes and columns `product_devices.device_name`/`expires_at`; grep proves no application code references them; no drops, no history rewrite | `alembic check` output captured; `alembic heads` = `b8c9d0e1f2a3` |

### Resolved in this pass (implementation sprint: device login, notifications, incidents, QR, ML, security)

| Area | What was enforced | Resolution | Evidence |
|---|---|---|---|
| Personal login by printed device number | Spec required logging in with the device number (`HSD-0001-K7M2Q9` → `ESP32-HS-001` / `ARK-001`); only e-mail login existed | `POST /api/auth/device-login` resolves the printed number to its bound account, returns generic errors (no number enumeration), shares the login rate-limit budget; registry model + migration `f1e2d3c4b5a6`; `seed_demo.py` seeds the first device | `tests/test_device_registry.py` (unknown/unbound/inactive numbers, one-device-per-account, activation limit, 429) |
| Notifications had no delivery channel | Alerts were computed but nothing was sent, and there was no preference/dedup model | `notifications` table + migration `a7b8c9d0e1f2` and `app/services/notification_service.py`: severity levels, dedup key + cooldown window (`NOTIFICATION_COOLDOWN_SECONDS`), per-user category preferences, delivery log with `sent` / `skipped_unconfigured` / `failed` honesty; SMTP empty = recorded as skipped, never breaks alerting; endpoints `GET /product/notifications`, `GET|PUT /product/notification-preferences/{category}` | `tests/test_notifications.py` (dedup, cooldown, preference gating, never-on-null, SMTP-unconfigured honesty) |
| No station QR generation | QR existed only as a frontend-built URL | Backend `GET /api/authority/stations/{code}/qr` + `.png` / `.svg` / `.pdf` label generation from `PUBLIC_BASE_URL`, authority-only; authority `QrCodes.tsx` renders real station list + live preview + downloads with loading/empty/error/unauthorized states | `tests/test_qr.py`; frontend `npm run build` / `npm run lint` clean |
| No incident or laboratory workflow | Incidents existed only as frontend mock data | `app/api/v1/incidents.py` + `incident_service.py`: AUTHORITY-only create/list/detail, forward-only transitions `raised → lab_notified → sample_collected → result_received → resolved` with an audit event per step, lab contacts, verbatim lab results forced to `source=laboratory` / `derived_from_sensors=false`, PDF report generation (`report.pdf`) and SMTP-reported delivery outcomes; migration `b8c9d0e1f2a3` | `tests/test_incidents.py` (RBAC 401/403, validation, invalid transitions, sample mismatch, non-finite rejection, PDF content honesty) |
| Anomaly model trained on 9 rows / skewed demo data | The shipped Isolation Forest could not generalise and artifacts were unversioned | Anomaly model retrained on real cleaned distributions with versioned artifacts and metrics stored beside them; `ml/scripts/inspect_datasets.py` audits external datasets (columns, units, provenance, duplicates, missing) and `ml/reports/evaluation_report.md` recomputes metrics from artifacts | `python -m pytest ml/tests -q` (140 passed) |
| Client-side suitability verdicts on the public WaterCheck page | `WaterCheck.tsx` computed pass/fail in the browser from mock data | Page rewritten to call the real `GET /api/public/stations/{code}/suitability` and render the backend result; backend gained `GET /api/public/stations` for the picker | `backend/tests/test_public.py`; frontend `ml-integration.test.tsx` asserts four use cards and no DO |
| Mock screens unlabelled or fabricating numbers | Command Center, Water Sources, Analytics, Station Detail, Nearby, Warnings and the sidebar probe count all presented demo data as real | Every one carries a visible demo notice with the exact reason; the fabricated probe count was removed; `MyChecks` “Safe” badge replaced with honest wording; `PrototypeBanner` no longer claims “no backend exists” for incidents (the backend does now) | `DemoDataNotice.tsx`, `PrototypeBanner.tsx`; frontend suite 70 passed |
| MQTT anonymous broker + unbounded ingestion | Backend could connect anonymously; absurd values (e.g. TDS 10⁹) were stored | `MQTT_USERNAME`/`MQTT_PASSWORD` required in production (fail-fast), `MQTT_ALLOW_ANONYMOUS` explicit opt-in rejected by the checker, `MQTT_USE_TLS` required for non-loopback brokers, per-run TLS/CA wiring and reconnect backoff in `mqtt_service.py`; ingestion bounds TDS ≤ 50 000 ppm, turbidity ≤ 4 000 NTU, index ≤ 100, non-finite rejected; `POST /product/activate` throttled (`RATE_LIMIT_ACTIVATE_MAX`) | `tests/test_security_hardening.py`, `tests/test_production_config.py`, `tests/test_telemetry.py`, `tests/test_device_registry.py` |
| Deployment checklist incomplete | Static checker missed MQTT, TLS, public URL and secret hygiene | `verify_production_config.py` now checks MQTT auth, broker TLS, HTTPS `PUBLIC_BASE_URL`, finite ingestion bounds and runs `git ls-files` for tracked secret files; canonical checklist with 14 still-unrun real-environment steps in `docs/DEPLOYMENT_VERIFICATION.md` | `python scripts/verify_production_config.py` (exits 1 on a dev `.env`, as intended) |

### Resolved in this pass (rule-based recommendation engine, 2026-10-30)

| Area | What was enforced | Resolution | Evidence |
|---|---|---|---|
| Advice derived from triggered rules | The spec requires recommendations keyed by `(use, parameter, direction)` returned only for caution / not-suitable / insufficient results, built from the rules the engine actually triggered | New `app/services/recommendations.py` with a closed rule table over `(use, parameter, direction)`; both engines attach it to every assessment (`suitability_engine.evaluate`, `water_suitability.assess_use`), and it returns an empty set for `within_configured_ranges` so no advice is invented for a rule that did not fire | `tests/test_recommendations.py` (206 tests: rule-table contract, per-rule content, behaviour, API surfaces) |
| Only the four inputs can shape advice | Causes/actions must never name an unmeasured parameter | `UNMEASURED_TERMS` guard: every rule's causes/actions/avoid are tested against it; unmeasured quantities (EC/SAR, microbiology, DO, heavy metals, rainfall, ML outputs) appear **only** in `missing_assessments`, each phrased "not measured by these sensors" | `test_rule_never_names_an_unmeasured_parameter`, `test_unmeasured_external_inputs_cannot_shape_advice` |
| Honest wording | Causes asserted, drinking advice implying safety, advice for temperature | Causes are worded "possible … — a single reading cannot identify the source"; every drinking action ends with laboratory confirmation and the explicit "cannot confirm that the water is safe"; no rule exists for temperature (no configured threshold) | `test_rule_causes_are_hedged_not_asserted`, `test_drinking_advice_*`, `test_no_rule_exists_for_temperature` |
| Incident steps are authority-only | Public/product responses must not expose the incident workflow | `recommendations.build(authority=True)` is invoked only on authority routes (`_add_authority_actions` in `app/api/v1/authority.py`); public and product schemas default to an empty set | `test_public_suitability_returns_recommendations`, `test_authority_suitability_adds_incident_steps`, `test_authority_actions_require_the_authority_view` |
| Direction recorded by the engine | Advice differs for above/below breaches | `water_suitability._direction()` records which side of the configured range was evaluated; the screening engine passes its own `direction` through | `test_pH_direction_changes_the_advice`, `test_high_tds_is_severe_and_high_urgency` |

Verification: backend `668 passed` (462 existing + 206 new), exit 0, 378 s; ML `140 passed`;
frontend `vitest 74 passed`, `tsc --noEmit` exit 0, `npm run build` exit 0, `npm run lint` 0 errors.

### Remaining limitations

| Finding | Severity | Detail | Fix direction |
|---|---|---|---|
| Tokens in `localStorage` | Low | XSS-exfiltratable | httpOnly cookie or short-lived tokens + refresh |
| Demo credentials documented | Low | `authority@hydrasense.local / DemoAuthority123!` is seeded | Change before any deployment |
| Public GET has a write side effect | Low | `/public/stations/{code}/suitability` persists assessment rows | Acceptable (idempotent unique constraint) but worth stating |
| Rate limiting covers auth + activation only | Low | `/auth/login`, `/auth/register`, `/auth/device-login` and `/product/activate` are throttled; public and other authority endpoints are not, and no global gateway limit exists | Extend `rate_limit(...)` dependencies or add an edge/WAF rule before real deployment |
| Rate-limit storage is PostgreSQL-only | Info | Counters use `SELECT ... FOR UPDATE` row locks; a non-PostgreSQL store would need its own atomic backend | Keep PostgreSQL, or swap in Redis if the stack ever moves |
| Production configuration not verified | Info | The production CORS allowlist, `APP_ENV=production` secret, and proxy settings are now covered by `scripts/verify_production_config.py` + `tests/test_production_config.py`, but those are **local static checks** — no production deployment has been exercised | Run the README *Deployment verification checklist* on the real environment before claiming production security |
| Authority prototype pages still mock | Medium | Incidents now have a complete, tested backend (`incidents.py` + service + PDF) but `Incidents.tsx` / `Laboratory.tsx` still render `mockData` — their banner now states exactly that the backend exists and the page is not wired to it; Inspections has no backend at all; Command Center, Live Monitoring's top board, Water Sources and parts of Station Detail still mix mock data | Wire the Incidents and Laboratory pages to the existing endpoints (list/create/detail/transition/PDF), then decide whether to build Inspections or drop it from navigation |
| Public check history not persisted | Low | The public (unauthenticated) My Checks page shows clearly-labelled demonstration entries — there is no endpoint storing public check history | Persist public checks or drop the page from navigation |
| No index-trained ML model / no probabilistic forecast | Info | Holdout MAE is an evaluation measure, not a prediction interval; turbidity-index readings keep the explicit "ML prediction unavailable" status | Paired index + reference-labelled data required before an index model; more history before stronger forecasts |
| Intentional schema drift open | Info | `alembic check` still fails: legacy `water_tests` / `water_test_assessments` / `water_test_predictions` tables and `product_devices.device_name`/`expires_at` columns exist in the database but not in the models (verified unreferenced; documented in README) | Write a reviewed migration only if the historical rows are expendable — never autogenerate-and-apply blindly |
| Alerts acknowledgement not persisted | Low | Acknowledging an alert is local UI state; there is no alert history, SMS or webhook dispatch | Add an `alert_events` table + acknowledge endpoint if persistence is needed |

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
  alerts and the gated forecast are live, and the incident/lab workflow has a
  full tested backend with PDF reports; the incidents, inspections and lab
  screens themselves are still labelled prototypes."
