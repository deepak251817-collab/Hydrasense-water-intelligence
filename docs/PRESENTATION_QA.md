# HydraSense — Presentation Q&A

> Answers written for a technical viva. Each one is grounded in code that exists in this checkout.
> Where the honest answer is "we did not verify that", the answer says so. Bluffing is the fastest
> way to lose marks — examiners probe the second sentence.

---

## A. Problem and architecture

**1. What problem does HydraSense solve?**

It turns cheap IoT water sensors into an auditable water-quality signal: ingest validated telemetry
from ESP32 stations, store it with provenance, screen it against BIS/CPCB standards for six intended
uses, flag unusual patterns with an ML model, and publish a QR-linked public page so citizens can see
the same data. It explicitly separates *what was measured* from *what was inferred*.

**2. Walk me through the architecture.**

Four layers: (1) ESP32 station or Python simulator publishing JSON over MQTT; (2) FastAPI backend
with an MQTT subscriber that validates, de-duplicates and stores readings in PostgreSQL, then derives
suitability assessments and ML results; (3) an `ml/` workspace holding datasets, training scripts and
three joblib artifacts; (4) a React SPA with public, product-user and authority surfaces. Diagram:
[PROJECT_GUIDE.md §3](PROJECT_GUIDE.md#3-system-architecture).

**3. Why MQTT instead of HTTP from the device?**

MQTT is publish/subscribe with QoS 1, a small binary overhead, keep-alives and offline resilience —
appropriate for a constrained device on an unreliable network. HTTP would need the device to know the
backend address, handle retries and auth, and would be chattier. The device only needs the broker
host and a topic.

**4. Why FastAPI and PostgreSQL?**

FastAPI gives typed Pydantic contracts, automatic OpenAPI docs and dependency-injected auth, which
made the "nullable means unknown" contract enforceable. PostgreSQL gives foreign keys, a JSON column
for diagnostics, unique constraints for idempotent derived data, and real time-zone-aware timestamps.
The tests run on in-memory SQLite so no database is needed in CI.

**5. Why React + Vite?**

Three distinct audiences with shared components; a SPA keeps the QR page instant and lets the
authority dashboard poll. Vite gives a fast dev loop, and the build is a static bundle.

---

## B. IoT and ingestion

**6. What exactly does the ESP32 publish?**

JSON to `hydrasense/stations/<STATION_CODE>/telemetry` every ~3 s with `station_code`, `device_id`,
ISO-8601 UTC `timestamp`, `pH`, `turbidity`, `tds`, `temperature`, `source:"esp32"`, and a
`diagnostics` object (raw ADC counts, voltages, calibration status, uptime, RSSI, error list).
Contract and sample packets: [firmware/README.md](../firmware/README.md).

**7. What happens if a sensor is not calibrated?**

The firmware publishes JSON `null` for that engineering value and puts the raw ADC/voltage into
`diagnostics` with `calibration_status:"pending"`. The backend stores `NULL`, skips ML inference
(because a model input is missing), and the UI renders "Uncalibrated" rather than a number. There is
a test for every branch of that logic in `backend/tests/test_telemetry.py`.

**8. Why is hardware turbidity a "relative index" and not NTU?**

The turbidity module's output (~3.5–3.7 V) must pass through a two-resistor divider to stay within
the ADS1115's 3.3 V limit, and no formazin standard calibration has been performed. So the firmware
reports a 0–100 index anchored to two sample voltages, and tags it
`diagnostics.turbidity.unit = "relative_index_0_100"`. Storing that number as NTU would silently
corrupt every downstream comparison, so the backend records the unit per row and **excludes
relative-index readings from NTU-based ML inference and NTU-based suitability limits**.

**9. How do you stop duplicate readings?**

Two independent checks. The backend queries for an existing `(station_id, device_id, timestamp)`
before inserting and logs `Skipped duplicate telemetry` (covers MQTT QoS 1 redelivery and device
retransmits). The database also has the same key available for a unique constraint if you want
hard enforcement; today it is an application-level guard, which the tests cover.

**10. What if a device publishes an unknown station code?**

The reading is rejected with a warning — stations are configuration, not something a device can
create. `backend/scripts/seed_demo.py` creates `ARK-001..003`.

**11. What if the payload is malformed or physically impossible?**

`validate_telemetry_payload` rejects: missing required fields, empty station/device ids, non-ISO
timestamps (a date without a time is rejected so readings do not collapse to midnight), booleans
masquerading as numbers, out-of-range values (pH 0–14, temperature −20…70 °C, non-negative TDS and
turbidity, relative index ≤ 100), malformed turbidity unit/status, invalid `source` tags, and
diagnostics blobs over 8 KiB. Rejections are logged with the reason and never stored.

**12. How do you distinguish simulator data from real hardware?**

A `source` column (`simulator` / `esp32`) on every row, plus `turbidity_unit` and `diagnostics`.
Suitability refuses to compare anything that is not `source="esp32"` and calibrated, and the public
page shows "physical station hardware" vs "simulated demonstration data".

**13. Is the simulator data scientifically valid?**

No, and the repository says so in `ml/README.md` and in the evaluation report. It exists to exercise
the pipeline. Scenario names (`normal`, `deteriorating`, `sudden_event`, `sensor_fault`) are not
ground-truth labels.

**14. Has the firmware been deployed in the field?**

Not verified in this repository. The sketch, wiring guide, payload contract and backend tests exist;
there is no field deployment log, no calibration record, and no hardware-in-the-loop test. Say
"implemented and contract-tested" rather than "deployed".

---

## C. Data

**15. What datasets do you use, and how big are they?**

Four USGS continuous series (10,000 rows each, one station `USGS-01649190`, 5-minute cadence,
Jan–Feb 2024), one 100,800-row Safe/Unsafe benchmark table, and a 9-row telemetry export from the
simulator. Full columns, ranges and caveats: [DATASET_CATALOG.md](DATASET_CATALOG.md).

**16. Where did the 100,800-row dataset come from?**

**That provenance is not recorded in the repository** — there is no URL, citation or license. Two
things are verifiable from the file: the label is 30 % Safe / 70 % Unsafe, and a Random Forest
reproduces it with 2 errors in 15,120 rows, which means the label is a deterministic rule over the
same four features. It is not field-validated potability data. Recording the source is an explicit
remaining task.

**17. Why do the "2024" USGS files hold only ~5 weeks?**

Each file is a 10,000-row export cap, not a full year. The names are misleading; the catalog records
the real spans.

**18. Is specific conductance the same as TDS?**

No. USGS parameter 95 is specific conductance in µS/cm; TDS is a mass concentration in mg/L. The
forecasting pipeline keeps `specific_conductance` as its own column and never converts or renames it.
The benchmark's `TDS_ppm` column is a separate, unrelated measurement.

**19. How did you prevent data leakage?**

- Supervised: stratified 70/15/15 split of the benchmark with `random_state=42`; the target is never a
  feature; `ml/tests/test_data_leakage.py` asserts both.
- Forecasting: chronological 70/15/15 with **global timestamp boundaries**, an INNER join strictly on
  identical timestamps, and only lag/rolling features computed from rows **before** the current one.
- Anomaly: the Isolation Forest fits only on `train.csv`; validation/test are never used for fitting.
- The evaluation report is recomputed from saved prediction files, not from training-time numbers.

**20. Why is your telemetry training set only 9 rows?**

Because that is what the simulator export contains (three snapshots of three stations, 5.1 seconds
apart). `create_splits.py` makes it 6 train / 0 validation / 3 test. The shipped Isolation Forest is
therefore a **pipeline demonstration**, not a trained detector — the model loads and serves, but its
anomaly rate (4 of 9) is descriptive only. Fixing this is the top remaining ML task.

**21. What cleaning did you actually perform?**

A new script `ml/preprocessing/clean_datasets.py` cleans copies of all six datasets into
`ml/data/processed/cleaned/` and writes a JSON + Markdown audit. Result: 140,809 rows in, 140,809 out,
**0 rows removed**, sources byte-identical (SHA-256 checked). The datasets were already tidy, so the
deliverable is the reproducible recipe and the corruption proof, not a big deletion count. Details:
[DATA_CLEANING_REPORT.md](DATA_CLEANING_REPORT.md).

**22. How do you know cleaning did not corrupt the data?**

Three independent checks, enforced by the script: source SHA-256 unchanged, row counts reconcile
across every step, and the output is a row-subset of the input on key columns. A separate comparison
confirmed the numeric values are identical after sorting.

---

## D. Machine learning

**23. What does each model actually predict?**

| Model | Prediction | Meaning |
|---|---|---|
| Isolation Forest | `anomaly_label` 0/1 + score | The pattern is unusual relative to 6 training rows |
| Random Forest | `Safe` / `Unsafe` + probabilities | The benchmark's label rule applied to four numbers |
| XGBoost | `deterioration_target` 0/1 | A rule-based deterioration flag one observation ahead, USGS features only |

**24. Why is Random Forest accuracy 99.99 %? Isn't that suspicious?**

It is suspicious, and correct to challenge. The label is a deterministic function of the same four
features, and the test split comes from the same static table, so the model is reconstructing a rule:
2 errors in 15,120 rows. It says nothing about field accuracy on ESP32 readings. The report includes
this in its `limitations`, and the honest counterpoint is the XGBoost result — 94 % accuracy but
balanced accuracy 0.54 and Unsafe recall 0.11 — which is what a real imbalanced series looks like.

**25. Why not report precision/recall for the anomaly model?**

There are no ground-truth contamination labels, so any precision/recall would be invented. The report
states the anomaly rate and score range and says they are descriptive only.

**26. Why Isolation Forest rather than an autoencoder or LSTM?**

It needs no labels, is cheap, deterministic with a fixed seed, and its decision function is
explainable enough for a dashboard. With 6 training rows, a deep model would be indefensible. If real
telemetry accumulates, the comparison should be re-run — that is future work, not a current claim.

**27. What features enter each model, and in what order?**

- Isolation Forest: `["ph", "turbidity", "tds", "temperature"]`
- Random Forest: `["pH", "tds", "turbidity", "temperature"]` — a **different order**, which is why
  `ml_service.py` assembles a named DataFrame per contract instead of a bare list.
- XGBoost: 36 features (current values, lags 1–3, rolling mean/std over 3 and 6 past observations,
  one-step changes), all past-only.

**28. What is the XGBoost target exactly?**

1 if, at the next observation, turbidity rises ≥ 10 % **or** specific conductance rises ≥ 10 % **or**
pH moves more than 0.20 units further from 7.0; otherwise 0. Temperature never triggers it. It is a
rule-based deterioration indicator, not contamination. Positive rate in training: 9.04 %.

**29. Why is XGBoost not live in the API?**

It needs USGS-specific lag/rolling and conductivity features that live telemetry does not provide.
`ml_status_service.py` reports it as `live_inference: false` rather than pretending.

**30. How do you handle a missing or corrupt model artifact?**

`ml_service.load_models()` returns False, the service is marked unavailable, ingestion continues, and
affected readings keep `NULL` ML columns. `/authority/ml/status` reports `artifact_present` and
`loaded` per model. No prediction is fabricated — this is enforced by tests and by
`hasMLAnalysis()` in the frontend.

**31. What about SHAP?**

SHAP summaries are generated for Random Forest and XGBoost into `ml/data/processed/`. They are
explainability artifacts for analysis; no API endpoint serves them, and the Analytics page explicitly
labels its SHAP area a placeholder.

---

## E. Suitability and standards

**32. Which standards did you implement?**

BIS IS 10500:2012 (Amendment 4) Table 1 for drinking/domestic (pH 6.5–8.5, TDS 500/2000 mg/L,
turbidity 1/5 NTU) and CPCB Designated Best Use classes for bathing (Class B), aquatic life (Class D)
and irrigation/industrial (Class E). Ruleset version `2026.10.1`.

**33. Why can the system never declare drinking water "safe"?**

Because BIS IS 10500 requires microbiological absence (E. coli / thermotolerant coliform in 100 mL)
and chemical parameters (nitrate, fluoride, arsenic, lead, hardness, chloride, sulfate) that this
station cannot measure. The engine reports those as **missing** and caps the best drinking-water
result at `lab_confirmation_required`. `preliminary_suitable` is structurally unreachable for
drinking water.

**34. What result codes exist?**

`preliminary_suitable`, `treatment_required` (value inside the permissible/relaxed band, or the use
requires treatment), `outside_limits`, `lab_confirmation_required`, `insufficient_data`.

**35. How do you handle stale readings?**

Freshness thresholds mirror the dashboard: ≤ 5 min fresh, ≤ 60 min delayed, older is stale. A stale
reading is reported as stale and never used for a "current" conclusion.

**36. What happens to simulated or relative-index readings in suitability?**

They are excluded from threshold comparison; the data-quality block lists them under
`excluded_parameters` with a reason. No silent substitution.

---

## F. API, security, frontend

**37. How does authentication and authorisation work?**

`POST /auth/login` verifies an argon2 hash (`pwdlib`) and issues a 60-minute HS256 JWT with
`sub`, `role`, `exp`. `get_current_user` decodes it and loads the user; `require_role` produces the
`PRODUCT_USER` and `AUTHORITY` dependencies. Cross-role calls return 403, covered by
`tests/test_rbac.py`. Public routes require no token.

**38. What are the security weaknesses?**

Stated plainly: the registration schema accepts a `role`, so a caller can self-register as
`AUTHORITY`; CORS is `allow_origins=["*"]` with credentials enabled; the JWT secret has a literal
default in `core/config.py`; there is no rate limiting or account lockout; tokens live in
`localStorage`. Each has a fix direction in [FEATURE_STATUS.md §6](FEATURE_STATUS.md#6-security-and-operations-findings).
Fixing the role issue is a five-line change and should be done before submission.

**39. How does the public page avoid leaking device internals?**

Public responses use dedicated schemas (`PublicLatestReading`, `PublicReadingHistoryRow`) that contain
no `diagnostics`, no device credentials and no internal ids beyond the station code. This is
structural, not a filter in the UI.

**40. How does the QR flow work?**

`PublicPageQrCard` encodes `${VITE_PUBLIC_BASE_URL || window.location.origin}/public/source/<station_code>`.
A phone opens that route, `PublicSource` calls three public endpoints (station, latest reading,
history) plus suitability, and renders provenance, the unit-aware turbidity badge, a trend chart and
the six-use assessment. If the base URL is localhost the card warns that the QR only works on that
machine.

**41. How does the frontend handle "no ML analysis"?**

`useLatestAnalysis` maps the response into `success`, `unavailable` (404/409), `unauthorized`, or
`error`, and `hasMLAnalysis()` requires every ML field to be present. The card renders "Analysis
unavailable" instead of a default verdict. There are 27 integration tests around this behaviour.

**42. Which parts of the dashboard are real?**

Real: backend station list, telemetry card, ML analysis card, ML summary, model health, suitability
section, QR card, map data, public pages, auth, device list. Mock: alerts, incidents, inspections,
laboratory, water-source cards, analytics selectors, command-centre KPIs. Exact matrix:
[FEATURE_STATUS.md](FEATURE_STATUS.md).

**43. Why does the station-detail route not show live ML?**

It is still keyed by mock source ids (`source-tg-halli`) while `MlLatestCard` sends that id to the
real API, which returns 404. The live station view is `/authority/monitoring`. This is a known
integration gap, not a hidden one.

---

## G. Testing, quality, limitations

**44. What testing do you have?**

353 automated tests: 152 backend (auth, RBAC, telemetry contract, ML API, suitability, water sources),
140 ML (pipeline, leakage, reproducibility, persistence, SHAP, forecasting), 61 frontend (turbidity
unit handling, ML integration, suitability UI, model health). All pass in this checkout, and lint and
production build are clean.

**45. What do the tests *not* cover?**

No hardware-in-the-loop test, no live broker end-to-end test (the subscriber's handler is tested
directly), no browser E2E (Playwright/Cypress), no load/performance test, and no coverage report —
so do not quote a coverage percentage.

**46. What are the biggest limitations?**

1. Isolation Forest trained on 9 rows (6 train) — a demonstration, not a detector.
2. Benchmark provenance unknown and label rule unverified; live accuracy unproven.
3. Large parts of the authority dashboard are mock UI.
4. No alerting/incident/notification backend; no product-user reading submission.
5. Hardware deployment unverified; turbidity is a relative index, pH/TDS uncalibrated by default.
6. Security gaps in role assignment, CORS and secret defaults.

**47. What would you do first with more time?**

Fix the role-escalation hole, record dataset provenance, replace the mock authority screens with the
existing API, and collect real telemetry to retrain the anomaly model. Ranked list with effort and
impact: [PROJECT_AUDIT_REPORT.md](PROJECT_AUDIT_REPORT.md).

**48. Why should we believe any of your numbers?**

Because they are regenerated from artifacts, not typed: `python ml/scripts/build_evaluation_report.py`
recomputes every metric from saved predictions and model files, and the report embeds model SHA-256
hashes, sizes and library versions. The cleaning report does the same for row counts and hashes. You
can run both in front of the examiner.

---

## H. Questions not to bluff

If asked any of these, give the honest short answer and move to the remaining-work list:

| Question | Honest answer |
|---|---|
| "Where exactly did the benchmark data come from?" | "Not recorded in the repo; recording it is on our task list." |
| "What accuracy do you get on real sensor data?" | "Unknown — we have not run a field validation." |
| "Is the ESP32 deployed at the river?" | "Firmware is implemented and contract-tested; no field deployment is recorded." |
| "Does it detect pollution?" | "It flags unusual patterns and screens against standards; it does not confirm pollution." |
| "How many users has it served?" | "None — this is a research prototype, not a deployed service." |
| "What is your test coverage?" | "No coverage tool is configured; 353 tests pass, and I can list what they cover." |
