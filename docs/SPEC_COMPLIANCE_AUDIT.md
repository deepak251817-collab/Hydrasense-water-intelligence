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
| Authority: notifications for anomalies / suspected discharge / offline | **Partial** | Product-user notifications exist (`app/services/notification_service.py`, `notifications` table migration `a7b8c9d0e1f2`: severity, dedup, cooldown, preferences, delivery log; `tests/test_notifications.py`). Authority-side anomalies arrive as `GET /api/authority/alerts`; no email/push dispatch to authority accounts, no anomaly-detection event feed |
| Authority: forecasts with uncertainty bands labelled "prediction" | **Partial** | `app/services/forecasting.py` serves a holdout-gated baseline; **no uncertainty interval exists** (holdout MAE is not a forecast band); no framed "prediction" band UI |
| Authority: QR per station deep-linking public page | **Implemented** | Backend `GET /api/authority/stations/{code}/qr[.png|.svg|.pdf]` (`backend/app/api/v1/qr.py`) encodes `PUBLIC_BASE_URL`; authority `QrCodes.tsx` renders preview + downloads; `tests/test_qr.py` |
| Authority: incident → lab workflow, statuses, lab results beside sensor data | **Partial (backend Implemented, UI demo)** | Backend `backend/app/api/v1/incidents.py` + `incident_service.py` + migration `b8c9d0e1f2a3`: forward-only statuses with audit events, lab contacts, verbatim lab results beside stored readings, PDF report; `tests/test_incidents.py`. The Incidents/Laboratory **pages** still render labelled `mockData` and are not wired to it |
| Public (QR scan): live values, freshness, trend | **Implemented** | `/public/source/:code` real API (frontend tests + backend `app/api/v1/public.py`) |
| Public: suitability for drinking/domestic/swimming/agriculture with suitable/caution/not-suitable/insufficient-data | **Partial** | Central engine with `within_configured_ranges/caution/outside_configured_ranges/insufficient_data` (`app/services/suitability_engine.py`, `app/services/screening_states.py`) covers **six** project purposes; the spec's four-state wording differs (see mapping below), and irrigation is correctly refused as certifiable, not "suitable" |
| Public: "may be suitable, but needs further testing" + missing list | **Partial** | Turbidity-unvalidated downgrade caps results at `caution` with reasons (final-remediation pass); the explicit "needs further testing (microbiology, chemical)" phrase exists only inconsistently in UI copy |
| Every verdict plain-language AI explanation grounded in actual values | **Missing** | No LLM integration anywhere (`grep openai|LLM` across backend/frontend → no hits). Explanations are rule-authored strings (`water_screening.assess`, `water_suitability.py`) — grounded, but not the spec's AI-explanation layer |
| Personal user: device-number login (first device HSD-0001-K7M2Q9 → ESP32-HS-001/ARK-001) | **Implemented** | `POST /api/auth/device-login` resolves the printed number to its bound account with generic errors; `seed_demo.py` seeds `HSD-0001-K7M2Q9` → `ESP32-HS-001` / `ARK-001`; `tests/test_device_registry.py` |
| Personal: email/push notifications, debounced/cooldown, never on null/stale | **Partial** | `app/services/alerting.py` never fires on null/stale (tests) and has a versioned threshold profile; notification service added (`app/services/notification_service.py`, dedup + cooldown + preferences + delivery log, email only, SMTP-unconfigured reported honestly) with `tests/test_notifications.py`. No push/SMS channel |

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
| "Preliminary screening, not laboratory certification" on every result screen | **Implemented** | Product check-water, public source and the rewritten `WaterCheck.tsx` carry the screening notice; the "Certification" wording is gone from the public check page (the Laboratory *prototype* page still shows labelled demo "Certified" badges with an explicit banner) |
| Mock data removed or clearly labelled | **Partial** | Remaining `mockData` imports are all behind visible demo notices: Analytics, CommandCenter, Incidents, Inspections, Laboratory, StationDetail, WaterSources, NearbySources, Warnings (`DemoDataNotice` / `PrototypeBanner`); `WaterCheck.tsx` no longer renders mock verdicts at all (it calls the public suitability API) |
| RBAC AUTHORITY vs PRODUCT_USER, public read-only | **Implemented** | `app/api/deps.py`, `tests/test_rbac.py` |
| Rate-limit login/register/activation | **Implemented** | login, register, device-login and `POST /product/activate` throttled (DB-backed, `rate_limit_counters`, migration `e7f8a9b0c1d2`; `tests/test_device_registry.py`, `tests/test_security_hardening.py`). `POST /product/tests` and public routes still unthrottled |
| MQTT broker username/password + ACLs, TLS outside host | **Partial** | Backend now requires `MQTT_USERNAME`/`MQTT_PASSWORD` in production and wires TLS (`app/core/config.py`, `app/services/mqtt_service.py`, `tests/test_security_hardening.py`); README ships an `allow_anonymous false` + ACL reference. Still missing in-repo: a real `mosquitto.conf` and broker-side verification |
| JWT ≥ 32 chars, no default | **Implemented** | no default in code, startup fail-fast, `tests/test_security_hardening.py` |
| Secrets only in .env / config.h | **Implemented** | `config.h` gitignored; `backend/.env.example` placeholders only |
| Ingestion upper bounds TDS/turbidity | **Implemented** | `validate_telemetry_payload` range checks (tests for every rejection branch) |

