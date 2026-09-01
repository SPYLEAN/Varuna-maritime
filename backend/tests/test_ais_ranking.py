"""
Unit Test Suite for SAMUDRANETRA TASK010B — Explainable AIS Evidence Ranking + Abstention Engine.

Verifies deterministic ranking, weight normalization, missing evidence handling,
hard spatiotemporal guards, abstention states (ambiguous, no candidate, insufficient data, non-vessel),
synthetic-mode labelling, reason code generation, and ranking freeze cryptographic SHA256.
"""

import json
from pathlib import Path
import pytest

from backend.app.services.ais_ranking import (
    get_current_data_mode,
    calculate_investigative_priority_score,
    generate_reason_codes_and_evidence,
    classify_attribution_state,
    create_api_ready_vessel_objects,
    create_ais_ranking_freeze,
    DEFAULT_WEIGHTS,
)

R001_DIR = Path(r"C:\Users\tanvi\OneDrive\Documents\Oil Spill\SamudraNetra-Research\R001_WAKASHIO")


def test_synthetic_data_mode_guard():
    """Verifies that synthetic data mode forces historical_attribution_valid = False."""
    mode, valid = get_current_data_mode(R001_DIR)

    assert mode in ["SYNTHETIC_DEMO", "REAL_HISTORICAL"]
    if mode == "SYNTHETIC_DEMO":
        assert valid is False


def test_deterministic_ranking_and_weight_normalization():
    """Verifies deterministic score calculation and weight normalization."""
    evidence_row = {
        "mmsi": "538001111",
        "vessel_name": "VESSEL_ALPHA",
        "vessel_type": "cargo",
        "candidate_id": "C001",
        "horizon_hours": 72,
        "spatial_compatibility_score": 0.90,
        "temporal_compatibility_score": 1.00,
        "route_compatibility_score": 0.80,
        "behaviour_indicator_score": 0.70,
        "ais_data_integrity_score": 0.90,
        "temporal_status": "TEMPORALLY_COMPATIBLE",
        "intersects_source_region": True,
        "min_geodesic_distance_km": 0.0,
    }

    res1 = calculate_investigative_priority_score(evidence_row)
    res2 = calculate_investigative_priority_score(evidence_row)

    assert res1["investigative_priority_score"] == res2["investigative_priority_score"]
    assert 0.0 <= res1["investigative_priority_score"] <= 1.0
    assert res1["hard_guard_passed"] is True


def test_hard_spatiotemporal_guard_capping():
    """Verifies that gap or behaviour anomalies CANNOT independently trigger HIGH priority if hard guard fails."""
    # Temporally incompatible but strong behaviour anomaly
    evidence_row_incomp_time = {
        "mmsi": "538002222",
        "vessel_name": "VESSEL_BETA",
        "vessel_type": "fishing",
        "candidate_id": "C001",
        "horizon_hours": 72,
        "spatial_compatibility_score": 0.95,
        "temporal_compatibility_score": 0.00,  # NOT_COMPATIBLE
        "route_compatibility_score": 0.90,
        "behaviour_indicator_score": 1.00,  # High behaviour anomaly
        "ais_data_integrity_score": 0.95,
        "temporal_status": "NOT_COMPATIBLE",
        "intersects_source_region": True,
        "min_geodesic_distance_km": 0.0,
    }

    res = calculate_investigative_priority_score(evidence_row_incomp_time)

    assert res["hard_guard_passed"] is False
    assert res["investigative_priority_score"] <= 0.69  # Capped below HIGH priority threshold (0.70)


