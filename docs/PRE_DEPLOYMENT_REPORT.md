# HydraSense — Pre-Deployment Audit Report

**Date:** 2026-10-31 · **Scope:** read-only audit against the 9-point spec. No code, config or
database was modified; this file is the only artifact created. Secret values are never printed —
variable names and their set/unset state only.

**Git status:** the working tree was **already dirty when the audit started** (uncommitted work from
the earlier simulation-panel sprint: 18 modified files + `SimulationDock.tsx`,
`simulation-panel.test.tsx` untracked). This audit changed **none** of them — after the audit the
diff is identical except for the new untracked `docs/PRE_DEPLOYMENT_REPORT.md`. Run
`git diff backend/.env.example` to see BLOCKER-1.

---

## 1. Summary table (read this first)

| # | Spec area | Verdict | Key evidence |
|---|---|---|---|
| 1 | Measures only pH, TDS, turbidity, temperature | **Implemented** | `backend/app/services/suitability_engine.py:16` rejects any other input; `tests/test_suitability_engine.py::test_engine_declares_exactly_the_four_sensor_inputs`; every "dissolved oxygen" hit is a *not measured* disclosure; `frontend/src/test/ml-integration.test.tsx:497` asserts no DO probe/DO trend tab |
| 2 | Three users (Authority / Public / Personal) | **Partial** | Authority: email login, live monitoring, alerts, forecasts, QR per source, lab contact + PDF reports all present with tests. Personal: `POST /api/auth/device-login` (`HSD-0001-K7M2Q9`) rate-limited, `tests/test_device_registry.py`, notifications API. **Gaps:** no AI/LLM explanation anywhere; public `NearbySources` + `Warnings` pages render **mock** suitability strings with no prototype label |
| 3 | Rules decide, ML assists, LLM explains, never "certified safe" | **Partial** | Rule engine + 206 recommendation tests; ML only anomaly/forecast; every "certification" string in backend code is a disclaimer. **Gap:** no LLM layer exists at all (only a documented constraint in `recommendations.py:24`); mock lab fixture says `"Certified"` (`mockData.ts:444`) |
| 4 | Null stays null, calibration visible, turbidity = index 0–100, TDS NaCl-eq, pH verified 4–7 | **Implemented** (pH range documentation Partial) | NULL tests in `test_telemetry.py`; `CalibrationBadge` + `data_quality.calibration_status`; index guards in 6 test files, alert bands 55/85; NaCl-equivalent in firmware + `SPEC_COMPLIANCE_AUDIT.md:69`; verified pH 4–7 exists **only** in gitignored `config.h:62` |
| 5 | Firmware: config.h ignored, NETWORK_MODE works, calibration gates output, no stale docs | **Partial / Wrong** | `config.h` untracked ✓; modes 0/1 (Wi-Fi, hotspot) work; **mode 2 Ethernet has no code in the sketch** (only `WiFi.h`, `WiFi.begin`) and `config.example.h` has no `NETWORK_MODE` at all; calibration flags gate output ✓ |
| 6 | Simulation: floating button, `source=simulator`, no real emails, no mixing | **Implemented** | `SimulationDock.tsx` + 5 Vitest tests; `test_simulation_and_alerts.py:525` asserts **0** `Notification` rows; simulated rows refused by the BIS view (`insufficient_data` / `not_comparable` asserted) |
| 7 | ML honesty (synthetic disclosed, model size, sklearn pin, baseline) | **Partial** | Synthetic disclosed in `ml/reports/evaluation_report.md` limitations; `scikit-learn==1.4.2` pinned == manifest == installed; forecast returns `baseline_mae`/`baseline_rmse`. **Gap:** anomaly model size (`size_bytes: 1456616`) appears only in `ml/models/model_manifest.json`, never surfaced in docs/API/UI |
| 8 | Security (RBAC, rate limits, JWT ≥32, MQTT auth, CORS, no demo creds, no secrets) | **Implemented** | 51 API routes → 43 protected, 8 intentionally public, **none** of authority/product routes missing the role guard; 33 hardening + 4 RBAC tests; `validate_security()` enforces ≥32 chars in production; production refuses anonymous MQTT; CORS allowlist fail-closed; no demo credentials in `backend/app`; `verify_production_config.py` "No secrets committed — 318 tracked files scanned" |
| 9 | Deployment readiness | **Partial** | Production config script **passes** (proper env, 1 REVIEW). Frontend builds ✓. **Env vars:** documented in `README.md:139–160` but **`backend/.env.example` was overwritten with wrong names**. **Migrations:** unverifiable without a database; offline SQL fails at `a9b0c1d2e3f4`. **MQTT subscriber:** starts per process, not guarded to one per deployment. **QR base URL:** configurable ✓ |

**Test / lint / build counts**

