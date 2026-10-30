# HydraSense — Project Audit Report

Audit date: 2026-10-24. Scope: the full repository (`backend/`, `frontend/`, `ml/`, `firmware/`).
Method: read the source, ran the test suites, ran the evaluation and cleaning pipelines, inspected
every dataset, and queried the running API where possible. Nothing in this report is copied from a
design document; where a claim could not be verified it is marked **UNVERIFIED**.

---

## 1. What the project genuinely does

HydraSense ingests water-quality telemetry from ESP32 stations or a Python simulator over MQTT,
validates and stores it in PostgreSQL, derives a standards-based suitability assessment for six
intended uses, attaches two live ML model outputs when the reading is complete, and exposes the data
through a public QR-linked page, a product-user area and an authority dashboard.

The implementation is strongest where honesty is hard: nullable measurements, per-row turbidity
units, provenance tags, explicit missing-parameter reporting, and an evaluation report that publishes
its own uncomfortable numbers.

## 2. Verified working features

Verified by executing code or tests in this checkout:

| Area | Evidence |
|---|---|
| JWT auth + argon2 hashing | `backend/tests` login/registration cases pass |
| Role-based access control | `tests/test_rbac.py` — 403 in both directions |
| Product-code binding at registration | registration tests; `product_devices` owner update |
| MQTT payload validation (12 rejection branches) | `tests/test_telemetry.py` |
| NULL-tolerant ingestion + provenance + diagnostics | `tests/test_telemetry.py` |
| Duplicate guard `(station, device, timestamp)` | same suite |
| Ingestion-time suitability for 6 uses | `water_suitability.py` + persistence tests |
| Turbidity unit contract (`ntu` vs `relative_index_0_100`) | migration + service + frontend tests |
| ML inference at ingestion, skipped honestly | `tests/test_ml_*.py` |
| Reading + ML analysis endpoints | backend + 27 frontend integration tests |
| Model health + evaluation report endpoint | `tests/test_ml_status.py` and frontend `model-health.test.tsx` |
| Public station / latest / history / suitability | public API tests + `PublicSource` tests |
| Station QR generation (png/svg/pdf) | `tests/test_qr.py` — backend endpoints + authority page |
| Device-number login | `tests/test_device_registry.py` — generic errors, one device per account, 429 |
| Notification dedup / cooldown / preferences | `tests/test_notifications.py` — SMTP-unconfigured reported honestly |
| Incident workflow + PDF report | `tests/test_incidents.py` — RBAC, forward-only transitions, verbatim lab results, PDF honesty |
| MQTT credentials + ingestion bounds enforced | `tests/test_security_hardening.py`, `tests/test_telemetry.py`, `tests/test_production_config.py` |
| Interactive API docs | `/docs`, `/openapi.json` |
| 882 automated tests | 668 backend, 140 ML, 74 frontend — all passing |

## 3. Features that are code-complete but not verified here

| Feature | Why not verified | Risk if claimed as working |
|---|---|---|
| ESP32 firmware on hardware | No device attached during audit | "Deployed station" claims are unsupported |
| MQTT broker end-to-end delivery | Broker not required for tests; handler tested directly | Low — the handler is the only custom logic |
| QR scan from a phone | Needs LAN URL and a second device | Low — URL construction is tested |
| Simulator scenarios | Needs a running broker | Low — code is straightforward |

## 4. Features that look real in the UI but are not

`✅ real API` / `🧪 mockData` / `🕳 placeholder`

