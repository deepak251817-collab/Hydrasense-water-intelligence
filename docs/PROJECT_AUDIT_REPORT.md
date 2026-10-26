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
| QR URL generation | frontend test asserts the encoded URL |
| Interactive API docs | `/docs`, `/openapi.json` |
| 353 automated tests | 152 backend, 140 ML, 61 frontend — all passing |

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
| Alerts / Incidents / Inspections / Laboratory / Sources | 🧪 |
| Station detail | 🧪 keyed by mock ids (real ML card 404s) |
| Public check-water / nearby sources / warnings / my checks | 🧪 |
| User check-water / history / activate | 🧪 |

Full matrix: [FEATURE_STATUS.md](FEATURE_STATUS.md).

## 5. Datasets actually used

| Dataset | Rows | Role | Provenance |
|---|---|---|---|
| `water_quality_dataset1.csv` | 100,800 | Random Forest training/eval | **UNVERIFIED** — no source recorded |
| `usgs_ph_2024.csv` | 10,000 | forecasting feature | USGS station `USGS-01649190`, Jan–Feb 2024, 5-min |
| `usgs_turbidity_2024.csv` | 10,000 | forecasting feature + target | same; **all Provisional** |
| `usgs_temperature_2024.csv` | 10,000 | forecasting feature | same |
| `usgs_conductance_2024.csv` | 10,000 | forecasting feature | same |
| `sensor_readings.csv` | 9 | Isolation Forest training/eval | own simulator, 2026-08-31 |

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
| Isolation Forest | yes | `anomaly_label`, `anomaly_score` | Unusual relative to **6 training rows** — demonstration, not validation |
| Random Forest | yes | `Safe`/`Unsafe` + probabilities | The benchmark's deterministic label rule over 4 features; not potability |
| XGBoost | no | `deterioration_target` | Rule-based one-step deterioration indicator on USGS features |

Regenerated metrics (identical to the committed report):

- Random Forest: n=15,120, accuracy **0.999868**, macro F1 **0.999843**, ROC-AUC **1.0000**,
  confusion matrix `[[4535, 1], [1, 10583]]`.
- Isolation Forest: n=9, **4 flagged** (44.4 %), scores −0.022505 … 0.103192.
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

1. **Anomaly model is a demonstration** — 6 training rows, 9 scored readings; no validated detection
   rate, no ground-truth labels.
2. **Benchmark provenance missing** and the label is a deterministic rule; field accuracy unknown.
3. **XGBoost is offline only**, single station, ~5 weeks, balanced accuracy 0.54.
4. **Much of the authority dashboard is mock UI** (five pages, plus the top board of Live Monitoring); station detail is keyed by mock ids.
5. **Incident, inspection, lab and notification backends are missing**; those pages are
   prototypes. (Alerting **was added**: `GET /api/product/alerts` + a versioned threshold profile
   that separates official BIS values from project-configured ones.)
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

### 1. Close the privilege-escalation hole (minutes, highest urgency) — **DONE**
`POST /api/auth/register` previously honoured a caller-supplied `role`. It now forces
`PRODUCT_USER` (any other role gets 403) and authority users are created only through the seed
script or a deliberate admin path, with regression tests. CORS is restricted to an explicit
allowlist and a non-default `JWT_SECRET_KEY` is required, with startup failing securely when it
is missing or (in production) insecure.
**Why first:** it was a security defect in an otherwise defensible project, and it was the
cheapest fix in this list.

### 2. Record dataset provenance and make data acquisition reproducible (hours)
Add `ml/data/external/SOURCES.md` (URL, publisher, access date, license, row count, checksum) for
`water_quality_dataset1.csv`, and a documented `ml/scripts/fetch_usgs.py` that reproduces the four
USGS queries (station, parameter codes, date range, 10,000-row cap). Fix the misleading `*_2024.csv`
names or document the cap.
**Why second:** every examiner question about the 99.99 % accuracy ends at "where did the data come
from", and today the repository has no answer.

### 3. Either retrain the anomaly model on real data or demote it explicitly (days)
Collect genuine telemetry (hardware or a longer simulator run with realistic diurnal/noise patterns),
re-export, re-split chronologically, retrain the Isolation Forest, and re-run
`detect_anomalies.py` + the evaluation report. If real data is not available before submission,
relabel the model everywhere as a pipeline demonstration and remove any wording that implies
detection capability.
**Why third:** it is the largest gap between the slides people want to show and what the code can
defend.

### 4. Make the authority dashboard consistent with the backend (days)
Replace `mockData` on Command Center, Live Monitoring's upper board, Water Sources, Analytics and
Station Detail with the existing `/authority/stations`, `/readings` and `/ml/status` endpoints; key
Station Detail by `station_code` so `MlLatestCard` resolves. For Alerts / Incidents / Inspections /
Laboratory, either build minimal real endpoints or label the pages "prototype" in the UI.
**Why fourth:** it prevents a live demo from showing fabricated numbers next to real ones, which is
the fastest way to lose credibility.

### 5. Add the product-user reading path or remove it from scope (days)
Implement `POST /product/readings` (upload a personal device measurement) and
`POST /product/activate` so the Activate page and the personal check flow call real endpoints, with
ownership checks. Otherwise remove those routes from the navigation and present the product-user area
as account + device management only.
**Why fifth:** it is the only user-facing workflow that currently promises something the backend
cannot do, and it is a coherent, self-contained feature to finish.

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
about not inventing data. The weak points are equally clear: a demonstration-only anomaly model, a
benchmark dataset with no recorded provenance, a security hole in registration, and a dashboard that
mixes live telemetry with mock operations screens. Fixing items 1 and 2 is a day's work and removes
the two questions most likely to derail a viva; items 3–5 determine whether the project reads as a
working prototype or a finished system.