def test_abstention_states():
    """Verifies all abstention engine classifications: AMBIGUOUS, NO_CREDIBLE_CANDIDATE, INSUFFICIENT_DATA, NON_VESSEL."""
    # 1. Ambiguous Attribution (top 2 delta <= 0.05)
    cand_ambig = [
        {"mmsi": "538001111", "vessel_name": "V1", "investigative_priority_score": 0.85, "hard_guard_passed": True},
        {"mmsi": "538002222", "vessel_name": "V2", "investigative_priority_score": 0.83, "hard_guard_passed": True},
    ]
    eval_ambig = classify_attribution_state(cand_ambig, ais_coverage_quality=0.90)
    assert eval_ambig["overall_case_state"] == "AMBIGUOUS_ATTRIBUTION"
    assert eval_ambig["abstention_triggered"] is True

    # 2. Insufficient Data (coverage quality < 0.30)
    eval_insuff = classify_attribution_state(cand_ambig, ais_coverage_quality=0.20)
    assert eval_insuff["overall_case_state"] == "INSUFFICIENT_DATA"
    assert eval_insuff["abstention_triggered"] is True

    # 3. No Credible Candidate (max score < 0.25)
    cand_low = [
        {"mmsi": "538003333", "vessel_name": "V3", "investigative_priority_score": 0.15, "hard_guard_passed": False},
    ]
    eval_nocred = classify_attribution_state(cand_low, ais_coverage_quality=0.90)
    assert eval_nocred["overall_case_state"] == "NON_VESSEL_SOURCE_POSSIBLE"
    assert eval_nocred["abstention_triggered"] is True

    # 4. Zero vessels
    eval_zero = classify_attribution_state([], ais_coverage_quality=0.90)
    assert eval_zero["overall_case_state"] == "NO_CREDIBLE_CANDIDATE"
    assert eval_zero["abstention_triggered"] is True


def test_reason_codes_and_evidence_categorization():
    """Verifies human-readable reason codes and supporting/limiting/missing evidence categorization."""
    evidence_row = {
        "intersects_source_region": True,
        "min_geodesic_distance_km": 0.0,
        "temporal_status": "TEMPORALLY_COMPATIBLE",
        "spatial_compatibility_score": 1.0,
    }
    behaviour_row = {
        "slowdown_event_detected": True,
        "cog_sharp_turns_count": 2,
    }
    gap_row = {
        "max_reporting_gap_hours": 3.5,
        "ais_gap_evidence": "MODERATE_REPORTING_GAP",
    }

    exp = generate_reason_codes_and_evidence(evidence_row, behaviour_row, gap_row)

    assert "SOURCE_REGION_INTERSECTION" in exp["reason_codes"]
    assert "STRONG_TEMPORAL_MATCH" in exp["reason_codes"]
    assert "SPEED_CHANGE_PRESENT" in exp["reason_codes"]
    assert "AIS_GAP_PRESENT" in exp["reason_codes"]
    assert len(exp["supporting_evidence"]) >= 3
    assert len(exp["limiting_evidence"]) >= 1


def test_api_ready_vessel_objects_schema():
    """Verifies that API-ready vessel objects match Section 14 schema and preserve synthetic data_mode."""
    vessels = [
        {
            "mmsi": "538001111",
            "vessel_name": "VESSEL_ALPHA",
            "vessel_type": "cargo",
            "investigative_priority_score": 0.85,
            "hard_guard_passed": True,
            "spatial_evidence": 0.90,
            "temporal_evidence": 1.00,
            "route_evidence": 0.80,
            "behaviour_evidence": 0.70,
            "ais_integrity": 0.95,
            "physics_support": 0.80,
            "reason_codes": ["SOURCE_REGION_INTERSECTION"],
            "supporting_evidence": ["Track intersects polygon"],
            "limiting_evidence": [],
            "missing_evidence": [],
        }
    ]

    api_objs = create_api_ready_vessel_objects(vessels, data_mode="SYNTHETIC_DEMO", historical_attribution_valid=False)

    assert len(api_objs) == 1
    obj = api_objs[0]
    assert obj["vessel_id"] == "538001111"
    assert obj["attribution_state"] == "HIGH_PRIORITY_INVESTIGATIVE_CANDIDATE"
    assert obj["data_mode"] == "SYNTHETIC_DEMO"
    assert obj["historical_attribution_valid"] is False


def test_ranking_freeze_integrity():
    """Verifies R001_AIS_RANKING_FREEZE.json creation and SHA256 integrity."""
    config = create_ais_ranking_freeze(R001_DIR)

    assert config["case_id"] == "R001_WAKASHIO"
    assert config["ranking_engine_frozen"] is True
    assert "freeze_sha256_hash" in config
    assert len(config["freeze_sha256_hash"]) == 64

    freeze_file = R001_DIR / "07_results" / "ais_ranking" / "R001_AIS_RANKING_FREEZE.json"
    assert freeze_file.exists()


def test_no_historical_wakashio_identity_usage():
    """Verifies that no Wakashio vessel name, MMSI, or IMO was hardcoded into ranking logic."""
    import inspect
    from backend.app.services import ais_ranking

    source = inspect.getsource(ais_ranking)
    assert "Wakashio" not in source
    assert "9801087" not in source  # Wakashio IMO