## 5. Firmware calibration

| Spec item | Status | Evidence |
|---|---|---|
| pH 2–3 point regression from buffer voltages | **Implemented (unverified on hardware)** | `config.h` buffer voltages feed a boot-time least-squares fit (2–3 points) in `.ino`; the old `PH_VOLTAGE_AT_PH7` / `PH_VOLTS_PER_PH_UNIT` constants are gone; firmware README §10 corrected. Whether the recorded constants match measured hardware voltages is **unverified** — no buffer measurement was taken in this pass |
| Divider factor on pH line folded in | **Unable to verify** | wiring table documents direct A0; user measures at "ADS1115 divider junction"; firmware `readPh` takes ADS volts directly (`.ino:~360–400`) |
| TDS ≥4-point fit, temperature-compensated, NaCl-equivalent stated | **Implemented (unverified on hardware)** | `TDS_CAL_POINTS` (≥4 standards) fitted as a quadratic at boot, values compensated to 25 °C with `k = 1 + 0.02*(T-25)` from the DS18B20, output labelled NaCl-equivalent mg/L; uncalibrated publishes `null` with an error string (`hydrasense_esp32.ino`). Reference standards themselves are not yet recorded |
| Turbidity index/NTU lookup, interpolation, labelled screening-only | **Partial** | relative index published honestly (`AnalogResult`, `.ino`), no NTU conversion — matches "keep index until calibration"; interpolation table is proposed, not built |
| Flags gate published values + `calibration_status` in diagnostics | **Implemented** | `PH_CALIBRATED` / `TDS_CALIBRATED` / `TURBIDITY_CALIBRATED` are referenced at publish time: uncalibrated pH/TDS publish JSON `null` with an explanatory error, per-sensor `calibration_status` appears in `diagnostics`; `TURBIDITY_CALIBRATED` is an explicit placeholder that still publishes `relative_index_0_100` |
| Versioned recalibration events in docs | **Partial** | project-configured screening constants recorded in `docs/FEATURE_STATUS.md`; per-sensor calibration versioning not started |

## 6. Dataset and ML

| Spec item | Status | Evidence |
|---|---|---|
| External dataset inspected (columns/units/rows/labels/provenance) | **Partial** | `ml/data/external/water_quality_dataset1.csv`: 100,799 rows + header, columns `pH, TDS_ppm, Turbidity_NTU, Temperature_C, Label` — units match the four sensors except turbidity is **NTU**, not the relative index. Label appears rule-derived. **Provenance/license missing** (`docs/PROJECT_AUDIT_REPORT.md` §5 marks it UNVERIFIED; no `SOURCES.md`) |
| Dataset not used for suitability rules | **Implemented** | suitability uses configured profiles only (`water_suitability.py`, `suitability_engine.py`) |
| Bootstrap/benchmark anomaly + quality models, then retrain on real readings | **Partial** | RF trained on the benchmark (plan is rule recovery); IF retrained on the cleaned benchmark split (70,560 rows, unsupervised, labels unused) replacing the 9-row model — but still **benchmark** data, not readings from this hardware (`ml/scripts/train_isolation_forest.py`, `ml/reports/evaluation_report.md`) |
| Never train/test same rows; time/station-aware splits; metrics reported | **Partial** | stratified + chronological splits with global boundaries (`ml/tests/test_data_leakage.py`); **station-aware** split does not apply (single benchmark station) — metrics published honestly incl. the 99.99 % rule-recovery caveat |
| Pin sklearn to match saved models / fix 1.4.2 vs 1.7.2 skew | **Implemented** | `ml/requirements.txt` pins `scikit-learn==1.4.2` and the IF was **retrained and re-saved under the pinned version**, removing the 1.7.2 pickle skew; artifact metadata recorded in `ml/models/model_manifest.json` |
| Forecast method documented + uncertainty intervals | **Partial** | Ridge-vs-persistence baseline, holdout gate (`app/services/forecasting.py`, docs); **no probabilistic interval** — the holdout MAE is an evaluation metric, not a prediction interval, and is documented as such |
| Versioned model artifacts + metrics beside artifact | **Implemented** | `ml/models/model_manifest.json` records version/training-data/metrics per artifact; `ml/reports/evaluation_report.md` recomputes metrics from the saved predictions |
| SHAP/feature importance where useful | **Partial** | SHAP artifacts exist offline; not exposed by any API |

## 7. Backend additions

