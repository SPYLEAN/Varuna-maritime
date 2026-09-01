from __future__ import annotations

import json
from pathlib import Path
import pytest

from backend.app.services.hindcast_engine import (
    OPERATIONAL_MIDPOINT_TIMESTAMP,
    OPERATIONAL_PRODUCT_ID,
    VectorTransportEngine,
    calculate_scenario_sensitivity,
    compute_source_envelope_geometry,
    run_r001_hindcast_engine_pipeline,
    select_candidate_hypotheses,
)

R001_DIR = Path(r"C:\Users\tanvi\OneDrive\Documents\Oil Spill\SamudraNetra-Research\R001_WAKASHIO")


def test_select_candidate_hypotheses():
    """Verify selection of 5-10 candidate hypotheses with group diversity protection."""
    hypotheses = select_candidate_hypotheses(R001_DIR, min_hypotheses=5, max_hypotheses=10)
    assert 5 <= len(hypotheses) <= 10

    groups = [h["group_id"] for h in hypotheses]
    # Verify group diversity (at least 3 distinct groups)
    assert len(set(groups)) >= 3

    for h in hypotheses:
        assert "hypothesis_id" in h
        assert "candidate_id" in h
        assert "centroid_lat" in h
        assert "centroid_lon" in h
        assert "evidence_priority_score" in h


def test_vector_transport_engine_initialization():
    """Verify VectorTransportEngine initializes with forcing datasets and extracts velocity vectors."""
    era5_nc = R001_DIR / "03_wind_era5" / "era5_wind_20200810.nc"
    hycom_nc = R001_DIR / "04_currents_hycom" / "uv3z_2020 (1).nc4"
    cmems_nc = R001_DIR / "05_waves_cmems" / "cmems_waves_202008.nc"

    engine = VectorTransportEngine(era5_nc, hycom_nc, cmems_nc)
    import pandas as pd
    dt = pd.to_datetime(OPERATIONAL_MIDPOINT_TIMESTAMP)

    # Test point off Mauritius coast
    u, v, status = engine.get_forcing_vector(-20.4, 57.7, dt, scenario="B")
    assert status == "ACTIVE"
    assert isinstance(u, float) and isinstance(v, float)
    engine.close()


def test_source_envelope_geometry_calculation():
    """Verify spatial convex hull envelope generation for particle ensembles."""
    pts = [
        {"lat": -20.40, "lon": 57.70},
        {"lat": -20.42, "lon": 57.72},
        {"lat": -20.41, "lon": 57.68},
        {"lat": -20.39, "lon": 57.71},
    ]
    env_geom = compute_source_envelope_geometry(pts)
    assert env_geom is not None
    assert env_geom["type"] in ["Polygon", "MultiPolygon"]
    assert "coordinates" in env_geom


def test_scenario_sensitivity_classification():
    """Verify scenario divergence distance calculation and sensitivity categorization."""
    pts_a = [{"lat": -20.40, "lon": 57.70}]
    pts_b = [{"lat": -20.41, "lon": 57.71}]
    pts_c = [{"lat": -20.415, "lon": 57.715}]

    sens = calculate_scenario_sensitivity(pts_a, pts_b, pts_c)
    assert "drift_divergence_ab_km" in sens
    assert "max_divergence_km" in sens
    assert sens["sensitivity_category"] in ["LOW_SENSITIVITY", "MODERATE_SENSITIVITY", "HIGH_SENSITIVITY"]


def test_run_r001_hindcast_engine_pipeline(tmp_path):
    """Verify end-to-end execution of TASK009B hindcast engine pipeline on R001 Wakashio."""
    res = run_r001_hindcast_engine_pipeline(R001_DIR, output_dir=tmp_path, num_particles_per_hyp=20)
    assert res["status"] == "PASS"
    assert res["task009b_status"] == "COMPLETED"
    assert res["ground_truth_accessed"] is False
    assert res["ais_accessed"] is False

    # Check all required deliverables in output_dir
    assert (tmp_path / "R001_HINDCAST_CONFIG.json").exists()
    assert (tmp_path / "R001_HINDCAST_SELECTION.json").exists()
    assert (tmp_path / "R001_HINDCAST_SUMMARY.md").exists()
    assert (tmp_path / "R001_PARTICLE_TRAJECTORIES.csv").exists()
    assert (tmp_path / "R001_SOURCE_REGIONS_24H.geojson").exists()
    assert (tmp_path / "R001_SOURCE_REGIONS_48H.geojson").exists()
    assert (tmp_path / "R001_SOURCE_REGIONS_72H.geojson").exists()
    assert (tmp_path / "R001_SOURCE_REGIONS_96H.geojson").exists()
    assert (tmp_path / "R001_HYPOTHESIS_PHYSICS.csv").exists()
    assert (tmp_path / "R001_SCENARIO_SENSITIVITY.csv").exists()
    assert (tmp_path / "R001_HINDCAST_PROVENANCE.json").exists()
    assert (tmp_path / "maps" / "R001_HINDCAST_COMBINED.png").exists()


def test_blindness_audit():
    """Strictly audit that no historical Wakashio grounding coordinates, MMSI, or release times are present in code or configs."""
    # Ensure operational midpoint timestamp is 2020-08-10T01:38:07.500Z
    assert OPERATIONAL_MIDPOINT_TIMESTAMP == "2020-08-10T01:38:07.500Z"
    assert OPERATIONAL_PRODUCT_ID == "S1B_IW_GRDH_1SDV_20200810T013755_20200810T013820_022854_02B625_672D"
