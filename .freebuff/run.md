# Run Doc — hydrasense-water-intelligence (Preview)

Project: Real-Time Water Quality Assessment and Intelligent Alert System Using
ML and IoT. Frontend is a Vite + React 19 + Tailwind 4 SPA in `frontend/`
(npm, `package-lock.json`). The ML pipeline (Phases 5A–5E) lives in `ml/`.

## 1. Reproduce the artifacts a fresh checkout needs

- Frontend dependencies (required to run the dev server):
  ```bash
  cd frontend && npm install
  ```
  `node_modules` is normally already present; run this only after a clean clone.
- ML processed artifacts (`ml/data/processed/*.csv`, model joblib files, SHAP
  outputs) are **not** required by the frontend dev server. If they must be
  regenerated from raw inputs, in order:
  ```bash
  python ml/scripts/prepare_supervised_splits.py   # Phase 5C-1 splits
  python ml/scripts/train_random_forest.py         # Phase 5C-2 model
  python ml/scripts/prepare_usgs_forecast_dataset.py  # Phase 5D-1 forecast splits
  python ml/scripts/train_xgboost.py               # Phase 5D-2 model
  python ml/scripts/explain_random_forest.py       # Phase 5E RF SHAP artifacts
  python ml/scripts/explain_xgboost.py             # Phase 5E XGBoost SHAP artifacts
  ```
- Environment files: none are required for the frontend dev server. The
  backend (FastAPI + PostgreSQL) is not started for the preview; if it ever is,
  copy any `.env` from the main checkout and adapt ports locally (never commit).

## 2. Run the dev server

- Package manager: **npm** (frontend/package-lock.json).
- Default port: **5173** (vite default; `frontend/vite.config.ts` sets none).
  If 5173 is busy, use `npm run dev -- --port 5174`.
- Start detached (Windows) so it outlives the conversation, logging stdout and
  stderr to separate files:
  ```powershell
  powershell -NoProfile -Command "(Start-Process -FilePath 'npm.cmd' -ArgumentList 'run','dev' -WorkingDirectory 'C:\Users\deepa\OneDrive\Desktop\hydrasense-water-intelligence\frontend' -RedirectStandardOutput 'C:\Users\deepa\OneDrive\Desktop\hydrasense-water-intelligence\.freebuff\preview.log' -RedirectStandardError 'C:\Users\deepa\OneDrive\Desktop\hydrasense-water-intelligence\.freebuff\preview.log.err' -WindowStyle Hidden -PassThru).Id"
  ```
- Confirm it survived and answers before registering the preview:
  ```powershell
  powershell -NoProfile -Command "Get-Process -Id <pid>"
  curl -s -o NUL -w "%{http_code}" http://localhost:5173/
  ```
- Frontend regression checks (not needed to start, but kept green):
  `npm run build` and `npm run lint` in `frontend/`; ML tests via
  `python -m pytest ml/tests` from the repo root.
