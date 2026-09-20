"""Tests for Marine Response Priority Engine and Workflow Integration (Iteration 2).

Verifies:
1. CRITICAL receptor (intersects, arrival <= 6h, sensitivity HIGH or CRITICAL)
2. HIGH receptor (intersects, arrival <= 12h, sensitivity HIGH/CRITICAL)
3. MEDIUM receptor (intersects, arrival <= 24h or lower sensitivity)
4. MONITOR when near uncertainty envelope
5. LOW when unrelated
6. deterministic response score
7. demo receptor data is never labeled REAL
8. response score is never labeled probability
9. response endpoint persists RESPONSE PRIORITIZED stage
10. incident review propagates response stage mode correctly
"""

from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services.response_priority import (
    EnvironmentalReceptor,
    TrajectoryThreat,
    calculate_response_score,
    classify_threat_priority,
    evaluate_case_response_priorities,
    evaluate_receptor_priority,
    generate_demo_receptors,
)
from backend.app.storage import storage


@pytest.fixture
def client():
    return TestClient(app)


# 1. CRITICAL receptor
def test_critical_receptor_classification():
    priority, reasons = classify_threat_priority(
        intersects=True,
        arrival_hours=4.5,
        sensitivity="HIGH",
        distance_km=0.5,
        uncertainty_km=4.8,
    )
    assert priority == "CRITICAL"
    assert any("Arrival within 6 hours" in r for r in reasons)
    assert any("Forecast envelope intersects" in r for r in reasons)

    # Test with sensitivity CRITICAL as well
    prio_crit, _ = classify_threat_priority(
        intersects=True,
        arrival_hours=2.0,
        sensitivity="CRITICAL",
        distance_km=0.1,
        uncertainty_km=4.8,
    )
    assert prio_crit == "CRITICAL"


# 2. HIGH receptor
def test_high_receptor_classification():
    priority, reasons = classify_threat_priority(
        intersects=True,
        arrival_hours=10.0,
        sensitivity="HIGH",
        distance_km=1.5,
        uncertainty_km=4.8,
    )
    assert priority == "HIGH"
    assert any("Arrival within 12 hours" in r for r in reasons)

    prio_crit_12h, _ = classify_threat_priority(
        intersects=True,
        arrival_hours=8.5,
        sensitivity="CRITICAL",
        distance_km=1.2,
        uncertainty_km=4.8,
    )
    assert prio_crit_12h == "HIGH"


# 3. MEDIUM receptor
def test_medium_receptor_classification():
    # <= 24h with lower sensitivity
    priority, reasons = classify_threat_priority(
        intersects=True,
        arrival_hours=18.0,
        sensitivity="MEDIUM",
        distance_km=2.5,
        uncertainty_km=4.8,
    )
    assert priority == "MEDIUM"
    assert any("Arrival within 24 hours" in r for r in reasons)

    # <= 6h with LOW sensitivity should be MEDIUM (not CRITICAL)
    prio_low_sens, _ = classify_threat_priority(
        intersects=True,
        arrival_hours=4.0,
        sensitivity="LOW",
        distance_km=0.8,
        uncertainty_km=4.8,
    )
    assert prio_low_sens == "MEDIUM"


# 4. MONITOR when near uncertainty envelope
def test_monitor_when_near_uncertainty_envelope():
    priority, reasons = classify_threat_priority(
        intersects=False,
        arrival_hours=None,
        sensitivity="HIGH",
        distance_km=8.5,
        uncertainty_km=6.0,
    )
    assert priority == "MONITOR"
    assert any("uncertainty buffer" in r for r in reasons)
    assert any("Met-ocean shift could bring receptor into trajectory path" in r for r in reasons)


# 5. LOW when unrelated
def test_low_when_unrelated():
    priority, reasons = classify_threat_priority(
        intersects=False,
        arrival_hours=None,
        sensitivity="LOW",
        distance_km=55.0,
        uncertainty_km=4.8,
    )
    assert priority == "LOW"
    assert any("No forecast envelope intersection" in r for r in reasons)
    assert any("sufficiently outside" in r for r in reasons)


