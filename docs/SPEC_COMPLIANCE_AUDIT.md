# HydraSense — Spec Compliance Audit (audit-first deliverable)

Audit date: 2026-10-30, branch `feature/final-remediation`, commit `2cd291c` (working tree clean).
Method: source read ("audit first"), prior test evidence in `docs/FEATURE_STATUS.md` /
`docs/PROJECT_AUDIT_REPORT.md`, and targeted greps listed inline. Nothing was changed to make a
claim true. Hardware, broker, email and lab items are marked **Unable to verify** where no real
infrastructure exists in this checkout.

Statuses: **Implemented** (code + automated test evidence), **Partial** (some paths real,
others mock/missing), **Missing** (no code path), **Unable to verify** (needs hardware/infra).

---

## 1. Product honesty (four parameters only)

| Spec item | Status | Evidence |
|---|---|---|
| Only pH / TDS / turbidity / temperature measured | **Implemented** | `SensorReading` has exactly `ph, tds, turbidity, turbidity_unit, temperature` (`backend/app/models/water.py`); telemetry validation rejects unknown keys (`mqtt_service.validate_telemetry_payload`) |
| No DO/BOD/metals/bacteria claims in code/UI/docs | **Partial** | Alerts page and My Checks were cleaned in the validation pass (`docs/FEATURE_STATUS.md` §6 "validation pass"), but `frontend/src/pages/public/WaterCheck.tsx` still states a "certification" notice (named below) and the incidents/lab pages render demo content |
| Turbidity is a relative index, never NTU-labelled | **Implemented** | per-row `turbidity_unit`, `parse_turbidity_meta`, index never compared to NTU limits (`tests/test_simulation_and_alerts.py`, `tests/test_suitability_engine.py`) |

## 2. User types

| Spec item | Status | Evidence |
|---|---|---|
| Authority: map + dashboard, live values, trends, station health, freshness | **Partial** | Live Monitoring / Analytics / Alerts / stations are real (`authorityApi.*` → `backend/app/api/v1/authority.py`); command-center KPI cards and WaterMap canvas are mock/placeholder (`frontend/src/data/mockData.ts`, `WaterMap.tsx` "Interactive GIS Placeholder") |
| Authority: notifications for anomalies / suspected discharge / offline | **Missing** | `grep -rli "notification\|smtplib" backend/app` → no notification service; alerting only generates rows via `app/services/alerting.py`. Anomaly events exist in ML output only |
| Authority: forecasts with uncertainty bands labelled "prediction" | **Partial** | `app/services/forecasting.py` serves a holdout-gated baseline; **no uncertainty interval exists** (holdout MAE is not a forecast band); no framed "prediction" band UI |
| Authority: QR per station deep-linking public page | **Partial** | Frontend-only `PublicPageQrCard` builds the URL (`frontend/src/components/...` test asserts the URL); no backend QR/PNG/SVG/PDF generation (`grep -rln qrcode backend` → empty) |
| Authority: incident → lab workflow, statuses, lab results beside sensor data | **Missing** | No incident/lab models or routes; pages are labelled prototypes (`PrototypeBanner.tsx`), data from `mockIncidents`/`mockLabRecords` |
| Public (QR scan): live values, freshness, trend | **Implemented** | `/public/source/:code` real API (frontend tests + backend `app/api/v1/public.py`) |
| Public: suitability for drinking/domestic/swimming/agriculture with suitable/caution/not-suitable/insufficient-data | **Partial** | Central engine with `within_configured_ranges/caution/outside_configured_ranges/insufficient_data` (`app/services/suitability_engine.py`, `app/services/screening_states.py`) covers **six** project purposes; the spec's four-state wording differs (see mapping below), and irrigation is correctly refused as certifiable, not "suitable" |
| Public: "may be suitable, but needs further testing" + missing list | **Partial** | Turbidity-unvalidated downgrade caps results at `caution` with reasons (final-remediation pass); the explicit "needs further testing (microbiology, chemical)" phrase exists only inconsistently in UI copy |
| Every verdict plain-language AI explanation grounded in actual values | **Missing** | No LLM integration anywhere (`grep openai|LLM` across backend/frontend → no hits). Explanations are rule-authored strings (`water_screening.assess`, `water_suitability.py`) — grounded, but not the spec's AI-explanation layer |
| Personal user: device-number login (first device HSD-0001-K7M2Q9 → ESP32-HS-001/ARK-001) | **Missing** | Device registry exists as `product_devices` but uses `product_code` format `HS-KIT-000124` (`backend/scripts/seed_demo.py:36`); no device-number-based login, no `HSD-` code seeded, one-device-per-account not enforced (registry has single `owner_id` FK per device but nothing blocks an account from binding many devices — actually acceptable; the unimplemented part is login-by-device-number) |
| Personal: email/push notifications, debounced/cooldown, never on null/stale | **Partial** | `app/services/alerting.py` never fires on null/stale (tests) and has a versioned threshold profile; **no delivery channel** (no email/push), no dedup/cooldown, no delivery log |

