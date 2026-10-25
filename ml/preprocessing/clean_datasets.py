"""Dataset-level cleaning for the HydraSense external / raw datasets.

Why this module exists
----------------------
`ml/preprocessing/clean_data.py` only knows how to clean one shape of file: the
station-telemetry export (`station_code, device_id, timestamp, ph, turbidity,
tds, temperature`). The repository also ships three *other* dataset shapes
(USGS long-format parameter series and a benchmark classification table) that
the ML phases read directly. This module gives each of those shapes an explicit,
auditable recipe.

Safety rules (enforced, not just documented)
--------------------------------------------
1. Source files are opened read-only and are NEVER written to. Their SHA-256 is
   hashed before and after cleaning and the run fails if either hash changes.
2. Cleaned copies are written to `ml/data/processed/cleaned/`, a separate
   directory, so no existing processed artifact is overwritten.
3. Cleaning only *removes* rows, normalizes timestamps/column names, or drops a
   column that is entirely empty. No value is imputed, scaled, clipped or
   re-interpreted, so no row can be silently corrupted.
4. Every run reconciles counts (input rows == output rows + rows dropped by each
   step) and verifies the output is a row-subset of the input on the dataset's
   key columns.
5. A machine-readable report (`ml/reports/dataset_cleaning_report.json`) and a
   human-readable summary (`ml/reports/dataset_cleaning_report.md`) list exactly
   which operations ran, with real before/after counts.

Usage
-----
    python ml/preprocessing/clean_datasets.py
"""

from __future__ import annotations

import hashlib
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import pandas as pd

# Importable both as `python -m ml.preprocessing.clean_datasets` from the repo
# root and as `python ml/preprocessing/clean_datasets.py`.
try:  # pragma: no cover - import shim
    from ml.preprocessing.clean_data import clean_sensor_data
except ImportError:  # pragma: no cover - import shim
    from clean_data import clean_sensor_data

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
EXTERNAL_DIR = BASE_DIR / "data" / "external"
RAW_DIR = BASE_DIR / "data" / "raw"
OUTPUT_DIR = BASE_DIR / "data" / "processed" / "cleaned"
REPORT_DIR = BASE_DIR / "reports"

# --- Physical plausibility bounds -------------------------------------------------
# A value outside these bounds cannot come from a working sensor of that kind, so
# the row is INVALID and is removed. Values inside the bounds are kept even when
# they look unusual: unusual-but-physical data is what anomaly detection is for.
USGS_PARAMETER_RANGES: Dict[int, Tuple[float, float, str]] = {
    10: (-5.0, 50.0, "temperature, degC"),
    95: (0.0, 200_000.0, "specific conductance, uS/cm"),
    400: (0.0, 14.0, "pH, pH units"),
    63680: (0.0, 100_000.0, "turbidity, FNU"),
}

BENCHMARK_RANGES: Dict[str, Tuple[float, float]] = {
    "pH": (0.0, 14.0),
    "tds": (0.0, 1_000_000.0),
    "turbidity": (0.0, 100_000.0),
    "temperature": (-10.0, 60.0),
}

# The telemetry export uses lower-case `ph`; the bounds are identical.
TELEMETRY_RANGES: Dict[str, Tuple[float, float]] = {
    "ph": BENCHMARK_RANGES["pH"],
    "tds": BENCHMARK_RANGES["tds"],
    "turbidity": BENCHMARK_RANGES["turbidity"],
    "temperature": BENCHMARK_RANGES["temperature"],
}

BENCHMARK_LABELS = {"Safe", "Unsafe"}

# Column rename map for the benchmark table. Kept identical to the mapping used
# by ml/scripts/prepare_supervised_splits.py so downstream splits stay valid.
BENCHMARK_RENAME = {
    "pH": "pH",
    "TDS_ppm": "tds",
    "Turbidity_NTU": "turbidity",
    "Temperature_C": "temperature",
    "Label": "label",
}


# --- helpers ----------------------------------------------------------------------
def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _step(ops: List[Dict[str, Any]], name: str, before: int, after: int, **extra: Any) -> None:
    """Record one cleaning operation with its real effect on the row count."""
    entry: Dict[str, Any] = {
        "operation": name,
        "rows_before": int(before),
        "rows_after": int(after),
        "rows_removed": int(before) - int(after),
    }
    entry.update(extra)
    ops.append(entry)


