"""Regression tests enforcing Varuna's scientific truthfulness contracts.

Validates:
1. Synthetic data can never identify itself as real Sentinel-1 data
2. Synthetic rasters never receive a fake archive SHA or STAC ID
3. Credentials alone do not produce CDSE PASS
4. Live provider PASS requires verified acquisition artifacts (archive, manifest, VV/VH)
5. Demo trajectory cannot identify itself as OpenDrift or REAL_ENVIRONMENTAL_FORCING
6. REAL OpenDrift status requires actual forcing & model execution
7. Synthetic AIS remains explicitly tagged as SYNTHETIC_DEMO
8. Final incident review report propagates execution modes truthfully
"""

import json
import os
from pathlib import Path
import pytest
import rasterio
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.storage import storage


@pytest.fixture
def client():
    return TestClient(app)


def test_synthetic_data_can_never_identify_as_real_sentinel1():
    """Prove that OilSeg V1 synthetic benchmark records declare synthetic provenance."""
    manifest_path = Path("07_results/final_build/oilseg_manifest.json")
    assert manifest_path.exists(), "OilSeg manifest must exist"

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert len(manifest) == 68

    for record in manifest:
        assert record["data_mode"] == "SYNTHETIC"
        assert record["source_dataset"] == "VARUNA_OILSEG_V1_SYNTHETIC_BENCHMARK"
        assert record["sensor_simulation"] == "SENTINEL1_LIKE_DUAL_POL"
        assert record["real_world_validation"] == "REAL_WORLD_GENERALIZATION_NOT_YET_VALIDATED"
        # Must not claim genuine Copernicus Sentinel product license
        assert "Copernicus Sentinel Open Access" not in record.get("license", "")


def test_synthetic_rasters_never_receive_fake_archive_sha_or_stac(client):
    """Prove that synthetic preprocessing never attaches fabricated provider provenance."""
    # Create case
    res = client.post("/api/v1/cases", json={"name": "Truthfulness Test Case", "latitude": 54.0, "longitude": 3.0})
    assert res.status_code == 201
    case_id = res.json()["case_id"]

    # Preprocess in demo mode
    prep_res = client.post(f"/api/v1/cases/{case_id}/workflow/preprocess", json={"execution_mode": "SYNTHETIC_DEMO"})
    assert prep_res.status_code == 200
    details = prep_res.json()["details"]

    assert details["execution_mode"] == "SYNTHETIC_DEMO"
    assert details["source_stac_item_id"] == "NONE"
    assert details["source_archive_sha256"] == "NONE"
    assert details["source_product_id"] == "NONE"

    # Verify GeoTIFF tags on disk
    vv_path = details["vv_path"]
    with rasterio.open(vv_path) as src:
        tags = src.tags()
        assert tags.get("DATA_MODE") == "SYNTHETIC_DEMO"
        assert tags.get("SOURCE_ARCHIVE_SHA256") == "NONE"
        assert tags.get("SOURCE_STAC_ITEM_ID") == "NONE"
        assert tags.get("SOURCE_PRODUCT_ID") == "NONE"


def test_credentials_alone_do_not_produce_cdse_pass(client, monkeypatch):
    """Prove that mere presence of credentials in env does NOT yield REAL_PROVIDER_VALIDATION=PASS."""
    monkeypatch.setenv("CDSE_USER", "mock_user_with_no_network")
    monkeypatch.setenv("CDSE_PASS", "mock_password_123")

    res = client.post("/api/v1/cases", json={"name": "Credentials Audit Case", "latitude": 54.0, "longitude": 3.0})
    case_id = res.json()["case_id"]

    raw_case = storage.get_case(case_id)
    raw_case.setdefault("data_manifest", {})["satellite_observations"] = [{
        "observation_id": f"obs_{case_id}",
        "stac_item_id": "S1A_IW_GRDH_NONEXISTENT_ITEM",
    }]
    storage.save_case(raw_case)

    # Acquire should attempt and gracefully block/fail rather than returning PASS
    acq_res = client.post(f"/api/v1/cases/{case_id}/workflow/acquire")
    assert acq_res.status_code == 200
    acq_data = acq_res.json()

    assert acq_data["status"] == "BLOCKED"
    assert acq_data["real_provider_validation"] == "BLOCKED"
    assert acq_data["execution_mode"] == "BLOCKED"


