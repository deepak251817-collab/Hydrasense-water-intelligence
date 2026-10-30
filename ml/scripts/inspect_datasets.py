"""Measured inspection of every external dataset used by the ML pipeline.

Reports, per file: column names, row count, duplicate rows, missing values,
value ranges, label balance, station/time coverage and units. Provenance and
licence are reported only when the repository actually documents them; when it
does not, the report says **unable to verify** instead of assuming a licence.

Outputs:
    ml/reports/dataset_inspection.json
    ml/reports/dataset_inspection.md

Run:  python ml/scripts/inspect_datasets.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
EXTERNAL_DIR = PROJECT_ROOT / "ml" / "data" / "external"
REPORTS_DIR = PROJECT_ROOT / "ml" / "reports"

import pandas as pd

BENCHMARK_FILE = "water_quality_dataset1.csv"
USGS_SPECS = {
    "usgs_ph_2024.csv": {"parameter": "pH", "unit": "pH Units", "code": "00400"},
    "usgs_conductance_2024.csv": {
        "parameter": "specific conductance (NOT TDS)",
        "unit": "uS/cm",
        "code": "00095",
    },
    "usgs_temperature_2024.csv": {"parameter": "temperature", "unit": "degC", "code": "00010"},
    "usgs_turbidity_2024.csv": {"parameter": "turbidity", "unit": "FNU (NTU-equivalent unit)", "code": "63680"},
}

PROVENANCE_UNKNOWN = (
    "Not documented in this repository. The source, access date and licence must "
    "be confirmed before redistribution or publication (unable to verify)."
)


def _basic_frame_stats(df: pd.DataFrame) -> dict[str, Any]:
    missing = {column: int(df[column].isna().sum()) for column in df.columns}
    all_null = sorted(column for column, count in missing.items() if count == len(df))
    return {
        "rows": int(len(df)),
        "columns": [str(column) for column in df.columns],
        "duplicate_rows": int(df.duplicated().sum()),
        "missing_values": missing,
        "missing_values_total": int(sum(missing.values())),
        "all_null_optional_columns": all_null,
    }


def inspect_benchmark(path: Path) -> dict[str, Any]:
    df = pd.read_csv(path)
    stats = _basic_frame_stats(df)
    label_counts = (
        {str(k): int(v) for k, v in df["Label"].value_counts().items()}
        if "Label" in df.columns
        else {}
    )
    total = sum(label_counts.values()) or 1
    ranges = {
        column: {
            "min": float(pd.to_numeric(df[column], errors="coerce").min()),
            "max": float(pd.to_numeric(df[column], errors="coerce").max()),
            "mean": float(pd.to_numeric(df[column], errors="coerce").mean()),
        }
        for column in ("pH", "TDS_ppm", "Turbidity_NTU", "Temperature_C")
        if column in df.columns
    }
    return {
        "file": BENCHMARK_FILE,
        "kind": "static classification benchmark",
        "rows": stats["rows"],
        "columns": stats["columns"],
        "units": {
            "pH": "pH units",
            "TDS_ppm": "mg/L (ppm), NaCl-equivalent scale as distributed",
            "Turbidity_NTU": "NTU (laboratory-style turbidity unit — NOT the hardware index)",
            "Temperature_C": "°C",
        },
        "duplicate_rows": stats["duplicate_rows"],
        "missing_values_total": stats["missing_values_total"],
        "missing_values": stats["missing_values"],
        "labels": label_counts,
        "class_balance": {
            label: round(count / total, 4) for label, count in label_counts.items()
        },
        "feature_ranges": ranges,
        "time_axis": None,
        "station_axis": None,
        "provenance": PROVENANCE_UNKNOWN,
        "fitness_for_project": (
            "Used only to bootstrap/benchmark the anomaly and Safe/Unsafe models on "
            "matching pH/TDS/turbidity/temperature units. Its NTU turbidity is NOT "
            "fed from the ESP32 relative index, and its labels never define suitability."
        ),
    }


def inspect_usgs(path: Path) -> dict[str, Any]:
    # Parameter codes are zero-padded identifiers (e.g. 00095), not numbers.
    df = pd.read_csv(path, dtype={"parameter_code": str})
    stats = _basic_frame_stats(df)
    times = pd.to_datetime(df["time"], errors="coerce", utc=True)
    values = pd.to_numeric(df["value"], errors="coerce")
    key_columns = [
        column for column in ("time", "value", "monitoring_location_id", "parameter_code")
        if column in df.columns
    ]
    missing_key_values = int(df[key_columns].isna().sum().sum()) if key_columns else None
    return {
        "file": path.name,
        "kind": "USGS time series (long format)",
        "rows": stats["rows"],
        "columns": stats["columns"],
        "units": (
            df["unit_of_measure"].dropna().astype(str).unique().tolist()
            if "unit_of_measure" in df.columns
            else []
        ),
        "parameters": (
            df["parameter_code"].dropna().astype(str).unique().tolist()
            if "parameter_code" in df.columns
            else []
        ),
        "stations": (
            df["monitoring_location_id"].dropna().astype(str).unique().tolist()
            if "monitoring_location_id" in df.columns
            else []
        ),
        "time_range": {
            "start": times.min().isoformat() if times.notna().any() else None,
            "end": times.max().isoformat() if times.notna().any() else None,
        },
        "value_range": {
            "min": float(values.min()) if values.notna().any() else None,
            "max": float(values.max()) if values.notna().any() else None,
        },
        "duplicate_rows": stats["duplicate_rows"],
        "missing_values_total": stats["missing_values_total"],
        "missing_values": stats["missing_values"],
        "missing_key_values": missing_key_values,
        "all_null_optional_columns": stats["all_null_optional_columns"],
        "approval_status": (
            df["approval_status"].dropna().astype(str).value_counts().to_dict()
            if "approval_status" in df.columns
            else {}
        ),
        "provenance": (
            "USGS Water Data for the Nation export (station USGS-01649190, 2024). "
            "USGS data are public-domain U.S. Government works; retain the USGS "
            "attribution when redistributing."
        ),
        "fitness_for_project": (
            "Used for chronological forecasting/deterioration research only. "
            "Specific conductance is kept distinct from TDS and is never converted "
            "or renamed."
        ),
    }


def build_report() -> dict[str, Any]:
    datasets = []
    benchmark = EXTERNAL_DIR / BENCHMARK_FILE
    if benchmark.exists():
        datasets.append(inspect_benchmark(benchmark))
    for filename in USGS_SPECS:
        path = EXTERNAL_DIR / filename
        if path.exists():
            datasets.append(inspect_usgs(path))

    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generator": "ml/scripts/inspect_datasets.py",
        "policy": (
            "All figures are measured from the files at generation time. Licence and "
            "provenance are reported only when documented; otherwise the report says "
            "unable to verify."
        ),
        "datasets": datasets,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# HydraSense dataset inspection",
        "",
        f"Generated: `{report['generated_at']}` by `{report['generator']}`.",
        "",
        "> Every figure below is measured from the source files. Licence/provenance is "
        "reported only where documented; otherwise it says **unable to verify**.",
        "",
    ]
    for dataset in report["datasets"]:
        lines += [f"## `{dataset['file']}`", ""]
        lines.append(f"- Kind: {dataset['kind']}")
        lines.append(f"- Rows: **{dataset['rows']:,}**")
        lines.append(f"- Columns: `{', '.join(dataset['columns'])}`")
        lines.append(f"- Duplicate rows: **{dataset['duplicate_rows']:,}**")
        if dataset.get("missing_key_values") is not None:
            lines.append(
                f"- Missing key values (time/value/station/parameter): "
                f"**{dataset['missing_key_values']:,}**"
            )
        optional = dataset.get("all_null_optional_columns") or []
        lines.append(
            f"- Empty optional columns: `{', '.join(optional)}`"
            if optional
            else "- Empty optional columns: none"
        )
        lines.append(
            f"- Missing values across all columns: **{dataset['missing_values_total']:,}**"
        )
        if dataset["units"]:
            units = dataset["units"]
            if isinstance(units, dict):
                for column, unit in units.items():
                    lines.append(f"- Unit — `{column}`: {unit}")
            else:
                lines.append(f"- Units: {', '.join(units)}")
        if dataset.get("labels"):
            lines.append(f"- Labels: `{dataset['labels']}`")
            lines.append(f"- Class balance: `{dataset['class_balance']}`")
        if dataset.get("feature_ranges"):
            lines.append(
                "- Feature ranges: "
                + "; ".join(
                    f"{column} {ranges['min']:g}–{ranges['max']:g}"
                    for column, ranges in dataset["feature_ranges"].items()
                )
            )
        if dataset.get("time_range"):
            lines.append(
                f"- Time range: {dataset['time_range']['start']} → {dataset['time_range']['end']}"
            )
        if dataset.get("stations"):
            lines.append(f"- Stations: {', '.join(dataset['stations'])}")
        if dataset.get("parameters"):
            lines.append(f"- Parameter codes: {', '.join(dataset['parameters'])}")
        if dataset.get("approval_status"):
            lines.append(f"- Approval status: `{dataset['approval_status']}`")
        lines += [
            f"- Provenance: {dataset['provenance']}",
            f"- Use in this project: {dataset['fitness_for_project']}",
            "",
        ]
    lines += [
        "## Not used for suitability",
        "",
        "No dataset here changes a suitability verdict: suitability is rule-based on the "
        "four live sensor values and the configured threshold profile. These datasets are "
        "used for model benchmarking/research only.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report = build_report()
    (REPORTS_DIR / "dataset_inspection.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    (REPORTS_DIR / "dataset_inspection.md").write_text(
        render_markdown(report), encoding="utf-8"
    )
    print(f"Inspected {len(report['datasets'])} datasets.")
    for dataset in report["datasets"]:
        missing = dataset.get("missing_key_values")
        missing_text = (
            f"{missing} missing key values"
            if missing is not None
            else f"{dataset['missing_values_total']} missing values"
        )
        print(
            f"  - {dataset['file']}: {dataset['rows']:,} rows, "
            f"{dataset['duplicate_rows']} duplicates, {missing_text}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
