"""
Unit Test Suite for SAMUDRANETRA TASK011 — FastAPI Investigation API Endpoints.

Verifies HTTP 200 OK responses, JSON contracts, claim guards, and 404 error handling across all 13 endpoints.
"""

from fastapi.testclient import TestClient
import pytest

from backend.app.main import app

client = TestClient(app)
CASE_ID = "R001_WAKASHIO"


def test_list_cases_endpoint():
    """GET /api/cases"""
    resp = client.get("/api/cases")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert data[0]["case_id"] == "R001_WAKASHIO"
    assert data[0]["historical_attribution_valid"] is False


def test_get_unified_case_endpoint():
    """GET /api/cases/{case_id}"""
    resp = client.get(f"/api/cases/{CASE_ID}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["case_id"] == "R001_WAKASHIO"
    assert "sar" in data
    assert "physics" in data
    assert "ais" in data


def test_get_sar_evidence_endpoint():
    """GET /api/cases/{case_id}/sar"""
    resp = client.get(f"/api/cases/{CASE_ID}/sar")
    assert resp.status_code == 200
    data = resp.json()
    assert data["candidate_count"] == 8


def test_get_candidates_endpoint():
    """GET /api/cases/{case_id}/candidates"""
    resp = client.get(f"/api/cases/{CASE_ID}/candidates")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["selected_hypotheses"]) == 8


def test_get_hindcast_endpoint():
    """GET /api/cases/{case_id}/hindcast"""
    resp = client.get(f"/api/cases/{CASE_ID}/hindcast")
    assert resp.status_code == 200
    data = resp.json()
    assert data["hindcast_status"] == "PHYSICS_UNCERTAIN"


def test_get_source_regions_endpoint():
    """GET /api/cases/{case_id}/source-regions"""
    resp = client.get(f"/api/cases/{CASE_ID}/source-regions")
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "FeatureCollection"
    assert len(data["features"]) > 0


def test_get_forward_validation_endpoint():
    """GET /api/cases/{case_id}/forward-validation"""
    resp = client.get(f"/api/cases/{CASE_ID}/forward-validation")
    assert resp.status_code == 200
    data = resp.json()
    assert data["best_closure_candidate"] == "C3929"


def test_get_ais_summary_endpoint():
    """GET /api/cases/{case_id}/ais"""
    resp = client.get(f"/api/cases/{CASE_ID}/ais")
    assert resp.status_code == 200
    data = resp.json()
    assert data["data_mode"] == "SYNTHETIC_DEMO"
    assert data["historical_attribution_valid"] is False


def test_get_vessels_endpoint():
    """GET /api/cases/{case_id}/vessels"""
    resp = client.get(f"/api/cases/{CASE_ID}/vessels")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


def test_get_attribution_endpoint_with_claim_guard():
    """GET /api/cases/{case_id}/attribution"""
    resp = client.get(f"/api/cases/{CASE_ID}/attribution")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ais_data_mode"] == "SYNTHETIC_DEMO"
    assert data["historical_attribution_valid"] is False
    assert "Synthetic AIS demonstration" in data["presentation_guard"]


def test_get_evidence_fusion_endpoint():
    """GET /api/cases/{case_id}/evidence"""
    resp = client.get(f"/api/cases/{CASE_ID}/evidence")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 8


def test_get_provenance_endpoint():
    """GET /api/cases/{case_id}/provenance"""
    resp = client.get(f"/api/cases/{CASE_ID}/provenance")
    assert resp.status_code == 200
    data = resp.json()
    assert data["case_id"] == "R001_WAKASHIO"


def test_get_timeline_endpoint():
    """GET /api/cases/{case_id}/timeline"""
    resp = client.get(f"/api/cases/{CASE_ID}/timeline")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 5
    assert data[0]["step_id"] == "T-96"


def test_unknown_case_id_returns_404():
    """Verifies that requests for an unknown case_id return HTTP 404 Not Found."""
    resp = client.get("/api/cases/UNKNOWN_CASE_999")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()
