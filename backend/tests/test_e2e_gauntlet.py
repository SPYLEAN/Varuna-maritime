"""
Unit Test Suite for SAMUDRANETRA TASK014 — End-to-End Operational + Failure-Mode Gauntlet.

Verifies golden path R001, operational state model, failure mode fixtures,
hard evidence guards (false positives), claim guard text auditor, and provenance integrity.
"""

from pathlib import Path
from fastapi.testclient import TestClient
import pytest

from backend.app.main import app
from backend.app.services.investigation_engine import (
    build_unified_investigation_case,
    build_failure_mode_fixture,
)

client = TestClient(app)
CASE_ID = "R001_WAKASHIO"
R001_DIR = Path(r"C:\Users\tanvi\OneDrive\Documents\Oil Spill\SamudraNetra-Research\R001_WAKASHIO")


def test_golden_path_r001_workflow():
    """1. Normal R001 Golden Path Workflow."""
    resp = client.get(f"/api/cases/{CASE_ID}")
    assert resp.status_code == 200
    c = resp.json()

    assert c["case_id"] == "R001_WAKASHIO"
    assert c["operational_state"] == "ANALYST_REVIEW_REQUIRED"
    assert c["sar"]["candidate_count"] == 8
    assert c["physics"]["hindcast_status"] == "PHYSICS_UNCERTAIN"
    assert c["ais"]["data_mode"] == "SYNTHETIC_DEMO"
    assert c["ais"]["historical_attribution_valid"] is False


def test_operational_state_lifecycle_model():
    """2. Real Operational State Model."""
    c = build_unified_investigation_case(R001_DIR)
    inv = c["investigation"]

    assert "operational_state" in inv
    assert inv["operational_state"] == "ANALYST_REVIEW_REQUIRED"
    assert inv["data_age"] == "LATEST OBSERVATION"
    assert inv["availability_status"] == "DATA_READY"


def test_failure_mode_no_credible_candidate():
    """6. Failure Case — No Credible Candidate."""
    fix = build_failure_mode_fixture(R001_DIR, "NO_CREDIBLE_CANDIDATE")

    assert fix["ais"]["abstention_state"] == "NO_CREDIBLE_CANDIDATE"
    assert fix["investigation"]["overall_state"] == "NO_CREDIBLE_CANDIDATE"
    for v in fix["ais"]["candidates"]:
        assert v["investigative_priority_score"] < 0.250


def test_failure_mode_ambiguous_attribution():
    """7. Failure Case — Ambiguous Vessels."""
    fix = build_failure_mode_fixture(R001_DIR, "AMBIGUOUS_ATTRIBUTION")

    assert fix["ais"]["abstention_state"] == "AMBIGUOUS_ATTRIBUTION"
    assert fix["investigation"]["overall_state"] == "AMBIGUOUS"
    scores = [v["investigative_priority_score"] for v in fix["ais"]["candidates"][:2]]
    assert abs(scores[0] - scores[1]) <= 0.05


def test_behavioural_false_positive_guard():
    """8. Behavioural False Positive Guard."""
    fix = build_failure_mode_fixture(R001_DIR, "BEHAVIOURAL_FALSE_POSITIVE")
    v = fix["ais"]["candidates"][0]

    assert v["behaviour_evidence"] == 0.95
    assert v["spatial_evidence"] == 0.00
    assert v["hard_guard_passed"] is False
    assert v["investigative_priority_score"] <= 0.69  # Cannot be HIGH priority


def test_spatial_false_positive_guard():
    """9. Spatial False Positive Guard."""
    fix = build_failure_mode_fixture(R001_DIR, "SPATIAL_FALSE_POSITIVE")
    v = fix["ais"]["candidates"][0]

    assert v["spatial_evidence"] == 0.95
    assert v["temporal_evidence"] == 0.00
    assert v["hard_guard_passed"] is False
    assert v["investigative_priority_score"] <= 0.69  # Cannot be HIGH priority


def test_temporal_false_positive_guard():
    """10. Temporal False Positive Guard."""
    fix = build_failure_mode_fixture(R001_DIR, "TEMPORAL_FALSE_POSITIVE")
    v = fix["ais"]["candidates"][0]

    assert v["temporal_evidence"] == 1.00
    assert v["spatial_evidence"] == 0.10
    assert v["hard_guard_passed"] is False
    assert v["investigative_priority_score"] <= 0.40  # Cannot be HIGH priority


def test_uncertain_physics_propagation():
    """11. Failure Case — Uncertain Physics Propagation."""
    fix = build_failure_mode_fixture(R001_DIR, "UNCERTAIN_PHYSICS")

    assert fix["physics"]["hindcast_status"] == "PHYSICS_UNCERTAIN"
    for h, q in fix["physics"]["horizon_quality"].items():
        assert q == "UNCERTAIN"


def test_empty_sar_candidates():
    """17. Failure Case — Empty SAR Candidates."""
    fix = build_failure_mode_fixture(R001_DIR, "EMPTY_SAR_CANDIDATES")

    assert fix["sar"]["candidate_count"] == 0
    assert fix["investigation"]["overall_state"] == "NO_VALID_SAR_CANDIDATE"


def test_non_vessel_source_case():
    """19. Non-Vessel Source Case."""
    fix = build_failure_mode_fixture(R001_DIR, "NON_VESSEL_SOURCE")

    assert fix["ais"]["abstention_state"] == "NON_VESSEL_SOURCE_POSSIBLE"
    assert fix["investigation"]["overall_state"] == "NON_VESSEL_SOURCE_POSSIBLE"


def test_provenance_failure_guard():
    """20. Provenance Failure Guard."""
    fix = build_failure_mode_fixture(R001_DIR, "PROVENANCE_CORRUPTED")

    assert fix["investigation"]["provenance"]["clean_room_protocol"] == "FAIL"
    assert fix["investigation"]["provenance"]["provenance_corrupted"] is True


def test_claim_guard_forbidden_words_auditor():
    """21. Claim Guard Text Auditor."""
    c = build_unified_investigation_case(R001_DIR)
    text = str(c).lower()

    forbidden_terms = ["culprit", "guilty", "proven source", "ai confidence", "probability of guilt", "100% accurate"]
    for term in forbidden_terms:
        assert term not in text, f"Forbidden term '{term}' found in unified investigation object."
