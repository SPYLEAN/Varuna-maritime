"""End-to-end integration tests for the complete 11-step Varuna case workflow.

Verifies:
- RULE 10 (Final API Workflow)
- Sequential stage progression:
  CASE CREATED -> PRODUCT ACQUIRED -> SAR PREPROCESSED -> SLICK ANALYSED
  -> CANDIDATE SELECTED -> HINDCAST COMPLETE -> FORECAST COMPLETE
  -> AIS CORRELATED -> REVIEW READY
- Full filesystem persistence
- Strict segregation between generic cases and R001 benchmark
"""

import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.storage import storage


@pytest.fixture
def client():
    return TestClient(app)


def test_full_case_workflow_progression(client, tmp_path):
    # 1. Create a new generic case
    create_res = client.post(
        "/api/v1/cases",
        json={
            "name": "North Sea Alpha Incident",
            "description": "Reported surface anomaly along offshore shipping corridor",
            "latitude": 53.5,
            "longitude": 2.5,
            "region": "North Sea",
            "incident_type": "SURFACE_SLICK",
        },
    )
    assert create_res.status_code == 201
    case_data = create_res.json()
    case_id = case_data["case_id"]

    # Verify initial workflow status
    wf_res = client.get(f"/api/v1/cases/{case_id}/workflow")
    assert wf_res.status_code == 200
    wf_data = wf_res.json()
    assert wf_data["current_stage"] == "CASE CREATED"
    assert wf_data["stages"]["CASE CREATED"]["completed"] is True
    assert wf_data["is_complete"] is False

    # 2. Attach mock satellite observation to manifest for generic case
    raw_case = storage.get_case(case_id)
    raw_case.setdefault("data_manifest", {})["satellite_observations"] = [{
        "observation_id": f"obs_{case_id}",
        "stac_item_id": f"S1A_IW_GRDH_20240410_{case_id}",
        "datetime": "2024-04-10T12:00:00Z",
    }]
    storage.save_case(raw_case)

    # 3. Product Acquisition
    acq_res = client.post(f"/api/v1/cases/{case_id}/workflow/acquire")
    assert acq_res.status_code == 200
    acq_data = acq_res.json()
    assert acq_data["status"] in ["SUCCESS", "BLOCKED"]

    # 4. SAR Preprocessing
    prep_res = client.post(f"/api/v1/cases/{case_id}/workflow/preprocess")
    assert prep_res.status_code == 200
    prep_data = prep_res.json()
    assert prep_data["status"] == "SUCCESS"
    assert prep_data["details"]["radiometric_mode"] == "SIGMA0_CALIBRATED_DB"

    # Verify workflow state updated in persistent storage
    wf_res = client.get(f"/api/v1/cases/{case_id}/workflow")
    assert wf_res.json()["current_stage"] == "SAR PREPROCESSED"

    # 5. Slick Analysis (OilSeg V1)
    seg_res = client.post(f"/api/v1/cases/{case_id}/workflow/analyse-slick")
    assert seg_res.status_code == 200
    seg_data = seg_res.json()
    assert seg_data["status"] == "SUCCESS"
    assert seg_data["details"]["model_version"] is not None
    assert seg_data["details"]["polygon_count"] > 0

    # 6. Candidate Selection (Evidence Gate)
    gate_res = client.post(
        f"/api/v1/cases/{case_id}/workflow/select-candidate",
        json={"wind_speed_ms": 6.5, "distance_to_land_km": 15.0},
    )
    assert gate_res.status_code == 200
    gate_data = gate_res.json()
    assert gate_data["status"] == "SUCCESS"
    assert gate_data["details"]["evidence_gate_status"] == "PHYSICS_ELIGIBLE"
    assert gate_data["details"]["physics_eligible"] is True

    # 7. Hindcast Execution
    hc_res = client.post(f"/api/v1/cases/{case_id}/workflow/hindcast")
    assert hc_res.status_code == 200
    hc_data = hc_res.json()
    assert hc_data["status"] == "SUCCESS"
    assert "probable_release_region" in hc_data["details"]
    assert "probable_release_window" in hc_data["details"]

    # 8. Forecast Execution
    fc_res = client.post(f"/api/v1/cases/{case_id}/workflow/forecast")
    assert fc_res.status_code == 200
    fc_data = fc_res.json()
    assert fc_data["status"] == "SUCCESS"
    assert "T+24h" in fc_data["details"]["horizons"]

    # 9. AIS Correlation
    ais_res = client.post(f"/api/v1/cases/{case_id}/workflow/correlate-ais")
    assert ais_res.status_code == 200
    ais_data = ais_res.json()
    assert ais_data["status"] == "SUCCESS"
    candidates = ais_data["details"]["candidates"]
    assert len(candidates) > 0
    for cand in candidates:
        # Enforce Rule 9 terminology: INVESTIGATIVE_CANDIDATE only
        assert cand["candidate_designation"] == "INVESTIGATIVE_CANDIDATE"
        assert "culprit" not in cand["candidate_designation"].lower()
        assert "guilty" not in cand["candidate_designation"].lower()

    # 10. Final Incident Review Report
    rev_res = client.get(f"/api/v1/cases/{case_id}/workflow/incident-review")
    assert rev_res.status_code == 200
    report = rev_res.json()
    assert report["case_id"] == case_id
    assert "response_intelligence" in report
    assert "where_is_it_moving" in report["response_intelligence"]
    assert "uncertainty_and_limitations" in report
    assert "provenance_chain" in report

    # 11. Verify End-to-End Workflow Completion
    wf_final = client.get(f"/api/v1/cases/{case_id}/workflow").json()
    assert wf_final["current_stage"] == "REVIEW READY"
    assert wf_final["is_complete"] is True
    for stage_name, stage_info in wf_final["stages"].items():
        if stage_name != "OBSERVATION SEARCHED":
            assert stage_info["completed"] is True, f"Stage {stage_name} should be completed"


def test_generic_case_cannot_access_r001_benchmark_endpoint(client):
    """Verifies that R001 benchmark endpoints reject generic non-benchmark cases."""
    res = client.get("/api/cases/generic_case_999999")
    assert res.status_code == 404
    assert "BENCHMARK_ENDPOINT_NOT_AVAILABLE_FOR_GENERIC_CASE" in res.json()["detail"]