| Screen | Data |
|---|---|
| Public QR page | ✅ |
| Login / Register / Dashboard / Devices | ✅ |
| Authority monitoring (station selector, telemetry, ML, suitability, QR) | ✅ |
| Authority command centre (stations + ML summary) | ✅ (rest of the page 🧪) |
| Water map | ✅ stations, 🕳 map canvas |
| Analytics | 🧪 selectors, ✅ model health, 🕳 SHAP |
| Authority alerts (station danger-level alerts) | ✅ `GET /api/authority/alerts` (acknowledgement still local) |
| Incidents / Inspections / Laboratory | 🧪 demo records behind a visible prototype banner (backend exists for incidents/lab — the page is not wired; Inspections has no endpoints) |
| Water sources | 🧪 |
| Station detail | 🧪 keyed by mock ids (real ML card 404s) |
| Public check-water / nearby sources / warnings / my checks | 🧪 |
| User check-water / history / activate | ✅ (`POST /product/tests`, `GET /product/tests`, `POST /product/activate`) |

Full matrix: [FEATURE_STATUS.md](FEATURE_STATUS.md).

## 5. Datasets actually used

| Dataset | Rows | Role | Provenance |
|---|---|---|---|
| `water_quality_dataset1.csv` | 100,800 | Random Forest training/eval | **UNVERIFIED** — no source recorded |
| `usgs_ph_2024.csv` | 10,000 | forecasting feature | USGS station `USGS-01649190`, Jan–Feb 2024, 5-min |
| `usgs_turbidity_2024.csv` | 10,000 | forecasting feature + target | same; **all Provisional** |
| `usgs_temperature_2024.csv` | 10,000 | forecasting feature | same |
| `usgs_conductance_2024.csv` | 10,000 | forecasting feature | same |
| `sensor_readings.csv` | 9 | kept for provenance only; no longer used to fit the Isolation Forest | own simulator, 2026-08-31 |

Derived: 7,601 synchronized USGS rows → 5,321/1,140/1,139 forecast splits; 70,560/15,120/15,120
supervised splits; 6/0/3 telemetry splits. Details: [DATASET_CATALOG.md](DATASET_CATALOG.md).

## 6. Cleaning actually performed

`ml/preprocessing/clean_datasets.py` (new) cleaned copies of all six datasets into
`ml/data/processed/cleaned/` and wrote `ml/reports/dataset_cleaning_report.{json,md}`.

- 140,809 rows in → 140,809 rows out, **0 rows removed** (the datasets were already clean).
- Source SHA-256 unchanged for all six files.
- USGS files reduced 12 → 6 columns by dropping constant/empty metadata columns.
- Benchmark columns renamed to the pipeline contract; values untouched.
- Telemetry cleaned by the existing Phase-5A cleaner (0 duplicates, 0 invalid).
- Numeric values proven identical to the sources; output proven to be a row-subset of input.

Report: [DATA_CLEANING_REPORT.md](DATA_CLEANING_REPORT.md).

## 7. What the ML genuinely predicts

| Model | Live? | Output | Honest meaning |
|---|---|---|---|
| Isolation Forest | yes | `anomaly_label`, `anomaly_score` | Unusual relative to the benchmark's feature distribution (70,560 training rows, unsupervised — labels unused); not contamination, and not this hardware's telemetry |
| Random Forest | yes | `Safe`/`Unsafe` + probabilities | The benchmark's deterministic label rule over 4 features; not potability |
| XGBoost | no | `deterioration_target` | Rule-based one-step deterioration indicator on USGS features |

Regenerated metrics (identical to the committed report):

- Random Forest: n=15,120, accuracy **0.999868**, macro F1 **0.999843**, ROC-AUC **1.0000**,
  confusion matrix `[[4535, 1], [1, 10583]]`.
- Isolation Forest: n=15,120 scored, **727 flagged** (rate 0.0481), scores −0.1002 … 0.1582.
- XGBoost: n=1,139, accuracy **0.943810**, balanced accuracy **0.537570**, macro F1 **0.528364**,
  ROC-AUC **0.628764**, Unsafe recall **0.1111** (3 of 27).

The 99.99 % figure is rule recovery on a same-distribution static split; the XGBoost balanced
accuracy is the realistic signal.

## 8. Verified end-to-end workflows

1. **Public QR flow** — open `/public/source/ARK-001` → station, latest reading, history, suitability
   from the API.