| Suite | Result |
|---|---|
| Backend `python -m pytest -q` | **681 passed**, 4 warnings (399 s) |
| ML `python -m pytest -q` | **140 passed** (60 s) |
| Frontend `npm test` (Vitest) | **79 passed**, 7 files |
| Frontend `npm run lint` | **0 errors**, 1 pre-existing warning (`components/ui/button.tsx`) |
| Frontend `npm run build` | **ok** — 2474 modules |
| `scripts/verify_production_config.py` (production-like env, loopback broker) | **no failures**, exit 0, 1 REVIEW (MQTT TLS) |
| `scripts/verify_production_config.py` (production-like env, remote broker, no TLS) | **1 FAIL** — `MQTT transport encrypted`, exit 1 (correct: TLS is mandatory off-host) |
| `scripts/verify_production_config.py` (as-is dev env) | 4 FAIL — expected, per `README.md:638` |

---

## 2. Spec detail

### 1. Four parameters only — Implemented
- `suitability_engine.evaluate` accepts exactly `ph, tds, turbidity, temperature`; extra keys raise
  (`tests/test_suitability_engine.py::test_unsupported_parameters_are_rejected_not_ignored`).
- "dissolved oxygen" appears in 18 places, **all** as exclusion statements
  (`water_screening.py:1016/1053` emit `not_measured`; `water_suitability.py:233/295` cite CPCB
  classes with "no DO sensor is installed"; README/table notes).
- Frontend has no DO sensor card or trend tab — enforced by
  `frontend/src/test/ml-integration.test.tsx` ("Four physical sensors — Dissolved Oxygen removed").

### 2. Three users — Partial
- **Authority**: email login (`/api/auth/login`), Live Monitoring (stable-window assessment),
  alerts (`/authority/alerts`), forecasts (`/authority/stations/{code}/forecast`), QR per source
  (`qr_service.py`, `tests/test_qr.py`), lab contacts + PDF incident reports
  (`incident_service.py`, `tests/test_incidents.py`).
- **Public**: QR scan → `/public/source/{code}` (API-backed, no login), live values,
  suitability for drinking / domestic / swimming / irrigation(agriculture) — `WaterCheck.tsx`
  maps `recreation → swimming`, `irrigation → irrigation`. Insufficient data shows
  "Insufficient data — check readings, calibration or timing" (`screening_states.py:43`).
  **Missing:** any AI/LLM explanation — grep for `llm|openai|gpt|anthropic|generative` returns
  only the constraint comment in `recommendations.py:24`.
  **Wrong:** `NearbySources.tsx` and `Warnings.tsx` render `mockWaterSources` (including
  `publicSuitability: "Safe"`) with **no** prototype banner, unlike `StationDetail.tsx` which does
  carry `PrototypeBanner`.
- **Personal**: `POST /api/auth/device-login` with `device_number` (`HSD-0001-K7M2Q9`), case-insensitive,
  generic 404, rate-limited — `tests/test_device_registry.py`. Notifications +
  preferences endpoints exist (`tests/test_notifications.py`).

### 3. Rules / ML / LLM — Partial
- Suitability is rule-driven; recommendations derive from triggered rules (206 tests in
  `tests/test_recommendations.py`, incl. `test_drinking_advice_never_claims_safety`).
- ML contributes only anomaly + benchmark classification + offline forecast; UI labels them as
  model output (`ModelHealthCard.tsx:198` disclaimer).
- "certified/certification": every backend hit is a negation
  (`_LIMITATION_NOT_CERTIFIED`, "not a laboratory safety certification", incident PDF footer).
  The only positive "Certified" is the mock lab fixture `mockData.ts:427–444`.
- **Missing:** the LLM explanation layer required by the spec (nothing to verify beyond the rule
  that it may only rephrase).

### 4. Data honesty — Implemented (pH documentation Partial)
- Nulls stay null: `test_failed_temperature_sensor_stored_as_null`,
  `test_missing_sensor_value_raises_warning_not_zero`, API returns `null`.
- Calibration visible: `CalibrationBadge`, `data_quality.calibration_status`,
  `TestResult.tsx:778`.
- Turbidity is a relative index: alert bands **55/85** index points
  (`alert_thresholds.py`, tests `test_index_alert_bands_are_55_and_85`,
  `test_index_thresholds_are_never_expressed_in_ntu`), unit-aware rendering in 8 components, and
  index rows are never compared with 1/5 NTU limits
  (`test_relative_index_is_never_compared_with_ntu`, `test_turbidity_index_is_never_compared_with_ntu_limits`).
- TDS labelled NaCl-equivalent mg/L (`hydrasense_esp32.ino:318/352`, `firmware/README.md:259`).
- pH verified 4–7: stated only in gitignored `config.h:62` ("values above 7 are extrapolated") —
  not in `firmware/README.md` or `config.example.h`.

