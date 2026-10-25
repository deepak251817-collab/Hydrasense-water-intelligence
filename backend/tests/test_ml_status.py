"""Tests for the ML transparency endpoint (model health + evaluation report).

Covered:
- authority-only access (401 without a token, 403 for product users);
- missing report -> evaluation null, no fabricated metrics;
- corrupt report -> treated as unavailable;
- present report -> returned verbatim (real metrics from the generator);
- no absolute filesystem paths or secrets in the response.
"""
import json
from pathlib import Path

import pytest

from app.services import ml_status_service


def _report() -> dict:
    return {
        "schema_version": "1.0",
        "generated_at": "2026-10-24T10:00:00+00:00",
        "generator": "ml/scripts/build_evaluation_report.py",
        "honesty_policy": "Metrics are computed from saved artifacts.",
        "random_forest": {
            "available": True,
            "metrics": {"n_samples": 100, "accuracy": 0.97, "f1_macro": 0.96},
        },
        "isolation_forest": {"available": True, "summary": {"anomaly_rate": 0.1}},
        "xgboost": {"available": False},
        "limitations": ["Model outputs are estimates, not laboratory results."],
    }


def test_ml_status_requires_authority(client):
    assert client.get("/api/authority/ml/status").status_code == 401


def test_ml_status_rejects_product_user(client, product_token_headers):
    res = client.get("/api/authority/ml/status", headers=product_token_headers)
    assert res.status_code == 403


def test_ml_status_without_report_is_explicitly_unavailable(
    client, authority_token_headers, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        ml_status_service, "EVALUATION_REPORT_PATH", tmp_path / "does-not-exist.json"
    )
    res = client.get("/api/authority/ml/status", headers=authority_token_headers)
    assert res.status_code == 200

    body = res.json()
    assert body["evaluation_available"] is False
    assert body["evaluation"] is None
    assert body["report"] is None
    assert body["generated_at"] is None

    # Model catalog is still described honestly (no metrics fabricated).
    assert {m["key"] for m in body["models"]} == {
        "isolation_forest",
        "random_forest",
        "xgboost",
    }
    for model in body["models"]:
        assert "/" not in model["file"] and "\\" not in model["file"]
        assert isinstance(model["loaded"], bool)
        assert isinstance(model["artifact_present"], bool)


def test_ml_status_returns_report_verbatim(
    client, authority_token_headers, tmp_path, monkeypatch
):
    report = _report()
    path = tmp_path / "evaluation_report.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    monkeypatch.setattr(ml_status_service, "EVALUATION_REPORT_PATH", path)

    res = client.get("/api/authority/ml/status", headers=authority_token_headers)
    assert res.status_code == 200
    body = res.json()
    assert body["evaluation_available"] is True
    assert body["report"] == "ml/reports/evaluation_report.json"
    assert body["generated_at"].startswith("2026-10-24T10:00:00")
    assert body["evaluation"]["random_forest"]["metrics"]["accuracy"] == 0.97
    assert body["evaluation"]["limitations"] == report["limitations"]


def test_ml_status_corrupt_report_is_unavailable(
    client, authority_token_headers, tmp_path, monkeypatch
):
    path = tmp_path / "evaluation_report.json"
    path.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setattr(ml_status_service, "EVALUATION_REPORT_PATH", path)

    res = client.get("/api/authority/ml/status", headers=authority_token_headers)
    assert res.status_code == 200
    body = res.json()
    assert body["evaluation_available"] is False
    assert body["evaluation"] is None


def test_ml_status_does_not_leak_filesystem_paths(
    client, authority_token_headers, tmp_path, monkeypatch
):
    report = _report()
    path = tmp_path / "evaluation_report.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    monkeypatch.setattr(ml_status_service, "EVALUATION_REPORT_PATH", path)

    res = client.get("/api/authority/ml/status", headers=authority_token_headers)
    text = res.text
    assert str(ml_status_service.PROJECT_ROOT) not in text
    assert "C:\\" not in text and "C:/" not in text
    # Model files are exposed by name only, never as paths.
    assert "ml/models" not in text and "ml\\models" not in text