2. **Authority monitoring** — login → station selector → telemetry card (link state, provenance,
   NULL handling, diagnostics) → ML card → suitability → QR card.
3. **Model transparency** — `/authority/ml/status` → report presence, per-model load state, metrics.
4. **Product account** — register (optionally with a product code) → login → profile → device list.
5. **Ingestion contract** — `process_telemetry_payload` validated against 12+ rejection branches and
   the accept path (store → assess → infer).

## 9. How to run each component

| Component | Command | Needs |
|---|---|---|
| PostgreSQL schema | `cd backend && alembic upgrade head` | PostgreSQL |
| Seeds | `python scripts/seed_demo.py`, `python scripts/seed_ml_readings.py` | migrated DB |
| Backend | `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000` | DB, optional broker |
| Broker | Mosquitto on `:1883` with `allow_anonymous true` for LAN testing | — |
| Simulator | `python backend/simulator/sensor_simulator.py --scenario normal --interval 5` | broker |
| Frontend | `cd frontend && npm install && npm run dev` | Node |
| Tests | `cd backend && python -m pytest -q`; `python -m pytest ml/tests -q`; `cd frontend && npm test` | — |
| ML evaluation | `python ml/scripts/build_evaluation_report.py` | artifacts |
| Dataset cleaning | `python ml/preprocessing/clean_datasets.py` | — |

Never start the backend with `python run_server.py`. Detailed setup: [README.md](../README.md) and
[PRESENTATION_DEMO_GUIDE.md](PRESENTATION_DEMO_GUIDE.md).

## 10. Limitations to state in the presentation

1. **Anomaly model has no ground truth** — trained unsupervised on benchmark feature
   distributions (70,560 rows), no field telemetry, no contamination labels; the reported flag
   rate is descriptive only.
2. **Benchmark provenance missing** and the label is a deterministic rule; field accuracy unknown.
3. **XGBoost is offline only**, single station, ~5 weeks, balanced accuracy 0.54.
4. **Much of the authority dashboard is mock UI** (command centre KPIs, five-page remnants, the top board of Live Monitoring); station detail is keyed by mock ids. *(Alerts threshold card corrected in the validation pass, and the Alerts page itself is now served by the real `GET /api/authority/alerts`.)*
5. **Incident and laboratory backends now exist** (`/api/authority/incidents` + lab contacts +
   PDF report, tests in `tests/test_incidents.py`), but the Incidents/Laboratory **pages** still
   render labelled demonstration records and Inspections still has no backend. (Alerting:
   `GET /api/product/alerts` + a versioned threshold profile, plus the authority-wide
   `GET /api/authority/alerts`; notifications now have a delivery service with dedup/cooldown.)
6. **Product-user reading submission is implemented** — `POST /api/product/tests` accepts a stable
   live window (or a clearly labelled demo) and `POST /api/product/activate` binds codes with
   ownership checks; the Activate, check-water and history screens call them.
7. **Hardware unverified**; pH/TDS uncalibrated by default; turbidity is a relative index, not NTU.
8. **Security**: role self-selection and permissive CORS, the default JWT secret and missing rate
   limiting are **fixed in this pass** (see §11 status note); still open: tokens in `localStorage`,
   seeded demo credentials, auth-endpoint-only rate limiting, and an unverified production
   configuration.
9. **No coverage report, no E2E browser tests, no load tests** — quote test counts, never a coverage %.
10. **Cleaning removed zero rows** — the datasets were already clean; the deliverable is the recipe
    and the audit, not a large cleanup count.

## 11. The five most important remaining tasks (ranked by urgency)

