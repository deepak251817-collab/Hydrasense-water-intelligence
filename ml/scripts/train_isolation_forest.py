"""
Isolation Forest Model Training Script for HydraSense ML Pipeline.

Trains an sklearn IsolationForest on the four approved sensor features:
- pH
- turbidity
- TDS
- temperature

Training source (2026-10 remediation): the benchmark training split
``ml/data/processed/supervised_train.csv`` (70,560 rows). The previous model
was fitted on only 9 telemetry rows, which is far too few to define a stable
"normal" region. The benchmark's ``label`` column is **not** used: Isolation
Forest remains fully unsupervised; the larger dataset only supplies realistic
feature distributions. This is an external-benchmark model and must be
recalibrated on real calibrated site telemetry before operational reliance.

Saves the trained model artifact to ml/models/isolation_forest.joblib.
"""

import sys
import argparse
import logging
from pathlib import Path
from typing import Dict, Tuple, Optional, List
import pandas as pd
import numpy as np
import joblib
from sklearn.ensemble import IsolationForest

# Ensure workspace root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BASE_DIR.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_TRAIN_PATH = BASE_DIR / "data" / "processed" / "supervised_train.csv"
DEFAULT_MODEL_PATH = BASE_DIR / "models" / "isolation_forest.joblib"

# Core approved sensor features, in the exact order the backend assembles them.
APPROVED_FEATURES = ["ph", "turbidity", "tds", "temperature"]


def _resolve_feature_columns(df: pd.DataFrame, features: List[str]) -> Dict[str, str]:
    """Map canonical feature names to actual columns (case-insensitive).

    The benchmark table uses ``pH`` while the telemetry export uses ``ph``;
    both describe the same quantity, so the match is case-insensitive and the
    fitted feature order stays canonical.
    """
    lookup = {str(column).strip().lower(): column for column in df.columns}
    mapping: Dict[str, str] = {}
    missing: List[str] = []
    for feature in features:
        actual = lookup.get(feature.lower())
        if actual is None:
            missing.append(feature)
        else:
            mapping[feature] = actual
    if missing:
        raise KeyError(f"Training dataset missing required feature columns: {missing}")
    return mapping
DEFAULT_CONTAMINATION = 0.05
DEFAULT_RANDOM_STATE = 42


def train_isolation_forest(
    train_path: Optional[Path] = None,
    model_path: Optional[Path] = None,
    features: Optional[List[str]] = None,
    contamination: float = DEFAULT_CONTAMINATION,
    random_state: int = DEFAULT_RANDOM_STATE,
    n_estimators: int = 100
) -> IsolationForest:
    """
    Train Isolation Forest model on training split and persist to disk.

    Parameters:
    -----------
    train_path : Path, optional
        Path to processed train.csv
    model_path : Path, optional
        Target path for saving isolation_forest.joblib
    features : List[str], optional
        Sensor features to train on (defaults to approved 4 parameters)
    contamination : float
        Expected ratio of anomalies in dataset
    random_state : int
        Random seed for reproducibility
    n_estimators : int
        Number of trees in forest
    """
    src_path = Path(train_path).resolve() if train_path else DEFAULT_TRAIN_PATH.resolve()
    dest_path = Path(model_path).resolve() if model_path else DEFAULT_MODEL_PATH.resolve()
    target_features = features or APPROVED_FEATURES

    dest_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Loading training data from %s", src_path)
    if not src_path.exists():
        raise FileNotFoundError(f"Training dataset not found at {src_path}")

    df_train = pd.read_csv(src_path)
    if df_train.empty:
        raise ValueError("Training dataset is empty. Cannot train Isolation Forest.")

    # Validate feature presence (case-insensitive; the benchmark uses `pH`).
    column_map = _resolve_feature_columns(df_train, target_features)

    # Extract the feature matrix in canonical order and handle missing values.
    # Any extra columns (notably a `label`) are deliberately ignored: the
    # anomaly detector is unsupervised and must never read class labels.
    X = pd.DataFrame(
        {
            feature: pd.to_numeric(df_train[column_map[feature]], errors="coerce")
            for feature in target_features
        }
    )

    # Drop any rows with NaN in features to ensure safe training
    initial_len = len(X)
    X = X.dropna()
    if len(X) < initial_len:
        logger.warning(
            "Dropped %d rows containing missing/invalid feature values during training preparation",
            initial_len - len(X)
        )

    if X.empty:
        raise ValueError("No valid numeric feature records remaining for Isolation Forest training.")

    logger.info(
        "Fitting IsolationForest on %d samples using features %s (contamination=%s, random_state=%d)",
        len(X), target_features, str(contamination), random_state
    )

    model = IsolationForest(
        n_estimators=n_estimators,
        contamination=contamination,
        random_state=random_state,
        n_jobs=-1
    )
    model.fit(X)

    # Save model artifact
    joblib.dump(model, dest_path)
    logger.info("Successfully trained and saved Isolation Forest model to %s", dest_path)
    return model


def main():
    parser = argparse.ArgumentParser(description="Train Isolation Forest model for HydraSense telemetry.")
    parser.add_argument("--train-path", type=str, default=str(DEFAULT_TRAIN_PATH), help="Path to train.csv")
    parser.add_argument("--model-path", type=str, default=str(DEFAULT_MODEL_PATH), help="Target output model file")
    parser.add_argument("--contamination", type=float, default=DEFAULT_CONTAMINATION, help="Contamination parameter")
    parser.add_argument("--random-state", type=int, default=DEFAULT_RANDOM_STATE, help="Random seed")
    parser.add_argument("--n-estimators", type=int, default=100, help="Number of trees")
    args = parser.parse_args()

    train_isolation_forest(
        train_path=Path(args.train_path),
        model_path=Path(args.model_path),
        contamination=args.contamination,
        random_state=args.random_state,
        n_estimators=args.n_estimators
    )


if __name__ == "__main__":
    main()
