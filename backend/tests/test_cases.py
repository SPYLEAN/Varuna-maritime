import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.storage import storage, JSONCaseStorage


@pytest.fixture(autouse=True)
def temp_storage(tmp_path):
    # Override storage directory for clean test isolation
    original_dir = storage.storage_dir
    storage.storage_dir = tmp_path / "cases"
    storage.storage_dir.mkdir(parents=True, exist_ok=True)
    yield
    storage.storage_dir = original_dir


client = TestClient(app)


def test_create_case():
    payload = {
        "name": "Mumbai Offshore Spill Incident",
        "description": "Observed dark slick near Mumbai harbor approaches",
        "observation_timestamp": "2026-08-27T10:00:00Z",
        "latitude": 18.92,
        "longitude": 72.83,
        "source": "Sentinel-1A SAR image pass",
        "tags": ["mumbai", "sar", "urgent"],
    }
    response = client.post("/cases", json=payload)
    assert response.status_code == 201
    data = response.json()

    assert "case_id" in data
    assert data["case_id"].startswith("case_")
    assert data["name"] == payload["name"]
    assert data["latitude"] == 18.92
    assert data["longitude"] == 72.83
    assert data["tags"] == ["mumbai", "sar", "urgent"]

    # Verify analysis status initialization
    status = data["analysis_status"]
    assert status["oil_detection"] == "not_started"
    assert status["spill_geometry"] == "not_started"
    assert status["hindcast"] == "not_started"
    assert status["ais_correlation"] == "not_started"
    assert status["attribution"] == "not_started"

    # Verify data manifest initialization
    manifest = data["data_manifest"]
    assert manifest["satellite_imagery"] == []
    assert manifest["oil_masks"] == []
    assert manifest["ais_data"] == []
    assert manifest["met_ocean_data"] == []
    assert manifest["research_notes"] == []
    assert manifest["analyst_questions"] == []
    assert manifest["generated_analysis_results"] == []


def test_list_cases():
    # Create two test cases
    client.post("/cases", json={"name": "Case Alpha"})
    client.post("/cases", json={"name": "Case Beta"})

    response = client.get("/cases")
    assert response.status_code == 200
    cases = response.json()
    assert len(cases) == 2
    names = [c["name"] for c in cases]
    assert "Case Alpha" in names
    assert "Case Beta" in names


def test_get_case():
    res_create = client.post("/cases", json={"name": "Retrieve Me", "description": "Testing GET endpoint"})
    case_id = res_create.json()["case_id"]

    response = client.get(f"/cases/{case_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["case_id"] == case_id
    assert data["name"] == "Retrieve Me"
    assert data["description"] == "Testing GET endpoint"


def test_get_unknown_case_returns_404():
    response = client.get("/cases/non_existent_case_id")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_add_analyst_question():
    res_create = client.post("/cases", json={"name": "Question Test Case"})
    case_id = res_create.json()["case_id"]

    question_payload = {
        "question": "Which vessels were present near the estimated origin?",
        "asked_by": "lead_analyst",
    }
    res_q = client.post(f"/cases/{case_id}/questions", json=question_payload)
    assert res_q.status_code == 201
    q_data = res_q.json()
    assert "question_id" in q_data
    assert q_data["question"] == question_payload["question"]
    assert q_data["asked_by"] == "lead_analyst"

    # Retrieve full case manifest to verify question persistence inside case
    res_case = client.get(f"/cases/{case_id}")
    assert res_case.status_code == 200
    case_data = res_case.json()
    questions = case_data["data_manifest"]["analyst_questions"]
    assert len(questions) == 1
    assert questions[0]["question_id"] == q_data["question_id"]
    assert questions[0]["question"] == question_payload["question"]


def test_analysis_status_initialized_correctly():
    res = client.post("/cases", json={"name": "Status Check Case"})
    case_data = res.json()
    status = case_data["analysis_status"]

    expected_modules = ["oil_detection", "spill_geometry", "hindcast", "ais_correlation", "attribution"]
    for module in expected_modules:
        assert status[module] == "not_started"