> **Status update (2026-10-25, security hardening pass).**
> - **Task 1 — resolved.** Public registration rejects any role other than `PRODUCT_USER` with a
>   403 (regression-tested in `tests/test_product_tests.py` and
>   `tests/test_security_hardening.py`). CORS is now an explicit env-driven allowlist
>   (`backend/app/core/cors.py`): no wildcard with credentials, fail-closed in production.
>   `JWT_SECRET_KEY` has no default in code — startup fails when it is missing, and production
>   additionally fails on short or known-insecure values; no secret is ever auto-generated.
>   Rate limiting was added on login and registration (429 + `Retry-After`, counters shared in
>   PostgreSQL via migration `e7f8a9b0c1d2`). Production configuration itself is not yet verified.
> - **Task 2 — open.** Dataset provenance (`SOURCES.md`, fetch script) not added.
> - **Task 3 — open.** The Isolation Forest still ships on the tiny telemetry split; wording is
>   guarded ("unusual sensor pattern", no detection claims) but no retraining happened.
> - **Task 4 — partially resolved.** Analytics now uses the real
>   `/authority/stations/{code}/forecast` gated forecast card and an honest evaluation explainer
>   (the fabricated SHAP grid was removed), and per-reading ML availability messages are explicit.
>   Command Center, Live Monitoring's upper board, Water Sources and Station Detail still mix
>   mock data; the incidents/inspections/lab pages remain labelled prototypes.
> - **Task 5 — resolved** by a different shape: instead of a separate `/product/readings`, the
>   readings travel with `POST /api/product/tests` (stable-window validation, ownership checks,
>   full assessment persisted), and `POST /api/product/activate` is implemented and tested.
>
> Also resolved since the audit: persistent multi-worker simulation state, the versioned alert
> threshold profile, validated baseline forecasting with holdout gating, and the turbidity-index
> ML exclusion message (workflow documented in `docs/TURBIDITY_INDEX_ML.md`).
>
> **Validation pass (2026-10-26, `feature/software-hardening-and-validation`).** Verified the
> four-parameter pipeline, simulation state, turbidity-unit handling, screening/alert honesty and
> three-river scope against code and tests (backend 342, ML 140, frontend 70 all passing; build and
> lint clean; migrations at head). Two honesty defects were fixed in the UI: the Alerts threshold
> card no longer claims dissolved-oxygen, NTU or “AI risk” triggers (now the four-sensor
> project-configured tiers pointing at the versioned profile endpoint, with the SMS/webhook claim
> removed), and the public My Checks page no longer fabricates lake/reservoir history quoted in NTU
> (now labelled three-river demonstration entries using the relative index).
>
> **Central suitability engine (2026-10-26).** Every water-use suitability decision is now
> traceable to exactly four sensor values plus the intended use and its configured threshold
> profile: `app/services/suitability_engine.py` rejects any other input (dissolved oxygen, ML
> predictions, rainfall, location, history) with `ValueError`, both screening engines share one
> canonical four-state vocabulary (`within_configured_ranges` / `caution` /
> `outside_configured_ranges` / `insufficient_data`), and the state is persisted (`overall_state`,
> migration `a9b0c1d2e3f4`) and served alongside the legacy status. Invalid, stale, unstable or
> non-finite readings always collapse to `insufficient_data`. 49 new tests
> (`tests/test_suitability_engine.py`); backend total 391, frontend 70, build and lint clean.
>
> **Final remediation (2026-10-28, `feature/final-remediation`).**
> - **Turbidity honesty in the product engine:** any purpose whose profile rates turbidity
>   (drinking, domestic, swimming, general) now caps its best result at `REVIEW_RECOMMENDED`
>   (canonical `caution`) when turbidity is an uncalibrated relative index or missing, with an
>   explicit warning — “pH and TDS passing their screening rules is reported as a caution, not as
>   a full pass”. Regression tests added in `test_product_tests.py`, `test_product_screening.py`
>   and `test_simulation_and_alerts.py`.
> - **Authority alerts are real:** new `GET /api/authority/alerts` (authority-role only) derives
>   danger-level alerts from each station’s latest stored reading through the shared alerting
>   service; `Alerts.tsx` was rewired off `mockAlerts` with loading / empty / error /
>   session-expired states. Temperature remains contextual; index values are never compared with
>   NTU limits; simulated rows keep their labels.
> - **Prototype labelling:** Incidents, Inspections and Laboratory now show a `PrototypeBanner`
>   naming the missing endpoints and stating that lab records are demonstration data, not
>   four-sensor measurements.
> - **Production-config tooling:** `scripts/verify_production_config.py` +
>   `tests/test_production_config.py` (local static checks only) and a README deployment
>   verification checklist; deployment security remains **UNVERIFIED**.
> - **Schema drift documented, not dropped:** `alembic check` failure analysed — legacy
>   `water_tests` / `water_test_assessments` / `water_test_predictions` tables and retired
>   `product_devices.device_name` / `expires_at` columns are unreferenced by application code
>   (grep-verified) and intentionally kept; migration history untouched, head = `b8c9d0e1f2a3`.
>
> **Implementation sprint (`feature/final-remediation`, 2026-10-29/30).** Ten deliverables,
> each committed separately:
> - **Firmware calibration gating** — pH two/three-point linear and quadratic fits, TDS
>   quadratic fit with temperature compensation, `PH_CALIBRATED` / `TDS_CALIBRATED` /
>   `TURBIDITY_CALIBRATED` actually gate published values (uncalibrated publishes `null`),
>   firmware README corrected (stale 1.1378 V comment, nonexistent `TDS_CAL_V*` constants).
> - **Device registry + device-number login** — `POST /api/auth/device-login`,
>   `tests/test_device_registry.py`.
> - **Notification service** — `notifications` table (migration `a7b8c9d0e1f2`), dedup,
>   cooldown, per-user preferences, delivery log with honest `skipped_unconfigured` state,
>   `tests/test_notifications.py`.
> - **Incident + laboratory workflow + PDF** — `incidents.py` + `incident_service.py` +
>   migration `b8c9d0e1f2a3`, forward-only transitions with audit trail, verbatim lab results,
>   PDF report, `tests/test_incidents.py`. The Incidents/Laboratory **pages** are still labelled
>   demos; Inspections still has no backend.
> - **Station QR generation** — backend png/svg/pdf endpoints + authority QR page,
>   `tests/test_qr.py`.
> - **Dataset inspection + anomaly retrain** — `ml/scripts/inspect_datasets.py` and
>   `ml/reports/dataset_inspection.md`; Isolation Forest retrained on cleaned real
>   distributions, artifacts versioned in `ml/models/model_manifest.json`; 140 ML tests green.
> - **Mock-screen honesty** — `WaterCheck.tsx` now renders the real public suitability API
>   (no client-side verdicts); demo notices on Command Center, Water Sources, Analytics,
>   Station Detail, Nearby, Warnings; fabricated sidebar probe count removed; `MyChecks`
>   “Safe” badge replaced; `PrototypeBanner` no longer claims “no backend” for incidents.
> - **Security hardening** — MQTT credentials required in production, TLS required for
>   non-loopback brokers, ingestion bounds (TDS ≤ 50 000 ppm, turbidity ≤ 4 000 NTU, index ≤
>   100), device activation rate-limited, HTTPS `PUBLIC_BASE_URL` and tracked-secret scan in
>   `verify_production_config.py`, canonical checklist in `docs/DEPLOYMENT_VERIFICATION.md`
>   (all 14 real-environment steps still **not run**).
>
> Test evidence for the sprint: backend **668 passed** (exit 0, 378 s), ML **140 passed**,
> frontend **74 passed**, `npm run build` exit 0, `npm run lint` 0 errors (1 pre-existing
> warning). Deployment security remains **UNVERIFIED**.

