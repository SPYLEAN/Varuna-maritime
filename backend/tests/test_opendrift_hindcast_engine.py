from __future__ import annotations

import json
from pathlib import Path
import pytest
import numpy as np

import opendrift
from opendrift.models.oceandrift import OceanDrift

from backend.app.services.opendrift_hindcast_engine import (
    sample_initial_particle_positions,
    run_r001_opendrift_production_pipeline,
)
from backend.app.services.hindcast_engine import select_candidate_hypotheses

R001_DIR = Path(r"C:\Users\tanvi\OneDrive\Documents\Oil Spill\SamudraNetra-Research\R001_WAKASHIO")


def test_opendrift_class_and_import():
    """Verify actual OpenDrift OceanDrift class instantiation without fallback."""
    o = OceanDrift(loglevel=50)
    assert type(o) is OceanDrift
    assert o.__class__.__module__ == "opendrift.models.oceandrift"
    assert opendrift.__version__ == "1.14.11"


def test_particle_seeding_reproducibility():
    """Verify 500 particle polygon ensemble sampling is deterministic across scenarios with seed=42."""
    hypotheses = select_candidate_hypotheses(R001_DIR)
    seeded_1 = sample_initial_particle_positions(hypotheses, num_particles_per_hyp=500, seed=42)
    seeded_2 = sample_initial_particle_positions(hypotheses, num_particles_per_hyp=500, seed=42)

    for h_id in seeded_1:
        lats_1, lons_1 = seeded_1[h_id]
        lats_2, lons_2 = seeded_2[h_id]
        assert len(lats_1) == 500
        assert np.allclose(lats_1, lats_2)
        assert np.allclose(lons_1, lons_2)


def test_opendrift_production_pipeline_execution(tmp_path):
    """Verify complete TASK009B.2 production pipeline execution generating all deliverables."""
    out_dir = tmp_path / "hindcast_opendrift"
    res = run_r001_opendrift_production_pipeline(R001_DIR, output_dir=out_dir, num_particles_per_hyp=5, seed=42, max_hypotheses_limit=1)

    assert res["status"] == "PASS"
    assert res["task009b2_status"] == "COMPLETED"
    assert res["ground_truth_accessed"] is False
    assert res["ais_accessed"] is False

    out_d = R001_DIR / "07_results" / "hindcast_opendrift"
    assert (out_d / "R001_OPENDRIFT_CONFIG.json").exists()
    assert (out_d / "R001_OPENDRIFT_SELECTION.json").exists()
    assert (out_d / "R001_OPENDRIFT_SUMMARY.md").exists()
    assert (out_d / "R001_OPENDRIFT_PARTICLE_TRAJECTORIES.csv").exists()
    assert (out_d / "R001_OPENDRIFT_SOURCE_REGIONS_24H.geojson").exists()
    assert (out_d / "R001_OPENDRIFT_SOURCE_REGIONS_48H.geojson").exists()
    assert (out_d / "R001_OPENDRIFT_SOURCE_REGIONS_72H.geojson").exists()
    assert (out_d / "R001_OPENDRIFT_SOURCE_REGIONS_96H.geojson").exists()
    assert (out_d / "R001_OPENDRIFT_HYPOTHESIS_PHYSICS.csv").exists()
    assert (out_d / "R001_OPENDRIFT_SCENARIO_SENSITIVITY.csv").exists()
    assert (out_d / "R001_CUSTOM_VS_OPENDRIFT_COMPARISON.csv").exists()
    assert (out_d / "R001_OPENDRIFT_PROVENANCE.json").exists()
