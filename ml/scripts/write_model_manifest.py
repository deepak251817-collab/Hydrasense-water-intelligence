"""Write a versioned manifest describing every served model artifact.

The manifest records, for each artifact: filename, size, SHA-256, estimator
type, sklearn version used to save it, file modification time (UTC), feature
contract, live-inference status, training source, and the metrics from the
generated evaluation report. It never invents metrics: values are copied from
``ml/reports/evaluation_report.json`` or reported as null.

Run:  python ml/scripts/write_model_manifest.py
"""

from __future__ import annotations

import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import joblib
import sklearn

MODELS_DIR = PROJECT_ROOT / "ml" / "models"
REPORT_PATH = PROJECT_ROOT / "ml" / "reports" / "evaluation_report.json"
MANIFEST_PATH = MODELS_DIR / "model_manifest.json"

MODEL_SPECS: dict[str, dict[str, Any]] = {
    "isolation_forest.joblib": {
        "key": "isolation_forest",
        "role": "Unsupervised anomaly screening",
        "features": ["ph", "turbidity", "tds", "temperature"],
        "live_inference": True,
        "trained_on": "ml/data/processed/supervised_train.csv (70,560 rows; label unused)",
        "report_section": "isolation_forest",
        "limitations": [
            "Trained on an external benchmark distribution; recalibrate on real calibrated site telemetry.",
            "No ground-truth contamination labels: the anomaly rate is descriptive, not a contamination rate.",
            "An anomaly is an unusual sensor pattern, never confirmed pollution.",
        ],
    },
    "random_forest_classifier.joblib": {
        "key": "random_forest",
        "role": "Safe/Unsafe benchmark classification (advisory)",
        "features": ["pH", "tds", "turbidity", "temperature"],
        "live_inference": True,
        "trained_on": "ml/data/processed/supervised_train.csv (70,560 rows)",
        "report_section": "random_forest",
        "limitations": [
            "The Safe/Unsafe label follows the benchmark dataset's labeling rule, not laboratory potability.",
            "Metrics come from a static benchmark test split, not the live sensors.",
            "Never overrides or alters rule-based suitability screening.",
        ],
    },
    "xgboost_deterioration.joblib": {
        "key": "xgboost",
        "role": "Offline future-deterioration analysis (not live)",
        "features": "ml/data/processed/xgboost_feature_list.txt (36 USGS-derived columns)",
        "live_inference": False,
        "trained_on": "ml/data/processed/forecast_train.csv (5,321 rows, USGS-01649190)",
        "report_section": "xgboost",
        "limitations": [
            "Offline only: requires USGS lag/rolling and conductivity features live telemetry cannot supply.",
            "Single station, ~5 weeks of synchronized data; temporal generalization is limited.",
            "Predicts a rule-based deterioration indicator, not confirmed contamination.",
        ],
    },
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest() -> dict[str, Any]:
    report: dict[str, Any] = {}
    if REPORT_PATH.exists():
        report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))

    artifacts = []
    for filename, spec in MODEL_SPECS.items():
        path = MODELS_DIR / filename
        if not path.exists():
            artifacts.append({"file": filename, "present": False, **{k: v for k, v in spec.items() if k != "report_section"}})
            continue

        model = joblib.load(path)
        section = report.get(spec["report_section"], {}) if report else {}
        metrics = section.get("metrics") if isinstance(section, dict) else None
        summary = section.get("summary") if isinstance(section, dict) else None

        artifacts.append(
            {
                "file": filename,
                "present": True,
                "key": spec["key"],
                "role": spec["role"],
                "estimator": type(model).__name__,
                "features": spec["features"],
                "live_inference": spec["live_inference"],
                "trained_on": spec["trained_on"],
                "saved_with_sklearn": sklearn.__version__,
                "size_bytes": path.stat().st_size,
                "sha256": _sha256(path),
                "modified_at_utc": datetime.fromtimestamp(
                    path.stat().st_mtime, tz=timezone.utc
                ).isoformat(),
                "metrics": metrics or summary,
                "metrics_source": (
                    "ml/reports/evaluation_report.json" if (metrics or summary) else None
                ),
                "limitations": spec["limitations"],
            }
        )

    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generator": "ml/scripts/write_model_manifest.py",
        "environment": {
            "python": platform.python_version(),
            "scikit_learn": sklearn.__version__,
        },
        "policy": (
            "Every served artifact is listed with its checksum, feature contract, "
            "training source and measured metrics. Missing artifacts are reported as "
            "absent, never replaced with placeholders."
        ),
        "artifacts": artifacts,
    }


def main() -> int:
    manifest = build_manifest()
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Wrote {MANIFEST_PATH.relative_to(PROJECT_ROOT)}")
    for artifact in manifest["artifacts"]:
        state = "present" if artifact["present"] else "MISSING"
        print(f"  - {artifact['file']}: {state}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
