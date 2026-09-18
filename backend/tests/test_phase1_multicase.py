"""
Test Suite for VARUNA Phase 1 — Genuine Multi-Case Core + R001 Isolation.

Verifies:
1. Product API v1 routes (/api/v1/cases, evidence, analysis)
2. Case #2 creation with full GeoJSON AOI and metadata
3. Persistence across storage reload
4. Zero-leakage contract: Case #2 contains NO R001 / Wakashio / C4053 / Mauritius / VESSEL_BETA
5. Case #2 clean empty analysis and manifest state
6. Generic evidence upload with SHA-256 provenance
7. Generic oil detection requires SAR evidence
8. Legacy benchmark endpoint strictly rejects generic cases (BENCHMARK_ENDPOINT_NOT_AVAILABLE_FOR_GENERIC_CASE)
9. R001 benchmark remains fully available on benchmark endpoint
"""

import io
import json
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.storage import storage, JSONCaseStorage

client = TestClient(app)


@pytest.fixture(autouse=True)
def temp_storage(tmp_path):
    """Isolate case storage in temporary directory during test execution."""
    original_dir = storage.storage_dir
    storage.storage_dir = tmp_path / "cases"
    storage.storage_dir.mkdir(parents=True, exist_ok=True)
    yield
    storage.storage_dir = original_dir