def test_live_provider_pass_requires_verified_acquisition_artifacts(client):
    """Prove that REAL_PROVIDER_VALIDATION=PASS requires verified archive, manifest, and measurement files."""
    # When no credentials and no cache, it must return BLOCKED
    res = client.post("/api/v1/cases", json={"name": "Artifacts Verification Case", "latitude": 54.0, "longitude": 3.0})
    case_id = res.json()["case_id"]

    raw_case = storage.get_case(case_id)
    raw_case.setdefault("data_manifest", {})["satellite_observations"] = [{
        "observation_id": f"obs_{case_id}",
        "stac_item_id": "S1A_IW_GRDH_TEST_OBS",
    }]
    storage.save_case(raw_case)

    acq_res = client.post(f"/api/v1/cases/{case_id}/workflow/acquire")
    acq_data = acq_res.json()
    assert acq_data["real_provider_validation"] == "BLOCKED"
    assert acq_data["execution_mode"] == "BLOCKED"


def test_demo_trajectory_cannot_identify_itself_as_opendrift(client):
    """Prove that demo trajectory approximation never calls itself OpenDrift or REAL_ENVIRONMENTAL_FORCING."""
    res = client.post("/api/v1/cases", json={"name": "Trajectory Nomenclature Case", "latitude": 54.0, "longitude": 3.0})
    case_id = res.json()["case_id"]

    # Preprocess & analyse
    client.post(f"/api/v1/cases/{case_id}/workflow/preprocess")
    client.post(f"/api/v1/cases/{case_id}/workflow/analyse-slick")
    client.post(f"/api/v1/cases/{case_id}/workflow/select-candidate")

    # Hindcast in demo mode
    hc_res = client.post(f"/api/v1/cases/{case_id}/workflow/hindcast", json={"execution_mode": "SYNTHETIC_DEMO"})
    assert hc_res.status_code == 200
    hc_details = hc_res.json()["details"]

    assert hc_details["engine"] == "DEMO_TRAJECTORY_APPROXIMATION"
    assert "OpenDrift" not in hc_details["engine"]
    assert hc_details["forcing_provenance"]["forcing_mode"] == "SYNTHETIC_DEMO_APPROXIMATION"
    assert hc_details["forcing_provenance"]["forcing_mode"] != "REAL_ENVIRONMENTAL_FORCING"
    assert hc_details["forcing_provenance"]["wind_dataset"] == "NONE"

    # Forecast in demo mode
    fc_res = client.post(f"/api/v1/cases/{case_id}/workflow/forecast", json={"execution_mode": "SYNTHETIC_DEMO"})
    assert fc_res.status_code == 200
    fc_details = fc_res.json()["details"]

    assert fc_details["engine"] == "DEMO_TRAJECTORY_APPROXIMATION"
    assert "OpenDrift" not in fc_details["engine"]
    assert fc_details["forcing_provenance"]["forcing_mode"] == "SYNTHETIC_DEMO_APPROXIMATION"
    assert fc_details["forcing_provenance"]["forecast_winds"] == "NONE"


def test_real_opendrift_status_requires_actual_model_execution(client):
    """Prove that requesting REAL OpenDrift execution returns BLOCKED when NetCDF forcing is absent."""
    res = client.post("/api/v1/cases", json={"name": "OpenDrift Execution Guard Case", "latitude": 54.0, "longitude": 3.0})
    case_id = res.json()["case_id"]

    client.post(f"/api/v1/cases/{case_id}/workflow/preprocess")
    client.post(f"/api/v1/cases/{case_id}/workflow/analyse-slick")
    client.post(f"/api/v1/cases/{case_id}/workflow/select-candidate")

    hc_res = client.post(f"/api/v1/cases/{case_id}/workflow/hindcast", json={"execution_mode": "REAL"})
    assert hc_res.status_code == 200
    hc_data = hc_res.json()
    assert hc_data["status"] == "BLOCKED"
    assert hc_data["execution_mode"] == "BLOCKED"
    assert "NetCDF" in hc_data["details"]["reason"]

    fc_res = client.post(f"/api/v1/cases/{case_id}/workflow/forecast", json={"execution_mode": "REAL"})
    assert fc_res.status_code == 200
    fc_data = fc_res.json()
    assert fc_data["status"] == "BLOCKED"
    assert fc_data["execution_mode"] == "BLOCKED"


