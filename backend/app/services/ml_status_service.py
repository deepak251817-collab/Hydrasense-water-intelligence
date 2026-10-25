"""ML transparency service: model health + real evaluation metrics.

Serves the machine-readable report produced by
`ml/scripts/build_evaluation_report.py` together with the live load state of
the inference service. Deliberately returns only public metadata — model file
NAMES, feature contracts and computed metrics — never absolute paths, dataset
credentials, or model internals.

If the report is missing, `evaluation_available` is False and `evaluation` is
None. No metric is ever fabricated or defaulted.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("hydrasense.ml_status")

# backend/app/services/ml_status_service.py -> project root
PROJECT_ROOT = Path(__file__).resolve().parents[3]
EVALUATION_REPORT_PATH = PROJECT_ROOT / "ml" / "reports" / "evaluation_report.json"
MODELS_DIR = PROJECT_ROOT / "ml" / "models"

# Public relative label for the report (no filesystem paths leak to clients).
REPORT_LABEL = "ml/reports/evaluation_report.json"

MODEL_CATALOG = (
    {
        "key": "isolation_forest",
        "name": "Isolation Forest",
        "role": "Unsupervised anomaly screening (unusual sensor patterns)",
        "file": "isolation_forest.joblib",
        "features": ["ph", "turbidity", "tds", "temperature"],
        "live_inference": True,
    },
    {
        "key": "random_forest",
        "name": "Random Forest",
        "role": "Safe/Unsafe water-quality classification (predicted class)",
        "file": "random_forest_classifier.joblib",
        "features": ["pH", "tds", "turbidity", "temperature"],
        "live_inference": True,
    },
    {
        "key": "xgboost",
        "name": "XGBoost",
        "role": "Offline deterioration prediction (not connected to live inference)",
        "file": "xgboost_deterioration.joblib",
        "features": [],
        "live_inference": False,
    },
)


def load_evaluation_report(report_path: Path | None = None) -> Optional[dict[str, Any]]:
    """Load the evaluation report, returning None when absent/corrupt.

    A corrupt report is logged and treated as unavailable — never replaced with
    placeholder metrics.
    """
    path = Path(report_path) if report_path is not None else EVALUATION_REPORT_PATH
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as err:
        logger.warning("ML evaluation report unreadable (%s): %s", path.name, err)
        return None
    if not isinstance(data, dict):
        logger.warning("ML evaluation report is not a JSON object: %s", path.name)
        return None
    return data


def _models_loaded(ml_service: Any) -> dict[str, bool]:
    loaded = bool(getattr(ml_service, "is_available", False))
    return {
        "isolation_forest": loaded and getattr(ml_service, "isolation_forest", None) is not None,
        "random_forest": loaded and getattr(ml_service, "random_forest", None) is not None,
        "xgboost": False,  # deliberately not served by the API
    }


def build_ml_status(
    ml_service: Any,
    report_path: Path | None = None,
) -> dict[str, Any]:
    """Assemble the status payload (see MLStatusResponse)."""
    report = load_evaluation_report(report_path)
    loaded = _models_loaded(ml_service)

    models = []
    for entry in MODEL_CATALOG:
        artifact = MODELS_DIR / entry["file"]
        models.append({
            "key": entry["key"],
            "name": entry["name"],
            "role": entry["role"],
            "file": entry["file"],  # name only, never an absolute path
            "features": list(entry["features"]),
            "live_inference": entry["live_inference"],
            "artifact_present": artifact.exists(),
            "loaded": bool(loaded.get(entry["key"], False)),
        })

    return {
        "models": models,
        "evaluation_available": report is not None,
        "evaluation": report,
        "report": REPORT_LABEL if report is not None else None,
        "generated_at": report.get("generated_at") if report else None,
    }