## 3. Decision architecture

| Spec item | Status | Evidence |
|---|---|---|
| Rule-based suitability, one backend engine, frontend only renders | **Implemented** | `app/services/suitability_engine.py` façade rejects extra inputs with `ValueError`; frontend `WaterSuitabilitySection` renders API result (frontend tests) |
| ML never overrides rule verdict | **Implemented** | ML results attach to readings (`attach_ml_results`), never to assessments (`tests/test_ml_service.py`) |
| ML for anomaly/forecast/advisory only | **Partial** | Anomaly (IF) + RF advisory labels exist; forecasting exists (baseline, gated). XGBoost offline (`ml_status_service.py` lists it not-served) |
| Skip ML when null or uncalibrated index | **Implemented** | per-reading `ml_availability.py` + tests |
| LLM explains, never decides | **Missing** | No LLM integration (see §2) |

## 4. Hard rules

| Spec item | Status | Evidence |
|---|---|---|
| Null stays null | **Implemented** | nullable columns; rejected payloads never zero-filled (`tests/test_telemetry.py`) |
| pH/TDS show "Uncalibrated" until recorded | **Partial** | Backend labels simulated/provisional; firmware publishes provisional demo values and hard-wires `calibrated=false` (`.ino:185,244,294`); the cal flags are **dead code** (`CONFIG.example.h` promises gating the sketch does not do) — Deliverable 2 |
| "Preliminary screening, not laboratory certification" on every result screen | **Partial** | Product check-water and public source pages carry screening notices; `WaterCheck.tsx` still says "Certification" and claims things against "public guidelines" (named in §8 below) |
| Mock data removed or clearly labelled | **Partial** | 11 pages still import `mockData`/`mockIncidents`/`mockAlerts`: Alerts (residual), Analytics, CommandCenter, Incidents, Inspections, Laboratory, StationDetail, WaterSources, NearbySources, Warnings, WaterCheck (grep 2026-10-30) |
| RBAC AUTHORITY vs PRODUCT_USER, public read-only | **Implemented** | `app/api/deps.py`, `tests/test_rbac.py` |
| Rate-limit login/register/activation | **Partial** | login + register throttled (DB-backed, `rate_limit_counters`, migration `e7f8a9b0c1d2`); **activation not throttled**, and `POST /product/tests` not throttled |
| MQTT broker username/password + ACLs, TLS outside host | **Missing / Unable to verify** | no `mosquitto*.conf` in repo; docs instruct `allow_anonymous true` for LAN (`docs/PROJECT_AUDIT_REPORT.md:138`); `config.example.h` encodes anonymous defaults (`MQTT_USER ""`) |
| JWT ≥ 32 chars, no default | **Implemented** | no default in code, startup fail-fast, `tests/test_security_hardening.py` |
| Secrets only in .env / config.h | **Implemented** | `config.h` gitignored; `backend/.env.example` placeholders only |
| Ingestion upper bounds TDS/turbidity | **Implemented** | `validate_telemetry_payload` range checks (tests for every rejection branch) |