# 6. Deterministic response score
def test_deterministic_response_score():
    score1 = calculate_response_score(
        priority="HIGH",
        arrival_hours=8.7,
        sensitivity="HIGH",
        distance_km=1.2,
    )
    score2 = calculate_response_score(
        priority="HIGH",
        arrival_hours=8.7,
        sensitivity="HIGH",
        distance_km=1.2,
    )
    assert score1 == score2
    assert 0.0 <= score1 <= 1.0
    # Higher urgency / sensitivity yields higher or equal score
    score_crit = calculate_response_score(
        priority="CRITICAL",
        arrival_hours=4.0,
        sensitivity="CRITICAL",
        distance_km=0.5,
    )
    assert score_crit > score1


# 7. Demo receptor data is never labeled REAL
def test_demo_receptor_data_is_never_labeled_real():
    receptors = generate_demo_receptors(case_lat=53.5, case_lon=2.5)
    assert len(receptors) >= 4
    for r in receptors:
        assert r.data_mode == "SYNTHETIC_DEMO"
        assert r.data_mode != "REAL"

    # When evaluated via engine, data_mode remains SYNTHETIC_DEMO
    res = evaluate_case_response_priorities(53.5, 2.5)
    for r in res["receptors"]:
        assert r["data_mode"] == "SYNTHETIC_DEMO"
        assert r["data_mode"] != "REAL"
    assert res["input_data_mode"] == "SYNTHETIC_DEMO"


# 8. Response score is never labeled probability
def test_response_score_never_labeled_probability():
    rec = EnvironmentalReceptor(
        receptor_id="REC-TEST-01",
        name="Test Lagoon",
        receptor_type="coastal wetland",
        latitude=53.55,
        longitude=2.55,
        sensitivity="HIGH",
        data_mode="SYNTHETIC_DEMO",
    )
    threat = TrajectoryThreat(
        receptor_id="REC-TEST-01",
        intersects_forecast_envelope=True,
        estimated_arrival_hours=6.0,
        minimum_distance_km=0.8,
        uncertainty_km=4.8,
        trajectory_execution_mode="SYNTHETIC_DEMO",
    )
    result = evaluate_receptor_priority(rec, threat)

    # Check field names
    result_dict = result.model_dump()
    assert "response_score" in result_dict
    assert "probability" not in result_dict
    assert "impact_probability" not in result_dict

    # Check reasons and limitations do not use probability terminology for the score
    for reason in result.reasons:
        assert "probability" not in reason.lower()
        assert "chance of impact" not in reason.lower()
    
    # Check that limitations explicitly disclaim probability
    assert any("not a" in lim.lower() and "probability" in lim.lower() for lim in result.limitations)


# 9. Response endpoint persists RESPONSE PRIORITIZED stage
def test_response_endpoint_persists_stage(client):
    # Setup case
    create_res = client.post(
        "/api/v1/cases",
        json={
            "name": "Response Priority Test Case",
            "latitude": 53.5,
            "longitude": 2.5,
            "region": "North Sea",
            "incident_type": "SURFACE_SLICK",
        },
    )
    assert create_res.status_code == 201
    case_id = create_res.json()["case_id"]

    # Attach mock obs and advance to FORECAST COMPLETE
    raw_case = storage.get_case(case_id)
    raw_case.setdefault("data_manifest", {})["satellite_observations"] = [{
        "observation_id": f"obs_{case_id}",
        "stac_item_id": f"S1A_IW_GRDH_20240410_{case_id}",
        "datetime": "2024-04-10T12:00:00Z",
    }]
    storage.save_case(raw_case)

    client.post(f"/api/v1/cases/{case_id}/workflow/acquire")
    client.post(f"/api/v1/cases/{case_id}/workflow/preprocess")
    client.post(f"/api/v1/cases/{case_id}/workflow/analyse-slick")
    client.post(
        f"/api/v1/cases/{case_id}/workflow/select-candidate",
        json={"wind_speed_ms": 6.5, "distance_to_land_km": 15.0},
    )
    client.post(f"/api/v1/cases/{case_id}/workflow/hindcast")
    client.post(f"/api/v1/cases/{case_id}/workflow/forecast")

    # Call /response-priority
    resp = client.post(f"/api/v1/cases/{case_id}/workflow/response-priority")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "SUCCESS"
    assert data["execution_mode"] == "REAL"
    assert data["engine_execution_mode"] == "REAL"
    assert data["trajectory_execution_mode"] == "SYNTHETIC_DEMO"
    assert data["receptor_data_mode"] == "SYNTHETIC_DEMO"
    assert data["effective_evidence_mode"] == "SYNTHETIC_DEMO"
    assert "generated_at" in data
    assert data["highest_priority_receptor"] is not None
    assert "response_window_hours" in data
    assert len(data["receptors"]) > 0
    assert len(data["limitations"]) > 0

    # Verify persistent stage in workflow status
    wf_res = client.get(f"/api/v1/cases/{case_id}/workflow")
    assert wf_res.status_code == 200
    wf = wf_res.json()
    assert wf["current_stage"] == "RESPONSE PRIORITIZED"
    assert "RESPONSE PRIORITIZED" in wf["stages"]
    assert wf["stages"]["RESPONSE PRIORITIZED"]["completed"] is True
    assert wf["stages"]["RESPONSE PRIORITIZED"]["data"]["highest_priority_receptor"] is not None