### 5. Firmware — Partial / Wrong
- `firmware/hydrasense_esp32/config.h` is **not tracked** (`git ls-files` shows only
  `config.example.h` and the `.ino`); `.gitignore` covers it.
- `NETWORK_MODE` exists only in the local `config.h` (0 = home Wi-Fi, 1 = hotspot, 2 = Ethernet).
  The sketch uses only `WIFI_SSID/WIFI_PASSWORD/MQTT_HOST` + `WiFi.h` — **there is no Ethernet code**,
  so mode 2 falls back to an empty SSID and never connects. `config.example.h` has no
  `NETWORK_MODE` at all, and `firmware/README.md` never documents network modes.
- Calibration flags gate output: `PH_CALIBRATED` / `TDS_CALIBRATED` / `TURBIDITY_CALIBRATED` keep
  engineering values `NULL` and publish raw ADC/voltage instead (`config.example.h:52–92`, tests
  `test_uncalibrated_hardware_reading_stored_without_fabrication`).

### 6. Simulation — Implemented
- Floating control on every authority page (`components/authority/SimulationDock.tsx`,
  mounted in `AuthorityLayout.tsx`), 5 Vitest tests in `test/simulation-panel.test.tsx`.
- Every generated row keeps `source="simulator"` + `SIMULATED DATA` diagnostics label
  (`simulation_service.py`), asserted in `test_generates_only_the_four_supported_sensors`.
- No real notifications: `test_authority_alert_view_never_dispatches_notifications`
  (`test_simulation_and_alerts.py:525`) asserts `Notification.count() == 0`.
- Never mixed with ESP32 data: simulated values are refused by the BIS view
  (`result=insufficient_data`, every parameter `not_comparable`) and ML skips index rows.