### 1. Close the privilege-escalation hole (minutes, highest urgency) — **DONE**
`POST /api/auth/register` previously honoured a caller-supplied `role`. It now forces
`PRODUCT_USER` (any other role gets 403) and authority users are created only through the seed
script or a deliberate admin path, with regression tests. CORS is restricted to an explicit
allowlist and a non-default `JWT_SECRET_KEY` is required, with startup failing securely when it
is missing or (in production) insecure.
**Why first:** it was a security defect in an otherwise defensible project, and it was the
cheapest fix in this list.

### 2. Record dataset provenance and make data acquisition reproducible (hours) — **PARTIAL**
`ml/reports/dataset_inspection.{md,json}` (from `ml/scripts/inspect_datasets.py`) now records
columns, units, row counts, duplicates, missing values and label balance for every external
dataset, and `ml/reports/dataset_cleaning_report.md` records SHA-256 + row reconciliation.
Still missing: `ml/data/external/SOURCES.md` with publisher/URL/license/access date per file and
a fetch script that reproduces the USGS queries; the misleading `*_2024.csv` names remain.
**Why second:** every examiner question about the 99.99 % accuracy ends at "where did the data come
from".

### 3. Either retrain the anomaly model on real data or demote it explicitly (days) — **DONE**
The Isolation Forest was retrained on the cleaned real distributions (the 9-row model is gone),
artifacts are versioned in `ml/models/model_manifest.json`, and metrics are recomputed into
`ml/reports/evaluation_report.md`. Honest limit that remains: the data is still benchmark data,
not telemetry from this hardware, so the model flags unusual patterns — it does not detect
contamination.
**Why third:** it is the largest gap between the slides people want to show and what the code can
defend.