# 10. Incident review propagates response stage mode correctly
def test_incident_review_propagates_response_stage_mode(client):
    create_res = client.post(
        "/api/v1/cases",
        json={
            "name": "Incident Review Response Test",
            "latitude": 53.5,
            "longitude": 2.5,
            "region": "North Sea",
            "incident_type": "SURFACE_SLICK",
        },
    )
    case_id = create_res.json()["case_id"]

    raw_case = storage.get_case(case_id)
    raw_case.setdefault("data_manifest", {})["satellite_observations"] = [{
        "observation_id": f"obs_{case_id}",
        "stac_item_id": f"S1A_IW_GRDH_20240410_{case_id}",
        "datetime": "2024-04-10T12:00:00Z",
    }]
    storage.save_case(raw_case)

    client.post(f"/api/v1/cases/{case_id}/workflow/acquire")
    client.post(f"/api/v1/cases/{case_id}/workflow/preprocess")
    client.post(f"/api/v1/cases/{case_id}/workflow/analyse-slick")
    client.post(f"/api/v1/cases/{case_id}/workflow/select-candidate")
    client.post(f"/api/v1/cases/{case_id}/workflow/hindcast")
    client.post(f"/api/v1/cases/{case_id}/workflow/forecast")
    client.post(f"/api/v1/cases/{case_id}/workflow/response-priority")
    client.post(f"/api/v1/cases/{case_id}/workflow/correlate-ais")

    rev_res = client.get(f"/api/v1/cases/{case_id}/workflow/incident-review")
    assert rev_res.status_code == 200
    report = rev_res.json()

    assert "RESPONSE PRIORITIZED" in report["stage_execution_modes"]
    assert report["stage_execution_modes"]["RESPONSE PRIORITIZED"] == "REAL"
    assert "highest_priority_receptor" in report["response_intelligence"]
    assert report["response_intelligence"]["highest_priority_receptor"] is not None
    assert "response_window_hours" in report["response_intelligence"]
    assert report["response_intelligence"]["engine_execution_mode"] == "REAL"
    assert report["response_intelligence"]["effective_evidence_mode"] == "SYNTHETIC_DEMO"