### 7. ML honesty — Partial
- Synthetic benchmark disclosed: `evaluation_report.md` limitations ("benchmark dataset's labeling
  rule… not laboratory potability") and manifest `limitations[]`.
- Anomaly model size: recorded as `size_bytes: 1456616` in `model_manifest.json` only — not shown
  in `ml_status` API, docs or UI.
- sklearn: `ml/requirements.txt` pins `scikit-learn==1.4.2`; manifest `1.4.2`; installed
  `1.4.2` — all three match.
- Forecast vs persistence: `ForecastModelInfo.baseline_mae/baseline_rmse` returned and rendered;
  a model that does not beat the baseline is withheld
  (`test_no_trained_forecast_is_fabricated`).

### 8. Security — Implemented
- Route audit: 51 API routes, 43 protected, 8 intentionally public (register/login/device-login +
  5 public station reads); **no** authority/product route lacks the role guard.
- Rate limits: DB-backed fixed windows, 429 + `Retry-After` (5 dedicated tests).
- JWT: no code default; production rejects <32 chars and known placeholders (`validate_security`).
- MQTT: production refuses anonymous unless `MQTT_ALLOW_ANONYMOUS=true` (and the checker FAILs that
  flag); credentials never logged.
- CORS: explicit allowlist, fail-closed in production, `*` rejected with credentials (9 tests).
- Demo credentials: none in `backend/app` ("changeme" exists only in the insecure-secret list).
- Secrets: `.env` and `config.h` gitignored; only `.env.example` tracked; checker scanned 318
  tracked files with no findings.

### 9. Deployment readiness — Partial
- **Production config script:** passes with proper production env (1 REVIEW: MQTT TLS).
- **Migrations on an empty DB:** see BLOCKER-3.
- **Frontend build:** ok (2474 modules), lint clean.
- **Required env vars:** `README.md:139–160` documents them correctly; **`backend/.env.example` does not** (BLOCKER-1).
- **MQTT subscriber once:** started in `main.py` lifespan → once *per process*; no guard and no
  deployment note limiting uvicorn to one worker (unlike the simulation loop, which has a lease).
- **QR base URL:** `PUBLIC_BASE_URL` (backend) + `VITE_PUBLIC_BASE_URL` (frontend), both configurable.

---

## 3. Grep results (requested)

| Pattern | Result |
|---|---|
| `NTU`/`ntu` | 458 hits / 80 files — all classified in the previous turbidity audit: unit-aware rendering, official BIS references for `unit="ntu"` rows only, or "not NTU" disclaimers. Guard tests live in `test_simulation_and_alerts.py`, `test_product_screening.py`, `test_suitability_engine.py`, `test_telemetry.py`, `test_forecasting.py`, `frontend/src/test/turbidity.test.tsx` |
| `DO` / dissolved oxygen | 18 hits, **all** "not measured"/"no DO sensor" disclosures + one test asserting its absence |
| `certified` | backend: 16 hits, **all** disclaimers; frontend: only mock lab fixture `mockData.ts:428 "Certified"` |
| `Safe` badge | ML label with explicit disclaimer (`MlIndicator`, `ModelHealthCard`); **mock** `publicSuitability: "Safe"` rendered by `PublicSourceCard` on the mock Nearby/Warnings pages |
| Mock data | 20 files import `mockData`; API-backed: WaterCheck, PublicSource, LiveMonitoring, Alerts data, QrCodes, Incidents… Mock-only pages: `StationDetail` (banner), `NearbySources` (no banner), `Warnings` (no banner) |
| Hardcoded thresholds | `StationDetail.tsx:201–203` (pH 6.5–8.5, TDS <500 — mock card), `Alerts.tsx:175/185` (tier copy). Backend thresholds live only in `alert_thresholds.py` / `water_screening.py` profiles |

---

## 4. Verdict: **NO-GO**

### BLOCKERS (must fix)
1. **`backend/.env.example` was overwritten with wrong variable names.** It now lists `JWT_SECRET`,
   `SECRET_KEY`, `MQTT_BROKER`, `REDIS_URL`, `DEMO_STRICT_TDS_RULE` — none of which the app reads
   (settings are `JWT_SECRET_KEY`, `MQTT_BROKER_HOST/PORT`, no Redis) — and dropped the documented
   CORS/rate-limit/TLS entries. Anyone deploying from it gets an unconfigured JWT secret and an
   undocumented CORS allowlist. Restore the previous template (see `git diff backend/.env.example`).
2. **Two public pages show fabricated "Safe" verdicts with no labelling.**
   `frontend/src/pages/public/NearbySources.tsx` and `Warnings.tsx` render `mockWaterSources`
   (`publicSuitability: "Safe" | "Caution" | "Restricted"`) straight from the bundle, with no
   `PrototypeBanner` and no API call. This violates "rules decide suitability" and "never certified
   safe" on a page a scanner can reach. Remove them, wire them to the public API, or label them
   exactly as `StationDetail.tsx` does.
3. **Migrations are unverified on an empty database, and offline generation fails.**
   `DATABASE_URL=… python -m alembic upgrade head --sql` rendered 13 revisions / 11 `CREATE TABLE`
   then aborted at `a9b0c1d2e3f4` with
   `sqlalchemy.exc.CompileError: No literal value renderer is available for literal value
   "('WITHIN_PROJECT_TARGETS', …)" with datatype NULL` (the `NOT IN :statuses` tuple bound in
   `_backfill`). No test applies migrations. Run `alembic upgrade head` against a scratch
   PostgreSQL and, if it reproduces, bind with `sa.text(...).bindparams(statuses=…, expanding=True)`.

### SHOULD-FIX
- **Firmware Ethernet is a dead option**: `NETWORK_MODE 2` exists only in `config.h`; the sketch has
  no `Ethernet` include/initialisation, and `config.example.h`/`firmware/README.md` document no
  network modes. Either implement it or drop the option and document modes 0/1 in the example.
- **MQTT subscriber is per-process**, not once per deployment; add a single-worker guard/env switch
  (the simulation loop already has a lease) or document `uvicorn --workers 1`.
- **AI explanation is missing entirely** for the public suitability view (spec 2/3): no LLM layer
  exists, only a rule that it may only rephrase rule-based advice.
- **Anomaly model size is not surfaced** (`size_bytes` sits only in `model_manifest.json`) although
  spec 7 asks for it to be stated.
- **Verified pH range (4–7) is documented only in gitignored `config.h`** — add it to
  `firmware/README.md` calibration section so it survives config sharing.
- **The local `config.h` holds live home Wi-Fi/hotspot credentials** (gitignored, correct) — they
  are not in git; rotate them if you consider them exposed during development.
- Dev shell here reported `JWT_SECRET_KEY is 9 chars` — an environment artifact; production
  validation rejects it, but a strong value belongs in `backend/.env`.

### Unable to verify
- **Hardware:** real sensor calibration, pH 4–7 verification on the probe, turbidity clear/milky
  reference points, Ethernet mode (no hardware).
- **Live broker:** MQTT broker ACL/auth/TLS on a real deployment (local mosquitto also refuses the
  `hydrasense/+/telemetry` wildcard subscription, so live end-to-end ingestion could not be observed
  here; the callback path was exercised instead).
- **Phone:** QR scanning from a physical handset against a real `PUBLIC_BASE_URL`.
- **Lab:** laboratory result delivery (email/SMTP) and real lab contact workflows.
- **Migrations on a real empty database:** forbidden by this audit's no-database rule (see BLOCKER-3).
- **Real deployment environment:** DNS, reverse proxy, browser CORS round-trip, observed rate limits
  — the checker itself states deployment security stays UNVERIFIED until the README checklist is run.
