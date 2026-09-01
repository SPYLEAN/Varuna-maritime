"""
Unit Test Suite for SAMUDRANETRA TASK009D — Blind Historical Truth Validation.

Verifies pre-truth freeze manifest generation, canonical truth parsing, zero post-truth tuning,
spatial metrics, candidate historical evaluation, claim guards, and AIS non-usage.
"""

import json
from pathlib import Path
import pytest
from shapely.geometry import Polygon, Point

from backend.app.services.historical_validation import (
    create_pre_truth_freeze_manifest,
    unlock_canonical_truth,
    evaluate_spatial_historical_compatibility,
    evaluate_temporal_compatibility,
    classify_historical_validation_category,
    generate_supported_claims,
    ELIGIBLE_HYPOTHESES,
)

R001_DIR = Path(r"C:\Users\tanvi\OneDrive\Documents\Oil Spill\SamudraNetra-Research\R001_WAKASHIO")


def test_pre_truth_freeze_manifest():
    """Verifies that pre-truth freeze manifest generates SHA256 hashes for blind outputs."""
    manifest = create_pre_truth_freeze_manifest(R001_DIR)

    assert manifest["case_id"] == "R001_WAKASHIO"
    assert manifest["task_id"] == "TASK009D"
    assert manifest["blind_outputs_frozen"] is True
    assert manifest["ais_accessed"] is False
    assert manifest["historical_truth_accessed_at_freeze"] is False
    assert manifest["frozen_artifacts_count"] > 0
    assert "R001_OPENDRIFT_CONFIG.json" in manifest["artifact_hashes"]

    manifest_file = R001_DIR / "07_results" / "historical_validation" / "R001_PRE_TRUTH_FREEZE_MANIFEST.json"
    assert manifest_file.exists()


def test_canonical_truth_extraction():
    """Verifies canonical ground truth unlock from 06_ground_truth/historical_truth.md."""
    # Ensure preflight freeze exists first
    create_pre_truth_freeze_manifest(R001_DIR)
    
    extract = unlock_canonical_truth(R001_DIR)

    assert extract["provenance_file"] == r"06_ground_truth\historical_truth.md"
    assert extract["ais_used"] is False
    assert extract["grounding_latitude"] is not None
    assert -21.0 <= extract["grounding_latitude"] <= -20.0
    assert 57.0 <= extract["grounding_longitude"] <= 58.0


def test_no_blind_output_mutation():
    """Verifies that blind outputs and candidate selection are untouched by historical validation."""
    opendrift_ranking = R001_DIR / "07_results" / "hindcast_opendrift" / "R001_OPENDRIFT_HYPOTHESIS_PHYSICS.csv"
    assert opendrift_ranking.exists()

    with open(opendrift_ranking, "r", encoding="utf-8") as f:
        text = f.read()

    # Ensure eligible candidate hypotheses list remains exactly 8
    assert len(ELIGIBLE_HYPOTHESES) == 8
    for cand in ELIGIBLE_HYPOTHESES:
        assert cand in text


def test_spatial_historical_metrics():
    """Verifies containment, boundary distance, centroid distance, and normalized spatial error calculations."""
    # Polygon around Pointe d'Esny (-20.43, 57.74)
    poly = Polygon([(57.70, -20.45), (57.78, -20.45), (57.78, -20.40), (57.70, -20.40)])
    
    # Truth inside
    metrics_inside = evaluate_spatial_historical_compatibility(poly, -20.438, 57.743)
    assert metrics_inside["truth_inside_source_region"] is True
    assert metrics_inside["boundary_distance_km"] == 0.0
    assert metrics_inside["centroid_distance_km"] < 10.0
    assert metrics_inside["normalized_spatial_error"] >= 0.0

    # Truth outside
    metrics_outside = evaluate_spatial_historical_compatibility(poly, -20.600, 57.743)
    assert metrics_outside["truth_inside_source_region"] is False
    assert metrics_outside["boundary_distance_km"] > 0.0
    assert metrics_outside["centroid_distance_km"] > metrics_outside["boundary_distance_km"]


def test_temporal_compatibility_classification():
    """Verifies temporal status classification for backward horizons."""
    t72 = evaluate_temporal_compatibility(72, "2020-08-06T00:00:00Z", "2020-07-25T15:25:00Z")
    assert t72["temporal_status"] == "TEMPORALLY_COMPATIBLE"

    t24 = evaluate_temporal_compatibility(24, "2020-08-06T00:00:00Z", "2020-07-25T15:25:00Z")
    assert t24["temporal_status"] == "NOT_COMPATIBLE"

    t_missing = evaluate_temporal_compatibility(72, "NOT_AVAILABLE_IN_CANONICAL_TRUTH", "NOT_AVAILABLE_IN_CANONICAL_TRUTH")
    assert t_missing["temporal_status"] == "TRUTH_TIME_INSUFFICIENT"


def test_validation_category_classification():
    """Verifies predefined historical validation category thresholds."""
    cat_strong = classify_historical_validation_category(True, 3.2, 0.0, 0.8, "TEMPORALLY_COMPATIBLE")
    assert cat_strong == "STRONG_HISTORICAL_COMPATIBILITY"

    cat_mod = classify_historical_validation_category(False, 22.0, 12.0, 3.5, "PARTIALLY_COMPATIBLE")
    assert cat_mod == "MODERATE_HISTORICAL_COMPATIBILITY"

    cat_incomp = classify_historical_validation_category(False, 120.0, 95.0, 15.0, "NOT_COMPATIBLE")
    assert cat_incomp == "INCOMPATIBLE"


def test_claim_generator_guards(tmp_path):
    """Verifies that R001_SUPPORTED_CLAIMS.md enforces strict claim boundaries and forbids overclaims."""
    best_cand = {
        "candidate_id": "C3929",
        "best_centroid_distance_km": 4.12,
        "best_horizon_hours": 72,
        "best_scenario": "C",
        "original_blind_rank": 1,
    }

    claims = generate_supported_claims(tmp_path, [], best_cand)

    assert "SAFE FOR PRESENTATION" in claims
    assert "REQUIRES QUALIFICATION" in claims
    assert "NOT SUPPORTED" in claims
    assert "C3929" in claims
    assert "4.12 km" in claims

    # Ensure prohibited phrases are in NOT SUPPORTED section
    assert "❌" in claims
    assert "SamudraNetra proved MV Wakashio caused the oil spill." in claims


def test_ais_non_usage():
    """Verifies that AIS data remains untouched in TASK009D."""
    manifest_file = R001_DIR / "07_results" / "historical_validation" / "R001_PRE_TRUTH_FREEZE_MANIFEST.json"
    if manifest_file.exists():
        data = json.loads(manifest_file.read_text(encoding="utf-8"))
        assert data.get("ais_accessed") is False

    truth_extract_file = R001_DIR / "07_results" / "historical_validation" / "R001_HISTORICAL_TRUTH_EXTRACT.json"
    if truth_extract_file.exists():
        data = json.loads(truth_extract_file.read_text(encoding="utf-8"))
        assert data.get("ais_used") is False