### 4. Make the authority dashboard consistent with the backend (days) — **PARTIAL**
Alerts, QR codes, suitability, forecasts and station telemetry are served by real endpoints.
Still open: Command Center, Live Monitoring's upper board, Water Sources, Analytics and parts of
Station Detail mix in mock data; the Incidents and Laboratory pages are not yet wired to their
(now existing) endpoints; Inspections has no backend; Station Detail is keyed by mock ids on the
map paths. Every one of these surfaces now carries a visible demo/prototype notice.
**Why fourth:** it prevents a live demo from showing fabricated numbers next to real ones, which is
the fastest way to lose credibility.

### 5. Add the product-user reading path or remove it from scope (days) — **DONE**
`POST /api/product/tests` accepts a stable live window (or a labelled demo) with ownership checks
and persists the full assessment; `POST /api/product/activate` binds codes with row locking;
`POST /api/auth/device-login` signs in the bound account from the printed device number. All
rate-limited and covered by `tests/test_product_tests.py` and `tests/test_device_registry.py`.

Lower-priority follow-ups: wire the cleaned copies into the training scripts, add coverage reporting,
add browser E2E tests, add rate limiting, and containerise PostgreSQL + Mosquitto for reproducible
setup.

---

## 12. What this audit changed in the repository

| File | Change |
|---|---|
| `ml/preprocessing/clean_datasets.py` | **New.** Auditable cleaning for all three dataset shapes: read-only sources, SHA-256 verification, count reconciliation, subset proof, JSON + Markdown report |
| `ml/data/processed/cleaned/*.csv` | **New.** Six cleaned copies (sources untouched) |
| `ml/reports/dataset_cleaning_report.{json,md}` | **New.** Generated audit of the cleaning run |
| `docs/*.md` | **New.** This documentation set (7 files) |
| `ml/README.md` | Documented the new cleaning script |
| `README.md` | Added a documentation index |

No application code, schema, model artifact, split or prediction file was modified. Backend, ML and
frontend test suites, lint and build were re-run after the changes and are green.

---

## 13. Bottom line

The backend, database, standards engine and ML serving path are real, tested and unusually careful
about not inventing data. The weak points are equally clear: a benchmark dataset with no recorded
provenance, operations screens (command centre, incidents, inspections, lab) that still show labelled
demonstration data, an anomaly model trained on benchmark rather than field telemetry, and a
production deployment that has never been exercised. The registration privilege-escalation hole,
the default JWT secret, the missing rate limits and the anonymous-MQTT path are fixed and tested.
Fixing the remaining mock screens is the single biggest step from “careful prototype” to “finished
system”; the deployment checklist in `docs/DEPLOYMENT_VERIFICATION.md` is what would let anyone
say the deployment itself is verified.