| Spec item | Status | Evidence |
|---|---|---|
| Device registry (device number → device_id/station/owner/activation; seed first device) | **Implemented** | `product_devices` gained `device_number` (migration `f1e2d3c4b5a6`); `seed_demo.py` seeds `HSD-0001-K7M2Q9` → `ESP32-HS-001` / `ARK-001` |
| Device-number activation + login | **Implemented** | `POST /api/auth/device-login` (generic errors, rate-limited) + `POST /api/product/activate`; `tests/test_device_registry.py` |
| Notification service email/push + dedup/severity/cooldown/prefs/delivery log | **Partial** | Email implemented (`app/services/notification_service.py`, `notifications` migration `a7b8c9d0e1f2`, dedup + cooldown + preferences + delivery log, honest `skipped_unconfigured`); no push/SMS channel |
| Incident + lab workflow (incident table, lab contacts, PDF report, status timeline, lab result ingestion, audit trail) | **Implemented (backend)** | `incidents.py` + `incident_service.py` + `incident_pdf.py`, migration `b8c9d0e1f2a3`, `tests/test_incidents.py`; frontend pages not yet wired |
| QR service (per-station, stable URL, PNG/SVG/PDF) | **Implemented** | `app/api/v1/qr.py` + authority `QrCodes.tsx`, `tests/test_qr.py` |
| Keep telemetry validation, per-row turbidity units, provenance, DB rate limiting, Alembic | **Implemented** | see FEATURE_STATUS §2; migrations at head `b8c9d0e1f2a3` |

## 8. Frontend additions

| Spec item | Status | Evidence |
|---|---|---|
| Authority map | **Missing (visual)** | placeholder canvas |
| Authority live board/station detail keyed by `station_code` | **Partial** | LiveMonitoring keys real stations; `StationDetail.tsx` still keyed by mock ids (`source-tg-halli`) → 404s on real cards |
| Authority alerts, incidents, lab contact, forecast cards, QR generator | **Partial** | Alerts real; forecast card real (gated); QR generator real (backend-backed); incidents/lab pages still render labelled demos although their backend exists |
| Public QR landing with four suitability cards + explanations + freshness + "needs further testing" | **Partial** | real public page exists with six-use cards; "needs further testing" wording not standardized |
| Personal device login / tank dashboard / history / alerts | **Implemented** | email login, device-number login, check-water, history and alert delivery with preferences/delivery log all real (`/product/notifications`) |

## 9. Honesty defects still open (from previous audits, file-level)

1. ~~`WaterCheck.tsx` certification wording~~ — **fixed**: the page now renders the public
   suitability API result with screening notices (no DO claim, no “Certification”).
2. `frontend/src/pages/authority/StationDetail.tsx` — mock-id keying (functional break) still open;
   the page now carries a visible demo notice.
3. CommandCenter / Analytics / WaterSources / NearbySources / Warnings mock remnants — still
   present, each now behind a visible demo notice with the exact reason.
4. ~~Personal `MyChecks` “Safe” badge~~ — **fixed** (honest wording, labelled demonstration history).
5. ~~Firmware docs vs sketch mismatches~~ — **fixed** (`firmware/README.md` §10 matches the sketch;
   `TDS_CAL_V0/V250` and the stale 1.1378 V comment are gone).
6. ~~IF artifact pickled under sklearn 1.7.2~~ — **fixed** (retrained and saved under 1.4.2,
   recorded in `ml/models/model_manifest.json`).

## 10. Next steps per the spec's deliverable order

1. **Firmware calibration + flag gating + README fix** — **done** (fit, gating, docs; hardware verification still open).
2. **Device-number registry + login** — **done** (`HSD-0001-K7M2Q9` seeded, tested).
3. **Notification service** — **done for email** (delivery log, cooldown, preferences); push/SMS not built.
4. **Incident + lab workflow + PDF** — **backend done, UI not wired**.
5. **QR backend service + public landing polish** — **done**.
6. **Dataset inspection + ML retraining + version pinning** — **done**; forecasting uncertainty interval remains open (no probabilistic model).
7. **Mock-screen removal/label pass** — **labelled**; Command Center / Water Sources / Analytics / Station Detail / Incidents / Laboratory / Inspections still show demos.
8. **MQTT broker auth/TLS + rate limits + ingestion bounds** — **code done**; broker-side ACL/TLS verification still open.
9. **Test sprint + docs/test-count update** — **done**: 668 backend + 140 ML + 74 frontend = 882 passing, docs updated.

## 11. Unable to verify (list)

- ESP32 firmware behavior on hardware, real sensor voltages, buffer calibration values.
- Mosquitto broker delivery, ACL/TLS behavior (no broker config is committed; README ships a
  reference `allow_anonymous false` + ACL snippet, unexercised).
- Dataset provenance/licence for `water_quality_dataset1.csv` (no record in repo).
- Production deployment configuration (static checks only: `scripts/verify_production_config.py`).
- Email delivery, phone QR scan, lab ingestion, GIS backend.
