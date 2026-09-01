"""
Unit tests for backend/app/services/opendrift_physics_quality_diagnosis.py
"""
import pytest
from pathlib import Path
import pandas as pd
import json

from backend.app.services.opendrift_physics_quality_diagnosis import (
    run_opendrift_physics_quality_diagnosis,
    calculate_source_region_spread_km,
    calculate_polygon_overlap_fraction,
    THRESHOLD_SUPPORTED_ACTIVE_PARTICLES,
    THRESHOLD_SUPPORTED_ACTIVE_FRACTION,
)

R001_DIR = Path(r"C:\Users\tanvi\OneDrive\Documents\Oil Spill\SamudraNetra-Research\R001_WAKASHIO")


def test_quality_thresholds_reachability():
    """Verify numeric quality threshold values and definitions."""
    assert THRESHOLD_SUPPORTED_ACTIVE_PARTICLES == 400
    assert THRESHOLD_SUPPORTED_ACTIVE_FRACTION == 0.80


def test_helper_calculations():
    """Verify source region spread and polygon overlap helpers."""
    pts = [{"lat": -20.0, "lon": 57.0}, {"lat": -20.1, "lon": 57.1}, {"lat": -20.0, "lon": 57.05}]
    spread = calculate_source_region_spread_km(pts)
    assert isinstance(spread, float)
    assert spread > 0.0

    poly_a = {"type": "Polygon", "coordinates": [[[57.0, -20.0], [57.1, -20.0], [57.1, -20.1], [57.0, -20.1], [57.0, -20.0]]]}
    poly_b = {"type": "Polygon", "coordinates": [[[57.05, -20.05], [57.15, -20.05], [57.15, -20.15], [57.05, -20.15], [57.05, -20.05]]]}
    overlap = calculate_polygon_overlap_fraction(poly_a, poly_b)
    assert 0.0 < overlap < 1.0


def test_opendrift_diagnosis_fast_execution(tmp_path):
    """Verify complete TASK009B.3 diagnosis pipeline execution on 1 hypothesis."""
    out_dir = tmp_path / "diagnostics"
    res = run_opendrift_physics_quality_diagnosis(R001_DIR, output_dir=out_dir, num_particles_per_hyp=5, seed=42, max_hypotheses_limit=1)

    assert res["status"] == "PASS"
    assert res["hypotheses_count"] == 1
    assert res["quality_logic_bug"] is False
    assert res["ground_truth_accessed"] is False
    assert res["ais_accessed"] is False
    assert res["ready_for_task009c"] is True

    d_dir = Path(res["deliverables_dir"])
    assert (d_dir / "R001_PHYSICS_QUALITY_DIAGNOSIS.csv").exists()
    assert (d_dir / "R001_PARTICLE_STATUS_BY_HORIZON.csv").exists()
    assert (d_dir / "R001_HORIZON_READINESS_MATRIX.csv").exists()
    assert (d_dir / "R001_FORWARD_VALIDATION_ELIGIBILITY.csv").exists()
    assert (d_dir / "R001_PHYSICS_QUALITY_DIAGNOSIS.json").exists()
    assert (d_dir / "R001_PHYSICS_QUALITY_DIAGNOSIS.md").exists()
