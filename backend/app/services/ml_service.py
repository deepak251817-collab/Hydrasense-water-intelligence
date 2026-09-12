"""ML Inference Service (Phase 6) — live Isolation Forest + Random Forest.

Loads the ALREADY-TRAINED Phase 5B / 5C-2 model artifacts and serves anomaly
screening and Safe/Unsafe classification for live telemetry. NO training
happens here; if a model artifact is missing the service is marked unavailable
rather than fabricating results.

Honesty (Phase 6 section 18):
- Isolation Forest identifies unusual sensor patterns.
- Random Forest predicts the benchmark dataset's Safe/Unsafe classification.
Neither output is laboratory confirmation, guaranteed safety, guaranteed
contamination, or causal pollution detection.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import joblib
import numpy as np
import pandas as pd

logger = logging.getLogger("hydrasense.ml")

# Project root: backend/app/services/ -> <root>
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
MODELS_DIR = PROJECT_ROOT / "ml" / "models"
ISOLATION_FOREST_PATH = MODELS_DIR / "isolation_forest.joblib"
RANDOM_FOREST_PATH = MODELS_DIR / "random_forest_classifier.joblib"

# Explicit feature contracts (Phase 6 section 3). The order of these arrays is
# EXACTLY the order used at training time; inputs are always assembled as a
# named pandas DataFrame in this order, never a bare list, so no dictionary or
# memory ordering can silently permute features.
ISOLATION_FOREST_FEATURES = ["ph", "turbidity", "tds", "temperature"]
RANDOM_FOREST_FEATURES = ["pH", "tds", "turbidity", "temperature"]

# Physical validation ranges. Temperature uses the Phase 5 ML cleaning range
# (ml/preprocessing/clean_data.py); pH, turbidity, and TDS follow the live
# sensor validation rules from Phase 4 telemetry ingestion.
VALIDATION_RANGES = {
    "pH": (0.0, 14.0),
    "turbidity": (0.0, None),
    "tds": (0.0, None),
    "temperature": (-10.0, 60.0),
}


class MLValidationError(ValueError):
    """Raised when telemetry values are invalid for ML inference."""


class MLServiceUnavailableError(RuntimeError):
    """Raised when inference is requested but models are not loaded."""


@dataclass(frozen=True)
class MLResult:
    """Structured ML result (Phase 6 section 5).

    anomaly_label: 1 = anomalous condition identified by Isolation Forest
        (an unusual sensor pattern, NOT contamination), 0 = normal pattern.
        Normalized from sklearn's native -1 (outlier) / +1 (inlier) convention.
    anomaly_score: Isolation Forest decision function (higher = more normal;
        negative values indicate anomalous patterns).
    water_quality_label: Random Forest "predicted water-quality class"
        ("Safe"/"Unsafe") for the benchmark dataset — not a laboratory result.
    safe_probability / unsafe_probability: RF class probabilities in [0, 1].
    """

    anomaly_label: int
    anomaly_score: float
    water_quality_label: str
    safe_probability: float
    unsafe_probability: float

    def to_dict(self) -> dict:
        return {
            "anomaly_label": self.anomaly_label,
            "anomaly_score": self.anomaly_score,
            "water_quality_label": self.water_quality_label,
            "safe_probability": self.safe_probability,
            "unsafe_probability": self.unsafe_probability,
        }


def validate_ml_features(
    ph: float, turbidity: float, tds: float, temperature: float
) -> None:
    """Validate the four live features for ML inference.

    Rejects missing/NaN/infinite/non-numeric values and out-of-range physics.
    Invalid sensor values are NEVER silently repaired (Phase 6 section 4).
    """
    for name, value in (
        ("pH", ph), ("turbidity", turbidity),
        ("tds", tds), ("temperature", temperature),
    ):
        if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
            raise MLValidationError(f"{name} must be a real number, got {value!r}")
        if np.isnan(value) or np.isinf(value):
            raise MLValidationError(f"{name} must be finite, got {value!r}")

    lo, hi = VALIDATION_RANGES["pH"]
    if not (lo <= ph <= hi):
        raise MLValidationError(f"pH out of valid physical range [{lo}, {hi}]: {ph}")
    if turbidity < 0.0:
        raise MLValidationError(f"turbidity cannot be negative: {turbidity}")
    if tds < 0.0:
        raise MLValidationError(f"tds cannot be negative: {tds}")
    lo, hi = VALIDATION_RANGES["temperature"]
    if not (lo <= temperature <= hi):
        raise MLValidationError(
            f"temperature out of valid physical range [{lo}, {hi}]: {temperature}"
        )


class MLService:
    """Holds the two live models and serves structured inference results.

    Models are loaded lazily once (never at import time, never retrained) and
    kept for the process lifetime.
    """

    def __init__(
        self,
        isolation_forest_path: Path = ISOLATION_FOREST_PATH,
        random_forest_path: Path = RANDOM_FOREST_PATH,
    ) -> None:
        self.isolation_forest_path = Path(isolation_forest_path)
        self.random_forest_path = Path(random_forest_path)
        self.isolation_forest = None
        self.random_forest = None
        self._loaded = False

    @property
    def is_available(self) -> bool:
        return self._loaded and self.isolation_forest is not None and self.random_forest is not None

    def load_models(self) -> bool:
        """Load both model artifacts once; return availability.

        A missing/corrupt artifact marks the service unavailable — the caller
        decides policy (fail clearly at startup or degrade gracefully).
        """
        import warnings

        self.isolation_forest = None
        self.random_forest = None
        self._loaded = False

        for kind, path in (
            ("Isolation Forest", self.isolation_forest_path),
            ("Random Forest", self.random_forest_path),
        ):
            if not path.exists():
                logger.error(
                    "ML model artifact missing: %s ('%s'). ML service is UNAVAILABLE; "
                    "telemetry ingestion continues without ML results.",
                    kind, path,
                )
                return False

        try:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always", UserWarning)
                iso = joblib.load(self.isolation_forest_path)
                rf = joblib.load(self.random_forest_path)
            for w in caught:
                if issubclass(w.category, UserWarning):
                    # Known cross-version pickles (IF trained under sklearn
                    # 1.7.2, RF under 1.4.2). Logged once; predictions verified
                    # by the Phase 6 test suite against Phase 5 behavior.
                    logger.warning("Model load warning (%s): %s", w.category.__name__, str(w.message)[:160])
        except Exception as exc:
            logger.error("Failed to load ML models: %s", exc, exc_info=True)
            return False

        # Validate expected feature contracts before serving (Phase 6 section 11).
        n_iso = getattr(iso, "n_features_in_", len(ISOLATION_FOREST_FEATURES))
        n_rf = getattr(rf, "n_features_in_", len(RANDOM_FOREST_FEATURES))
        if n_iso != len(ISOLATION_FOREST_FEATURES) or n_rf != len(RANDOM_FOREST_FEATURES):
            logger.error(
                "Model feature-count contract mismatch: IsolationForest expects %s features, "
                "RandomForest expects %s; service contract provides %s/%s.",
                n_iso, n_rf, len(ISOLATION_FOREST_FEATURES), len(RANDOM_FOREST_FEATURES),
            )
            return False

        self.isolation_forest = iso
        self.random_forest = rf
        self._loaded = True
        logger.info(
            "ML models loaded: IsolationForest (%s features) and RandomForest (%s features) "
            "from %s",
            n_iso, n_rf, MODELS_DIR,
        )
        return True

    def predict(self, ph: float, turbidity: float, tds: float, temperature: float) -> MLResult:
        """Run anomaly screening + Safe/Unsafe classification on one reading."""
        if not self.is_available:
            raise MLServiceUnavailableError(
                "ML models are not loaded; inference is unavailable. "
                "No prediction is fabricated."
            )
        validate_ml_features(ph, turbidity, tds, temperature)

        try:
            X_iso = pd.DataFrame(
                [[ph, turbidity, tds, temperature]],
                columns=ISOLATION_FOREST_FEATURES,  # exact training order
            )
            raw_iso_label = int(self.isolation_forest.predict(X_iso)[0])
            # sklearn convention: -1 = outlier, +1 = inlier. Spec contract
            # (Phase 6 section 5): anomaly_label is 0 or 1 with 1 = anomalous.
            anomaly_label = 1 if raw_iso_label == -1 else 0
            anomaly_score = float(self.isolation_forest.decision_function(X_iso)[0])
            logger.info(
                "ML inference success: anomaly_label=%s (sklearn raw=%s) anomaly_score=%.6f",
                anomaly_label, raw_iso_label, anomaly_score,
            )
        except MLValidationError:
            raise
        except Exception as exc:
            logger.error("Isolation Forest inference failed: %s", exc, exc_info=True)
            raise

        try:
            X_rf = pd.DataFrame(
                [[ph, tds, turbidity, temperature]],
                columns=RANDOM_FOREST_FEATURES,  # exact training order (tds before turbidity)
            )
            proba = self.random_forest.predict_proba(X_rf)[0]
            classes = [str(c) for c in self.random_forest.classes_]
            prob_map = dict(zip(classes, (float(p) for p in proba)))
            safe_probability = prob_map.get("Safe", 0.0)
            unsafe_probability = prob_map.get("Unsafe", 0.0)
            water_quality_label = str(self.random_forest.predict(X_rf)[0])
            logger.info(
                "ML inference success: water_quality_label=%s safe_p=%.6f unsafe_p=%.6f",
                water_quality_label, safe_probability, unsafe_probability,
            )
        except Exception as exc:
            logger.error("Random Forest inference failed: %s", exc, exc_info=True)
            raise

        return MLResult(
            anomaly_label=anomaly_label,
            anomaly_score=anomaly_score,
            water_quality_label=water_quality_label,
            safe_probability=safe_probability,
            unsafe_probability=unsafe_probability,
        )


# Process-wide singleton, loaded during application startup (app.main lifespan).
ml_service = MLService()
