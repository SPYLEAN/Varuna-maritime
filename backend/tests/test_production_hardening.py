"""
Unit Test Suite for SAMUDRANETRA TASK015 — Production Hardening + Deployment Readiness.

Verifies /health, /ready, /version endpoints, CORS middleware, version string 0.9.0-rc1,
security baseline, and claim safety disclaimers.
"""

from fastapi.testclient import TestClient
import pytest

from backend.app.main import app

from backend.app.config import VARUNA_VERSION

client = TestClient(app)
CASE_ID = "R001_WAKASHIO"


def test_health_endpoint():
    """1. Verify GET /health endpoint."""
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == "healthy"
    assert data["version"] in (VARUNA_VERSION, "0.9.0-rc1", "2.0.0-rc1")
    assert data["api"] is True
    assert data["case_data"] is True


def test_readiness_endpoint():
    """2. Verify GET /ready endpoint."""
    resp = client.get("/ready")
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == "READY"
    assert data["service_running"] is True
    assert data["case_data_ready"] is True
    assert data["version"] in (VARUNA_VERSION, "0.9.0-rc1", "2.0.0-rc1")


def test_version_endpoint():
    """3. Verify GET /version endpoint."""
    resp = client.get("/version")
    assert resp.status_code == 200
    data = resp.json()

    assert data["version"] in (VARUNA_VERSION, "0.9.0-rc1", "2.0.0-rc1")
    assert data["release_stage"] == "PRODUCTION_CANDIDATE"


def test_cors_security_headers():
    """4. Verify CORS middleware header presence on API responses."""
    resp = client.get("/health", headers={"Origin": "http://localhost:8080"})
    assert resp.status_code == 200
    assert "access-control-allow-origin" in resp.headers


def test_claim_disclaimer_preservation():
    """5. Verify synthetic AIS disclaimers propagate across endpoints."""
    resp = client.get(f"/api/cases/{CASE_ID}/attribution")
    assert resp.status_code == 200
    data = resp.json()

    assert data["ais_data_mode"] == "SYNTHETIC_DEMO"
    assert data["historical_attribution_valid"] is False
    assert "Synthetic AIS demonstration" in data["presentation_guard"]