def test_product_api_v1_routes():
    """1. Verify that /api/v1/cases product routes are mounted and functional."""
    payload = {
        "name": "API v1 Verification Case",
        "description": "Verifying product API v1 namespace",
        "region": "Bay of Bengal",
        "incident_type": "Routine Surveillance",
        "priority": "NORMAL",
        "tags": ["v1", "test"],
    }
    resp = client.post("/api/v1/cases", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert "case_id" in data
    c_id = data["case_id"]

    # Verify GET /api/v1/cases
    list_resp = client.get("/api/v1/cases")
    assert list_resp.status_code == 200
    cases_list = list_resp.json()
    assert any(c["case_id"] == c_id for c in cases_list)

    # Verify GET /api/v1/cases/{id}
    get_resp = client.get(f"/api/v1/cases/{c_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["name"] == payload["name"]

    # Verify GET /api/v1/cases/{id}/evidence
    ev_resp = client.get(f"/api/v1/cases/{c_id}/evidence")
    assert ev_resp.status_code == 200
    assert isinstance(ev_resp.json(), list)


def test_create_second_case():
    """2. Verify creating Case #2 persists metadata, region, priority, and real GeoJSON AOI."""
    aoi_polygon = {
        "type": "Polygon",
        "coordinates": [
            [
                [68.50, 20.80],
                [70.00, 20.80],
                [70.00, 22.00],
                [68.50, 22.00],
                [68.50, 20.80],
            ]
        ],
    }
    payload = {
        "name": "TEST CASE 2 — Arabian Sea Incident",
        "description": "Observed dark anomaly off Gujarat coast",
        "observation_timestamp": "2026-09-18T12:00:00Z",
        "latitude": 21.40,
        "longitude": 69.25,
        "region": "Arabian Sea (Gujarat Coast)",
        "incident_type": "Operational Oil Spill",
        "priority": "HIGH",
        "source": "Sentinel-1A SAR pass",
        "tags": ["arabian-sea", "gujarat", "urgent"],
        "aoi_geojson": aoi_polygon,
    }

    resp = client.post("/api/v1/cases", json=payload)
    assert resp.status_code == 201
    c2 = resp.json()

    assert c2["case_id"].startswith("case_")
    assert c2["name"] == payload["name"]
    assert c2["region"] == "Arabian Sea (Gujarat Coast)"
    assert c2["incident_type"] == "Operational Oil Spill"
    assert c2["priority"] == "HIGH"
    assert c2["latitude"] == 21.40
    assert c2["longitude"] == 69.25
    assert c2["aoi_geojson"] == aoi_polygon


def test_case_persists_after_storage_reload():
    """3. Verify Case #2 persists to disk and reloads cleanly into a fresh JSONCaseStorage instance."""
    payload = {
        "name": "Persistence Verification Case",
        "region": "Gulf of Kutch",
        "priority": "NORMAL",
        "aoi_geojson": {
            "type": "Polygon",
            "coordinates": [[[69.0, 22.0], [70.0, 22.0], [70.0, 23.0], [69.0, 23.0], [69.0, 22.0]]],
        },
    }
    resp = client.post("/api/v1/cases", json=payload)
    assert resp.status_code == 201
    case_id = resp.json()["case_id"]

    # Re-instantiate storage directly pointing to the same directory
    reloaded_storage = JSONCaseStorage(storage.storage_dir)
    reloaded_case = reloaded_storage.get_case(case_id)

    assert reloaded_case is not None
    assert reloaded_case["case_id"] == case_id
    assert reloaded_case["name"] == payload["name"]
    assert reloaded_case["region"] == payload["region"]
    assert reloaded_case["aoi_geojson"] == payload["aoi_geojson"]


def test_case2_has_no_r001_metadata():
    """4. Zero-Leakage Contract: Case #2 must contain NO R001, Wakashio, C4053, Mauritius, or VESSEL_BETA."""
    payload = {
        "name": "TEST CASE 2 — Independent Incident",
        "region": "Lakshadweep Waters",
        "incident_type": "Operational Oil Spill",
    }
    resp = client.post("/api/v1/cases", json=payload)
    assert resp.status_code == 201
    case_id = resp.json()["case_id"]

    get_resp = client.get(f"/api/v1/cases/{case_id}")
    raw_text = json.dumps(get_resp.json()).upper()

    forbidden_terms = ["R001", "WAKASHIO", "C4053", "MAURITIUS", "2020-08-10", "VESSEL_BETA", "0.5818", "0.907"]
    for term in forbidden_terms:
        assert term not in raw_text, f"Zero-leakage violation: forbidden term '{term}' found in Case #2 data."


def test_case2_has_no_r001_analysis():
    """5. Zero-Leakage Contract: Case #2 must initialize with unstarted analysis status and empty manifests."""
    resp = client.post("/api/v1/cases", json={"name": "TEST CASE 2 — Empty State Audit"})
    assert resp.status_code == 201
    c = resp.json()

    # Analysis Status must be not_started
    status_map = c["analysis_status"]
    assert status_map["oil_detection"] == "not_started"
    assert status_map["spill_geometry"] == "not_started"
    assert status_map["hindcast"] == "not_started"
    assert status_map["ais_correlation"] == "not_started"
    assert status_map["attribution"] == "not_started"

    # Data Manifest must be completely empty
    manifest = c["data_manifest"]
    assert manifest["satellite_imagery"] == []
    assert manifest["oil_masks"] == []
    assert manifest["ais_data"] == []
    assert manifest["met_ocean_data"] == []
    assert manifest["research_notes"] == []
    assert manifest["evidence"] == []
    assert manifest["generated_analysis_results"] == []


def test_generic_evidence_upload():
    """6. Verify genuine generic evidence upload into Case #2 with cryptographic SHA-256 provenance."""
    resp = client.post("/api/v1/cases", json={"name": "Evidence Test Case"})
    assert resp.status_code == 201
    case_id = resp.json()["case_id"]

    fake_raster_bytes = b"GENUINE_SAR_TIFF_BINARY_PAYLOAD_SAMPLE_987654321"
    files = {"file": ("scene_vv.tif", fake_raster_bytes, "image/tiff")}
    data = {
        "evidence_type": "sar_image",
        "source": "Sentinel-1A IW GRDH",
        "acquisition_timestamp": "2026-09-18T06:00:00Z",
    }

    up_resp = client.post(f"/api/v1/cases/{case_id}/evidence", files=files, data=data)
    assert up_resp.status_code == 201
    ev = up_resp.json()

    assert ev["evidence_id"].startswith("ev_")
    assert ev["case_id"] == case_id
    assert ev["evidence_type"] == "sar_image"
    assert ev["file_size"] == len(fake_raster_bytes)
    assert len(ev["sha256"]) == 64  # valid sha256 hex string

    # Verify evidence item is in case manifest
    c_resp = client.get(f"/api/v1/cases/{case_id}")
    manifest_evidence = c_resp.json()["data_manifest"]["evidence"]
    assert len(manifest_evidence) == 1
    assert manifest_evidence[0]["evidence_id"] == ev["evidence_id"]


def test_generic_oil_detection_requires_sar():
    """7. Verify running oil detection on a fresh case without SAR evidence yields insufficient_data."""
    resp = client.post("/api/v1/cases", json={"name": "No-SAR Case"})
    assert resp.status_code == 201
    case_id = resp.json()["case_id"]

    detect_resp = client.post(f"/api/v1/cases/{case_id}/analysis/oil-detection")
    assert detect_resp.status_code == 200
    res = detect_resp.json()

    assert res["status"] == "insufficient_data"
    assert any("No SAR image evidence found" in w for w in res["warnings"])


def test_legacy_r001_endpoint_rejects_generic_case():
    """8. Verify legacy R001 benchmark endpoints reject generic cases with structured error and no R001 data."""
    resp = client.post("/api/v1/cases", json={"name": "Generic Case #2"})
    assert resp.status_code == 201
    case_id = resp.json()["case_id"]

    # Calling legacy endpoint with generic case_id must reject
    legacy_resp = client.get(f"/api/cases/{case_id}")
    assert legacy_resp.status_code in [400, 404]
    err_detail = legacy_resp.json()["detail"]
    assert "BENCHMARK_ENDPOINT_NOT_AVAILABLE_FOR_GENERIC_CASE" in str(err_detail)


def test_r001_still_available():
    """9. Verify validated benchmark case R001_WAKASHIO remains functional on benchmark endpoints."""
    resp = client.get("/api/cases/R001_WAKASHIO")
    assert resp.status_code == 200
    data = resp.json()

    assert data["case_id"] == "R001_WAKASHIO"
    assert "sar" in data
    assert "physics" in data
    assert "ais" in data
    assert data["sar"]["candidate_count"] == 8