## 5. Firmware calibration

| Spec item | Status | Evidence |
|---|---|---|
| pH 2–3 point regression from buffer voltages | **Missing** | sketch uses constants `PH_VOLTAGE_AT_PH7=1.0278` / `59.16 mV/pH` (`.ino` conversion block); user's measured buffers (7.00 ≈ 1.238–1.254 V, 4.01 ≈ 1.472–1.496 V) contradict both constants → Deliverable 2 |
| Divider factor on pH line folded in | **Unable to verify** | wiring table documents direct A0; user measures at "ADS1115 divider junction"; firmware `readPh` takes ADS volts directly (`.ino:~360–400`) |
| TDS ≥4-point fit, temperature-compensated, NaCl-equivalent stated | **Missing** | demo 2-point line `ppm = 1050.58·V − 330.76` (`.ino:283–318`), no temp compensation, labelled DEMO; no `TDS_CAL_*` constants exist anywhere (README row named "fix docs matching" in `firmware/README.md`) |
| Turbidity index/NTU lookup, interpolation, labelled screening-only | **Partial** | relative index published honestly (`AnalogResult`, `.ino`), no NTU conversion — matches "keep index until calibration"; interpolation table is proposed, not built |
| Flags gate published values + `calibration_status` in diagnostics | **Missing** | flags never referenced by the sketch (grep); `calibrated` hard-wired false; README §10 semantics do not match code — Deliverable 2 |
| Versioned recalibration events in docs | **Partial** | project-configured screening constants recorded in `docs/FEATURE_STATUS.md`; per-sensor calibration versioning not started |

## 6. Dataset and ML

| Spec item | Status | Evidence |
|---|---|---|
| External dataset inspected (columns/units/rows/labels/provenance) | **Partial** | `ml/data/external/water_quality_dataset1.csv`: 100,799 rows + header, columns `pH, TDS_ppm, Turbidity_NTU, Temperature_C, Label` — units match the four sensors except turbidity is **NTU**, not the relative index. Label appears rule-derived. **Provenance/license missing** (`docs/PROJECT_AUDIT_REPORT.md` §5 marks it UNVERIFIED; no `SOURCES.md`) |
| Dataset not used for suitability rules | **Implemented** | suitability uses configured profiles only (`water_suitability.py`, `suitability_engine.py`) |
| Bootstrap/benchmark anomaly + quality models, then retrain on real readings | **Partial** | RF trained on the dataset (plan is rule recovery); IF still trained on 9 simulator rows (`sensor_readings.csv`) — the "9-row anomaly model" is NOT yet replaced |
| Never train/test same rows; time/station-aware splits; metrics reported | **Partial** | stratified + chronological splits with global boundaries (`ml/tests/test_data_leakage.py`); **station-aware** split does not apply (single benchmark station) — metrics published honestly incl. the 99.99 % rule-recovery caveat |
| Pin sklearn to match saved models / fix 1.4.2 vs 1.7.2 skew | **Partial** | `ml/requirements.txt` pins `scikit-learn==1.4.2` and env reports 1.4.2; the IF artifact was pickled under **1.7.2** and loads with a logged warning (`backend/app/services/ml_service.py:171–175`); retrain-on-pinned or repickle is open — Deliverable 7 |
| Forecast method documented + uncertainty intervals | **Partial** | Ridge-vs-persistence baseline, holdout gate (`app/services/forecasting.py`, docs); **no probabilistic interval** — documented as limitation, not yet implemented (deliverable 7 scope for a real interval) |
| Versioned model artifacts + metrics beside artifact | **Partial** | `ml/models/*.joblib` + `ml/reports/*`; no version metadata file naming commit/data-hash |
| SHAP/feature importance where useful | **Partial** | SHAP artifacts exist offline; not exposed by any API |