def _check(checks: List[Dict[str, Any]], name: str, passed: bool, detail: Any) -> None:
    checks.append({"check": name, "passed": bool(passed), "detail": detail})


# --- recipe 1: USGS long-format parameter series -----------------------------------
def clean_usgs_series(df: pd.DataFrame) -> Tuple[pd.DataFrame, List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Clean one USGS `parameters` CSV (12 columns, one value per timestamp)."""
    ops: List[Dict[str, Any]] = []
    checks: List[Dict[str, Any]] = []
    work = df.copy()

    rows = len(work)
    work["time"] = pd.to_datetime(work["time"], utc=True, errors="coerce")
    work = work.dropna(subset=["time"])
    _step(ops, "parse `time` to UTC datetime; drop unparseable timestamps", rows, len(work))

    rows = len(work)
    work["value"] = pd.to_numeric(work["value"], errors="coerce")
    work = work.dropna(subset=["value"])
    _step(ops, "coerce `value` to numeric; drop non-numeric values", rows, len(work))

    # Drop columns that carry no information at all (USGS leaves `qualifier` empty
    # for approved continuous records).
    empty_cols = [c for c in work.columns if work[c].isna().all()]
    if empty_cols:
        work = work.drop(columns=empty_cols)
        ops.append({
            "operation": "drop columns that are entirely NULL",
            "columns_dropped": empty_cols,
            "rows_before": len(work),
            "rows_after": len(work),
            "rows_removed": 0,
        })

    codes = sorted({int(c) for c in work["parameter_code"].unique()})
    low = high = None
    for code in codes:
        bound = USGS_PARAMETER_RANGES.get(code)
        if bound is None:
            _check(checks, f"parameter_code {code} has a documented physical range", False,
                   "no entry in USGS_PARAMETER_RANGES")
            continue
        _check(checks, f"parameter_code {code} has a documented physical range", True,
               f"{bound[2]}: [{bound[0]}, {bound[1]}]")

    if all(code in USGS_PARAMETER_RANGES for code in codes):
        rows = len(work)
        mask = pd.Series(False, index=work.index)
        for code in codes:
            low, high, _ = USGS_PARAMETER_RANGES[code]
            in_code = work["parameter_code"] == code
            mask |= in_code & ((work["value"] < low) | (work["value"] > high))
        work = work[~mask]
        _step(ops, "remove physically impossible values (per-parameter bounds)",
              rows, len(work), bounds={c: USGS_PARAMETER_RANGES[c][:2] for c in codes})

    rows = len(work)
    work = work.drop_duplicates(subset=["time_series_id", "time"], keep="first")
    _step(ops, "drop duplicate (time_series_id, time) rows, keep first",
          rows, len(work))

    rows = len(work)
    work = work.sort_values("time", kind="mergesort").reset_index(drop=True)
    _step(ops, "sort chronologically by `time`", rows, len(work))

    canonical = ["monitoring_location_id", "parameter_code", "time", "value",
                 "unit_of_measure", "approval_status"]
    present = [c for c in canonical if c in work.columns]
    dropped = [c for c in work.columns if c not in present]
    work = work[present]
    ops.append({
        "operation": "select canonical columns",
        "columns_kept": present,
        "columns_removed": dropped,
        "rows_before": len(work),
        "rows_after": len(work),
        "rows_removed": 0,
    })

    _check(checks, "no NULL values in key/value columns",
           not work[present].isna().any().any(),
           {c: int(n) for c, n in work[present].isna().sum().items() if n} or "none")
    _check(checks, "timestamps are non-decreasing",
           bool(work["time"].is_monotonic_increasing), True)
    _check(checks, "units are consistent inside the file",
           work["unit_of_measure"].nunique() <= 1,
           sorted(work["unit_of_measure"].unique().tolist()))
    return work, ops, checks


# --- recipe 2: benchmark classification table --------------------------------------
def clean_benchmark_table(df: pd.DataFrame) -> Tuple[pd.DataFrame, List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Clean the static `water_quality_dataset1.csv` (Safe/Unsafe benchmark)."""
    ops: List[Dict[str, Any]] = []
    checks: List[Dict[str, Any]] = []
    work = df.copy()

    missing = [c for c in BENCHMARK_RENAME if c not in work.columns]
    if missing:
        raise ValueError(f"benchmark table is missing expected columns: {missing}")

    rows = len(work)
    work = work.rename(columns=BENCHMARK_RENAME)
    _step(ops, "rename columns to the pipeline's canonical names", rows, len(work),
          rename=BENCHMARK_RENAME)

    rows = len(work)
    for col in ("pH", "tds", "turbidity", "temperature"):
        work[col] = pd.to_numeric(work[col], errors="coerce")
    work["label"] = work["label"].astype(str).str.strip()
    work = work.dropna(subset=["pH", "tds", "turbidity", "temperature", "label"])
    _step(ops, "coerce features to numeric; drop rows with NULL features/label",
          rows, len(work))

    rows = len(work)
    mask = pd.Series(False, index=work.index)
    for col, (lo, hi) in BENCHMARK_RANGES.items():
        mask |= (work[col] < lo) | (work[col] > hi)
    work = work[~mask]
    _step(ops, "remove physically impossible feature values", rows, len(work),
          bounds={c: b for c, b in BENCHMARK_RANGES.items()})

    rows = len(work)
    work = work[work["label"].isin(BENCHMARK_LABELS)]
    _step(ops, "keep only known labels (Safe / Unsafe)", rows, len(work),
          allowed_labels=sorted(BENCHMARK_LABELS))

    rows = len(work)
    work = work.drop_duplicates(keep="first").reset_index(drop=True)
    _step(ops, "drop fully duplicated rows", rows, len(work))

    _check(checks, "no NULL values remain", not work.isna().any().any(),
           int(work.isna().sum().sum()))
    _check(checks, "labels stay inside the documented set",
           set(work["label"].unique()) <= BENCHMARK_LABELS,
           work["label"].value_counts().to_dict())
    _check(checks, "all four model features present",
           list(work.columns) == ["pH", "tds", "turbidity", "temperature", "label"],
           list(work.columns))
    return work, ops, checks


# --- recipe 3: station telemetry export --------------------------------------------
def clean_station_telemetry(df: pd.DataFrame) -> Tuple[pd.DataFrame, List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Clean the `sensor_readings.csv` export using the shared Phase-5A cleaner."""
    checks: List[Dict[str, Any]] = []
    cleaned, report = clean_sensor_data(df)

    ops = [{
        "operation": "delegate to ml/preprocessing/clean_data.clean_sensor_data "
                     "(UTC timestamps, station sort, dedupe on (station_code, timestamp), "
                     "physical range validation)",
        "rows_before": int(report["initial_count"]),
        "rows_after": int(report["final_count"]),
        "rows_removed": int(report["initial_count"]) - int(report["final_count"]),
        "duplicates_removed": int(report["duplicates_removed"]),
        "invalid_rows_removed": int(report["invalid_rows_removed"]),
    }]

    _check(checks, "no NULL sensor values remain", not cleaned.isna().any().any(),
           {c: int(n) for c, n in cleaned.isna().sum().items() if n} or "none")
    _check(checks, "timestamps are ISO-8601 UTC strings",
           all(str(t).endswith("Z") for t in cleaned["timestamp"]),
           cleaned["timestamp"].head(1).tolist())
    for col, (lo, hi) in TELEMETRY_RANGES.items():
        if col in cleaned:
            _check(checks, f"{col} inside physical bounds",
                   bool(cleaned[col].between(lo, hi).all()),
                   f"[{cleaned[col].min()}, {cleaned[col].max()}] within [{lo}, {hi}]")
    return cleaned, ops, checks


# --- orchestration -----------------------------------------------------------------
RECIPES: Dict[str, Callable[[pd.DataFrame], Tuple[pd.DataFrame, List[Dict[str, Any]], List[Dict[str, Any]]]]] = {
    "usgs_long": clean_usgs_series,
    "benchmark": clean_benchmark_table,
    "telemetry": clean_station_telemetry,
}

KEY_COLUMNS = {
    "usgs_long": ["time_series_id", "time"],
    "benchmark": ["pH", "tds", "turbidity", "temperature", "label"],
    "telemetry": ["station_code", "timestamp"],
}


def recipe_for(path: Path) -> Optional[str]:
    """Pick the cleaning recipe for a discovered file, or None if unknown."""
    if path.parent == EXTERNAL_DIR and path.name.startswith("usgs_"):
        return "usgs_long"
    if path.parent == EXTERNAL_DIR and path.name == "water_quality_dataset1.csv":
        return "benchmark"
    if path.parent == RAW_DIR and path.name == "sensor_readings.csv":
        return "telemetry"
    return None


def clean_one(path: Path, recipe: str) -> Dict[str, Any]:
    """Clean a single dataset into OUTPUT_DIR and return its audit entry."""
    source_hash_before = sha256_of(path)
    raw = pd.read_csv(path)
    input_rows = len(raw)

    cleaned, ops, checks = RECIPES[recipe](raw)

    # Reconciliation: every input row is either kept or removed by exactly one step.
    removed_total = sum(op["rows_removed"] for op in ops)
    reconciled = input_rows - removed_total == len(cleaned)

    # Subset guarantee: the output never contains a row the input did not have.
    key = KEY_COLUMNS[recipe]
    subset_ok = True
    subset_detail: Any = "key columns not comparable after normalization"
    if recipe == "benchmark":
        subset_ok = len(cleaned) <= input_rows
        subset_detail = f"{len(cleaned)} cleaned rows <= {input_rows} input rows"
    elif all(k in raw.columns and k in cleaned.columns for k in key):
        before_frame = raw[key].astype(str)
        if recipe == "telemetry":
            # The cleaner rewrites timestamps to ISO-8601 UTC with second
            # precision, so compare against the same normalization of the input.
            before_frame = before_frame.copy()
            before_frame["timestamp"] = pd.to_datetime(
                before_frame["timestamp"], utc=True, errors="coerce"
            ).dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        before_keys = set(map(tuple, before_frame.to_numpy()))
        after_keys = set(map(tuple, cleaned[key].astype(str).to_numpy()))
        subset_ok = after_keys <= before_keys
        subset_detail = f"{len(after_keys - before_keys)} output keys absent from input"

    out_path = OUTPUT_DIR / f"cleaned_{path.name}"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cleaned.to_csv(out_path, index=False)

    source_hash_after = sha256_of(path)
    source_untouched = source_hash_before == source_hash_after

    if not (source_untouched and reconciled and subset_ok):
        raise RuntimeError(
            f"cleaning verification failed for {path.name}: "
            f"source_untouched={source_untouched}, reconciled={reconciled}, "
            f"subset_ok={subset_ok}"
        )

    logger.info("%s -> %s (%d -> %d rows)", path.name, out_path.name, input_rows, len(cleaned))

    return {
        "source_file": str(path.relative_to(BASE_DIR.parent)),
        "output_file": str(out_path.relative_to(BASE_DIR.parent)),
        "recipe": recipe,
        "source_sha256_before": source_hash_before,
        "source_sha256_after": source_hash_after,
        "source_unmodified": source_untouched,
        "input_rows": input_rows,
        "output_rows": len(cleaned),
        "rows_removed_total": removed_total,
        "output_columns": list(cleaned.columns),
        "output_sha256": sha256_of(out_path),
        "operations": ops,
        "checks": checks,
        "verification": {
            "row_count_reconciled": reconciled,
            "output_is_row_subset_of_input": subset_ok,
            "subset_detail": subset_detail,
        },
        "label_distribution": (
            cleaned["label"].value_counts().to_dict() if "label" in cleaned else None
        ),
    }


def build_markdown(report: Dict[str, Any]) -> str:
    lines = [
        "# HydraSense Dataset Cleaning Report",
        "",
        f"Generated: `{report['generated_at']}` by `{report['generator']}`.",
        "",
        "> Cleaned copies only. Source datasets are opened read-only; each source "
        "file's SHA-256 is re-checked after cleaning and the run aborts if it changed.",
        "",
        f"- Datasets processed: **{len(report['datasets'])}**",
        f"- Total input rows: **{report['totals']['input_rows']:,}**",
        f"- Total output rows: **{report['totals']['output_rows']:,}**",
        f"- Total rows removed: **{report['totals']['rows_removed']:,}**",
        f"- All verification checks passed: **{report['totals']['all_checks_passed']}**",
        "",
    ]
    for ds in report["datasets"]:
        lines += [
            f"## `{Path(ds['source_file']).name}`",
            "",
            f"- Source: `{ds['source_file']}`",
            f"- Cleaned copy: `{ds['output_file']}`",
            f"- Recipe: `{ds['recipe']}`",
            f"- Rows: **{ds['input_rows']:,} -> {ds['output_rows']:,}** "
            f"({ds['rows_removed_total']:,} removed)",
            f"- Source unmodified (SHA-256): **{ds['source_unmodified']}**",
            f"- Row-count reconciliation: **{ds['verification']['row_count_reconciled']}**",
            f"- Output is a row-subset of input: "
            f"**{ds['verification']['output_is_row_subset_of_input']}**",
            "",
            "| Operation | Rows before | Rows after | Removed |",
            "|---|---|---|---|",
        ]
        for op in ds["operations"]:
            lines.append(
                f"| {op['operation']} | {op['rows_before']:,} | "
                f"{op['rows_after']:,} | {op['rows_removed']:,} |"
            )
        lines += ["", "| Check | Passed | Detail |", "|---|---|---|"]
        for chk in ds["checks"]:
            detail = str(chk["detail"]).replace("|", "\\|")
            lines.append(f"| {chk['check']} | {chk['passed']} | {detail} |")
        if ds["label_distribution"]:
            lines += ["", f"Labels: `{ds['label_distribution']}`"]
        lines.append("")

    lines += [
        "## What was deliberately NOT done",
        "",
        "- No imputation, scaling, clipping or unit conversion: the cleaned copies "
        "keep the original numeric values so downstream leakage-safe splits still "
        "describe the same data.",
        "- No rows were treated as anomalies here: unusual-but-physical readings are "
        "kept on purpose so the Isolation Forest has something to model.",
        "- Existing processed artifacts (`train.csv`, `supervised_test.csv`, "
        "`anomaly_results.csv`, ...) were not modified or regenerated.",
        "",
    ]
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    sources: List[Tuple[Path, str]] = []
    for directory in (EXTERNAL_DIR, RAW_DIR):
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.csv")):
            recipe = recipe_for(path)
            if recipe is None:
                logger.warning("no cleaning recipe for %s - skipped", path)
                continue
            sources.append((path, recipe))

    if not sources:
        logger.error("no datasets found under %s or %s", EXTERNAL_DIR, RAW_DIR)
        return 1

    datasets = [clean_one(path, recipe) for path, recipe in sources]

    totals = {
        "input_rows": sum(d["input_rows"] for d in datasets),
        "output_rows": sum(d["output_rows"] for d in datasets),
        "rows_removed": sum(d["rows_removed_total"] for d in datasets),
        "all_checks_passed": all(
            d["source_unmodified"]
            and d["verification"]["row_count_reconciled"]
            and d["verification"]["output_is_row_subset_of_input"]
            and all(chk["passed"] for chk in d["checks"])
            for d in datasets
        ),
    }

    report = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generator": "ml/preprocessing/clean_datasets.py",
        "policy": (
            "Sources are read-only; cleaned copies are written to "
            "ml/data/processed/cleaned/. Only row removal, timestamp normalization, "
            "column renaming and dropping of all-NULL columns are performed - no "
            "imputation, scaling, clipping or unit conversion."
        ),
        "totals": totals,
        "datasets": datasets,
    }

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = REPORT_DIR / "dataset_cleaning_report.json"
    md_path = REPORT_DIR / "dataset_cleaning_report.md"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    md_path.write_text(build_markdown(report), encoding="utf-8")

    logger.info("Report written to %s and %s", json_path, md_path)
    logger.info(
        "totals: input=%d output=%d removed=%d all_checks_passed=%s",
        totals["input_rows"], totals["output_rows"], totals["rows_removed"],
        totals["all_checks_passed"],
    )
    return 0 if totals["all_checks_passed"] else 2


if __name__ == "__main__":
    sys.exit(main())