# 11. Real engine + demo trajectory => effective_evidence_mode SYNTHETIC_DEMO
def test_real_engine_plus_demo_trajectory_yields_synthetic_demo():
    from backend.app.services.response_priority import compute_effective_evidence_mode
    
    # Rule check
    eff_mode = compute_effective_evidence_mode(
        trajectory_execution_mode="SYNTHETIC_DEMO",
        receptor_data_mode="REAL",
    )
    assert eff_mode == "SYNTHETIC_DEMO"
    assert eff_mode != "REAL"

    rec = EnvironmentalReceptor(
        receptor_id="REC-REAL-01",
        name="Real Surveyed Marine Reserve",
        receptor_type="marine reserve",
        latitude=53.5,
        longitude=2.6,
        sensitivity="HIGH",
        data_mode="REAL",
    )
    threat = TrajectoryThreat(
        receptor_id="REC-REAL-01",
        intersects_forecast_envelope=True,
        estimated_arrival_hours=9.0,
        minimum_distance_km=1.5,
        uncertainty_km=4.8,
        trajectory_execution_mode="SYNTHETIC_DEMO",  # Demo trajectory
    )
    res = evaluate_receptor_priority(rec, threat, engine_execution_mode="REAL")
    
    assert res.engine_execution_mode == "REAL"
    assert res.trajectory_execution_mode == "SYNTHETIC_DEMO"
    assert res.receptor_data_mode == "REAL"
    assert res.effective_evidence_mode == "SYNTHETIC_DEMO"
    assert res.effective_evidence_mode != "REAL"


# 12. Demo receptor data cannot result in effective_evidence_mode REAL
def test_demo_receptor_data_cannot_result_in_effective_evidence_mode_real():
    from backend.app.services.response_priority import compute_effective_evidence_mode
    
    # Even if trajectory was a real simulation, demo receptors force SYNTHETIC_DEMO
    eff_mode = compute_effective_evidence_mode(
        trajectory_execution_mode="REAL",
        receptor_data_mode="SYNTHETIC_DEMO",
    )
    assert eff_mode == "SYNTHETIC_DEMO"
    assert eff_mode != "REAL"

    rec = EnvironmentalReceptor(
        receptor_id="REC-DEMO-99",
        name="Demonstration Coastal Inlet",
        receptor_type="coastal inlet",
        latitude=53.5,
        longitude=2.6,
        sensitivity="CRITICAL",
        data_mode="SYNTHETIC_DEMO",
    )
    threat = TrajectoryThreat(
        receptor_id="REC-DEMO-99",
        intersects_forecast_envelope=True,
        estimated_arrival_hours=5.0,
        minimum_distance_km=0.5,
        uncertainty_km=3.0,
        trajectory_execution_mode="REAL",
    )
    res = evaluate_receptor_priority(rec, threat, engine_execution_mode="REAL")
    
    assert res.engine_execution_mode == "REAL"
    assert res.trajectory_execution_mode == "REAL"
    assert res.receptor_data_mode == "SYNTHETIC_DEMO"
    assert res.effective_evidence_mode == "SYNTHETIC_DEMO"
    assert res.effective_evidence_mode != "REAL"

    # Also test case level evaluation with custom demo receptors
    case_res = evaluate_case_response_priorities(
        case_lat=53.5,
        case_lon=2.5,
        forecast_data={"execution_mode": "REAL"},
        custom_receptors=[rec],
        engine_execution_mode="REAL",
    )
    assert case_res["engine_execution_mode"] == "REAL"
    assert case_res["trajectory_execution_mode"] == "REAL"
    assert case_res["receptor_data_mode"] == "SYNTHETIC_DEMO"
    assert case_res["effective_evidence_mode"] == "SYNTHETIC_DEMO"
    assert case_res["effective_evidence_mode"] != "REAL"


# 13. UI does not label demo trajectory REAL
def test_ui_does_not_label_demo_trajectory_real():
    index_html = (Path(__file__).resolve().parents[2] / "ops_console" / "index.html").read_text(encoding="utf-8")
    app_js = (Path(__file__).resolve().parents[2] / "ops_console" / "app.js").read_text(encoding="utf-8")

    # In index.html truthfulness card, TRAJECTORY must be SYNTHETIC_DEMO
    assert 'id="truth-stage-traj">SYNTHETIC_DEMO<' in index_html
    assert 'id="truth-stage-traj">REAL<' not in index_html

    # In app.js, ensure trajectory is set to SYNTHETIC_DEMO when demo forcing was used
    assert 'trajTruth.innerText = "SYNTHETIC_DEMO"' in app_js

    # Verify the 5 truthfulness cards are present
    assert "SAR PROCESSING" in index_html
    assert "TRAJECTORY" in index_html
    assert "RESPONSE ENGINE" in index_html
    assert "RESPONSE INPUTS" in index_html
    assert "RECEPTOR DATA" in index_html