def test_synthetic_ais_remains_explicitly_tagged(client):
    """Prove that synthetic AIS candidate tracks are explicitly tagged with ais_data_mode=SYNTHETIC_DEMO."""
    res = client.post("/api/v1/cases", json={"name": "AIS Tagging Case", "latitude": 54.0, "longitude": 3.0})
    case_id = res.json()["case_id"]

    client.post(f"/api/v1/cases/{case_id}/workflow/preprocess")
    client.post(f"/api/v1/cases/{case_id}/workflow/analyse-slick")
    client.post(f"/api/v1/cases/{case_id}/workflow/select-candidate")
    client.post(f"/api/v1/cases/{case_id}/workflow/hindcast")

    ais_res = client.post(f"/api/v1/cases/{case_id}/workflow/correlate-ais")
    assert ais_res.status_code == 200
    ais_data = ais_res.json()

    assert ais_data["details"]["execution_mode"] == "SYNTHETIC_DEMO"
    assert ais_data["details"]["ais_data_mode"] == "SYNTHETIC_DEMO"

    for candidate in ais_data["details"]["candidates"]:
        assert candidate["ais_data_mode"] == "SYNTHETIC_DEMO"
        assert candidate["source_record_type"] == "SYNTHETIC_DEMO_TRAFFIC"
        assert candidate["candidate_designation"] == "INVESTIGATIVE_CANDIDATE"
        assert "culprit" not in candidate["candidate_designation"].lower()
        assert "guilty" not in candidate["candidate_designation"].lower()


def test_final_report_propagates_execution_modes_correctly(client):
    """Prove that final incident review report propagates stage execution modes and honest terminology."""
    res = client.post("/api/v1/cases", json={"name": "Report Propagation Case", "latitude": 54.0, "longitude": 3.0})
    case_id = res.json()["case_id"]

    # Ingest mock observation & run workflow
    raw_case = storage.get_case(case_id)
    raw_case.setdefault("data_manifest", {})["satellite_observations"] = [{
        "observation_id": f"obs_{case_id}",
        "stac_item_id": f"S1A_IW_GRDH_TEST_{case_id}",
    }]
    storage.save_case(raw_case)

    client.post(f"/api/v1/cases/{case_id}/workflow/acquire")
    client.post(f"/api/v1/cases/{case_id}/workflow/preprocess")
    client.post(f"/api/v1/cases/{case_id}/workflow/analyse-slick")
    client.post(f"/api/v1/cases/{case_id}/workflow/select-candidate")
    client.post(f"/api/v1/cases/{case_id}/workflow/hindcast")
    client.post(f"/api/v1/cases/{case_id}/workflow/forecast")
    client.post(f"/api/v1/cases/{case_id}/workflow/correlate-ais")

    rev_res = client.get(f"/api/v1/cases/{case_id}/workflow/incident-review")
    assert rev_res.status_code == 200
    report = rev_res.json()

    modes = report["stage_execution_modes"]
    assert modes["PRODUCT ACQUIRED"] == "BLOCKED"
    assert modes["SAR PREPROCESSED"] == "SYNTHETIC_DEMO"
    assert modes["SLICK ANALYSED"] == "REAL"
    assert modes["CANDIDATE SELECTED"] == "REAL"
    assert modes["HINDCAST COMPLETE"] == "SYNTHETIC_DEMO"
    assert modes["FORECAST COMPLETE"] == "SYNTHETIC_DEMO"
    assert modes["AIS CORRELATED"] == "SYNTHETIC_DEMO"

    # Terminology verification: no false certainty
    resp_intel = report["response_intelligence"]
    assert "oil-like evidence" in resp_intel["what_was_observed"].lower()
    assert "confirmed oil" not in resp_intel["what_was_observed"].lower()
    assert "legally defensible" not in json.dumps(report).lower()
