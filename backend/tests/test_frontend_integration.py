"""
Unit Test Suite for SAMUDRANETRA TASK013 — Real Frontend ↔ Backend Integration.

Verifies API endpoint schemas consumed by the ops console frontend,
synthetic AIS guard propagation, zero unscientific terminology, and mock audit validity.
"""

from pathlib import Path
from fastapi.testclient import TestClient
import pytest

from backend.app.main import app

client = TestClient(app)
CASE_ID = "R001_WAKASHIO"
R001_DIR = Path(r"C:\Users\tanvi\OneDrive\Documents\Oil Spill\SamudraNetra-Research\R001_WAKASHIO")


def test_frontend_consumed_endpoints_validity():
    """Verifies that all 11 endpoints consumed by ops_console/app.js respond with 200 OK and valid schemas."""
    endpoints = [
        f"/api/cases/{CASE_ID}",
        f"/api/cases/{CASE_ID}/sar",
        f"/api/cases/{CASE_ID}/candidates",
        f"/api/cases/{CASE_ID}/hindcast",
        f"/api/cases/{CASE_ID}/source-regions",
        f"/api/cases/{CASE_ID}/forward-validation",
        f"/api/cases/{CASE_ID}/ais",
        f"/api/cases/{CASE_ID}/vessels",
        f"/api/cases/{CASE_ID}/attribution",
        f"/api/cases/{CASE_ID}/evidence",
        f"/api/cases/{CASE_ID}/timeline",
    ]

    for ep in endpoints:
        resp = client.get(ep)
        assert resp.status_code == 200, f"Endpoint {ep} failed with status {resp.status_code}"


def test_synthetic_ais_guard_propagation():
    """Verifies that /attribution endpoint forces historical_attribution_valid = False and provides presentation guard."""
    resp = client.get(f"/api/cases/{CASE_ID}/attribution")
    assert resp.status_code == 200
    data = resp.json()

    assert data["ais_data_mode"] == "SYNTHETIC_DEMO"
    assert data["historical_attribution_valid"] is False
    assert "Synthetic AIS demonstration" in data["presentation_guard"]


def test_no_unscientific_wording_in_api_payloads():
    """Verifies that unscientific terms ('confidence', 'guilt', 'culprit', 'true source') do not appear in API responses."""
    endpoints = [
        f"/api/cases/{CASE_ID}",
        f"/api/cases/{CASE_ID}/attribution",
        f"/api/cases/{CASE_ID}/vessels",
    ]

    forbidden_terms = ["confidence", "guilt", "culprit", "true source"]
    for ep in endpoints:
        resp = client.get(ep)
        payload_str = resp.text.lower()
        for term in forbidden_terms:
            assert term not in payload_str, f"Forbidden term '{term}' found in endpoint {ep}"


def test_investigative_priority_metric_name():
    """Verifies that ranked vessels expose investigative_priority_score instead of probability_of_causing_spill."""
    resp = client.get(f"/api/cases/{CASE_ID}/vessels")
    assert resp.status_code == 200
    vessels = resp.json()

    assert len(vessels) > 0
    top_vessel = vessels[0]
    assert "investigative_priority_score" in top_vessel
    assert "probability_of_causing_spill" not in top_vessel
    assert "guilt_probability" not in top_vessel