## 7. Backend additions

| Spec item | Status | Evidence |
|---|---|---|
| Device registry (device number → device_id/station/owner/activation; seed first device) | **Partial** | `product_devices` maps `product_code → device_id`, owner, activation (`models/device.py`); no `device_number` column/`HSD-` seed; device↔station binding not encoded |
| Device-number activation + login | **Missing** | `POST /product/activate` exists (code-based); no login-by-device-number flow |
| Notification service email/push + dedup/severity/cooldown/prefs/delivery log | **Missing** | no module, no model, no migration |
| Incident + lab workflow (incident table, lab contacts, PDF report, status timeline, lab result ingestion, audit trail) | **Missing** | only labelled prototype pages |
| QR service (per-station, stable URL, PNG/SVG/PDF) | **Missing** | frontend-only preview card |
| Keep telemetry validation, per-row turbidity units, provenance, DB rate limiting, Alembic | **Implemented** | see FEATURE_STATUS §2; migrations at head `a9b0c1d2e3f4` |

## 8. Frontend additions

| Spec item | Status | Evidence |
|---|---|---|
| Authority map | **Missing (visual)** | placeholder canvas |
| Authority live board/station detail keyed by `station_code` | **Partial** | LiveMonitoring keys real stations; `StationDetail.tsx` still keyed by mock ids (`source-tg-halli`) → 404s on real cards |
| Authority alerts, incidents, lab contact, forecast cards, QR generator | **Partial** | Alerts real; incidents/lab mock; forecast card real (gated); QR preview real (frontend-only) |
| Public QR landing with four suitability cards + explanations + freshness + "needs further testing" | **Partial** | real public page exists with six-use cards; "needs further testing" wording not standardized |
| Personal device login / tank dashboard / history / alerts | **Partial** | email login, check-water, history real; device-number login and alert delivery missing |

## 9. Honesty defects still open (from previous audits, file-level)

1. `frontend/src/pages/public/WaterCheck.tsx` — certification wording, "calibrated against public guidelines", any DO claim (per spec deliverable 8).
2. `frontend/src/pages/authority/StationDetail.tsx` — mock-id keying (functional break).
3. CommandCenter / Analytics / WaterSources / NearbySources / Warnings mock remnants.
4. Personal `MyChecks` (`frontend/src/pages/user`) — the "Safe" badge named in the spec (check current copy at implementation time).
5. Firmware docs vs sketch mismatches (`firmware/README.md` §10, nonexistent `TDS_CAL_V0/V250`, stale 1.1378 vs 1.0278 comment).
6. IF artifact pickled under sklearn 1.7.2 served under 1.4.2 with a warning.

## 10. Next steps per the spec's deliverable order

1. **Firmware calibration + flag gating + README fix** (self-contained; pure firmware/docs).
2. **Device-number registry + login** — extend `product_devices` + `/auth/login` variant; seed `HSD-0001-K7M2Q9`.
3. **Notification service** (email first, delivery log, cooldown; wire product + authority alerts).
4. **Incident + lab workflow + PDF** (models, endpoints, auth, timeline, tests).
5. **QR backend service + public landing polish.**
6. **Dataset provenance + ML retraining version-handling + forecasting uncertainty (needs labeled anomalies to go beyond hierarchy).**
7. **Mock-screen removal/label pass.**
8. **MQTT broker auth/ACL config + rate-limit coverage for activation/tests + ingestion bound re-check.**
9. **Test sprint + docs/test-count update.**

## 11. Unable to verify (list)

- ESP32 firmware behavior on hardware, real sensor voltages, buffer calibration values.
- Mosquitto broker delivery, ACL/TLS behavior (no broker config in repo).
- Dataset provenance/licence for `water_quality_dataset1.csv` (no record in repo).
- Production deployment configuration (static checks only: `scripts/verify_production_config.py`).
- Email delivery, phone QR scan, lab ingestion, GIS backend.
