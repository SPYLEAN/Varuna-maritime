from __future__ import annotations

from pathlib import Path
import pytest
import numpy as np
from shapely.geometry import Polygon, box

from backend.app.services.opendrift_forward_validation import (
    reconcile_c028_accounting,
    freeze_task009b_inputs,
    sample_source_region_ensemble,
    calculate_arrival_metrics,
    classify_forward_closure_quality,
    perform_blindness_audit,
    run_task009c_forward_validation_pipeline,
    ELIGIBLE_CANDIDATE_IDS,
    EXCLUDED_CANDIDATE_IDS,
    ROBUSTNESS_SEED,
)

R001_DIR = Path(r"C:\Users\tanvi\OneDrive\Documents\Oil Spill\SamudraNetra-Research\R001_WAKASHIO")


def test_c028_accounting_reconciliation():
    """Verify C028 preflight audit reconciliation (Active=46, Stranded=454, Total=500)."""
    res = reconcile_c028_accounting(R001_DIR)
    assert res["candidate_id"] == "C028"
    assert res["active"] == 46
    assert res["stranded"] == 454
    assert res["total_particles"] == 500
    assert res["active"] + res["stranded"] == 500
    assert res["total_equals_500"] is True
    assert res["underlying_hindcast_altered"] is False
    assert res["excluded_from_forward_validation"] is True


def test_frozen_input_hash_verification(tmp_path):
    """Verify SHA256 input freeze generation and verification."""
    freeze_d = tmp_path / "freeze"
    res = freeze_task009b_inputs(R001_DIR, freeze_d)
    assert res["case_id"] == "R001_WAKASHIO"
    assert len(res["frozen_file_hashes_sha256"]) > 0
    assert (freeze_d / "R001_FORWARD_INPUT_FREEZE.json").exists()


def test_eligible_hypotheses_filtering():
    """Verify only 8 eligible hypotheses are used and C3833 / C028 are excluded."""
    assert len(ELIGIBLE_CANDIDATE_IDS) == 8
    assert "C3929" in ELIGIBLE_CANDIDATE_IDS
    assert "C001" in ELIGIBLE_CANDIDATE_IDS
    assert "C4053" in ELIGIBLE_CANDIDATE_IDS
    assert "C3833" in EXCLUDED_CANDIDATE_IDS
    assert "C028" in EXCLUDED_CANDIDATE_IDS
    assert "C3833" not in ELIGIBLE_CANDIDATE_IDS
    assert "C028" not in ELIGIBLE_CANDIDATE_IDS


def test_independent_source_region_resampling():
    """Verify independent source-region particle ensemble sampling with fixed seed 314159."""
    poly = box(57.5, -20.5, 57.7, -20.3)
    lats, lons = sample_source_region_ensemble(poly, num_particles=500, seed=ROBUSTNESS_SEED)

    assert len(lats) == 500
    assert len(lons) == 500
    assert isinstance(lats, np.ndarray)
    assert isinstance(lons, np.ndarray)

    # Repeat with same seed to verify deterministic reproducible sampling
    lats_repeat, lons_repeat = sample_source_region_ensemble(poly, num_particles=500, seed=ROBUSTNESS_SEED)
    assert np.allclose(lats, lats_repeat)
    assert np.allclose(lons, lons_repeat)


def test_arrival_metrics_calculation():
    """Verify arrival metrics calculation and distance to candidate polygon."""
    cand_poly = box(57.5, -20.5, 57.6, -20.4)
    lats = np.array([-20.45, -20.46, -20.44])
    lons = np.array([57.55, 57.56, 57.54])
    status = np.array([0.0, 0.0, 0.0])

    m = calculate_arrival_metrics(lats, lons, status, cand_poly)
    assert m["active_count"] == 3
    assert m["active_fraction"] == 1.0
    assert m["inside_candidate_fraction"] == 1.0
    assert m["centroid_distance_km"] >= 0.0
    assert m["equivalent_radius_km"] > 0.0
    assert m["normalized_centroid_error"] >= 0.0


def test_closure_quality_classification():
    """Verify predeclared quality classification thresholds."""
    metrics_good = {
        "active_fraction": 1.0,
        "centroid_distance_km": 5.0,
        "within_2km_fraction": 0.8,
        "p90_distance_km": 10.0,
    }
    assert classify_forward_closure_quality(metrics_good, "SUPPORTED") == "GOOD_CLOSURE"

    metrics_poor = {
        "active_fraction": 1.0,
        "centroid_distance_km": 45.0,
        "within_2km_fraction": 0.0,
        "p90_distance_km": 50.0,
    }
    assert classify_forward_closure_quality(metrics_poor, "UNCERTAIN") == "POOR_CLOSURE"

    metrics_insuf = {
        "active_fraction": 0.1,
        "centroid_distance_km": 5.0,
        "within_2km_fraction": 0.0,
        "p90_distance_km": 10.0,
    }
    assert classify_forward_closure_quality(metrics_insuf, "INSUFFICIENT_DATA") == "INSUFFICIENT_DATA"


def test_blindness_audit():
    """Verify ground truth and AIS isolation blindness audit."""
    audit = perform_blindness_audit(R001_DIR)
    assert audit["ground_truth_accessed"] is False
    assert audit["ais_accessed"] is False
    assert audit["status"] in ["PASS", "FAIL"]


def test_task009c_fast_pipeline_execution(tmp_path):
    """Verify complete TASK009C forward validation pipeline fast execution on 1 hypothesis."""
    out_dir = tmp_path / "forward_validation"
    res = run_task009c_forward_validation_pipeline(
        R001_DIR,
        output_dir=out_dir,
        num_particles_per_ensemble=5,
        seed=314159,
        max_hypotheses_limit=1,
    )

    assert res["status"] == "PASS"
    assert res["c028_reconciled"] is True
    assert res["frozen_inputs_verified"] is True
    assert res["eligible_hypotheses_count"] == 1
    assert res["blindness_audit"] == "PASS"
    assert res["ready_for_blind_truth_validation"] == "YES"

    d_dir = Path(res["deliverables_dir"])
    assert (d_dir / "R001_FORWARD_CONFIG.json").exists()
    assert (d_dir / "R001_FORWARD_INPUT_FREEZE.json").exists()
    assert (d_dir / "R001_FORWARD_ELIGIBILITY.json").exists()
    assert (d_dir / "R001_NUMERICAL_CLOSURE_METRICS.csv").exists()
    assert (d_dir / "R001_SOURCE_REGION_ROBUSTNESS_METRICS.csv").exists()
    assert (d_dir / "R001_FORWARD_SCENARIO_SENSITIVITY.csv").exists()
    assert (d_dir / "R001_FORWARD_HORIZON_SUMMARY.csv").exists()
    assert (d_dir / "R001_FORWARD_PARTICLE_STATUS.csv").exists()
    assert (d_dir / "R001_FORWARD_ARRIVAL_ENVELOPES.geojson").exists()
    assert (d_dir / "R001_FORWARD_SUMMARY.md").exists()
    assert (d_dir / "R001_FORWARD_PROVENANCE.json").exists()
