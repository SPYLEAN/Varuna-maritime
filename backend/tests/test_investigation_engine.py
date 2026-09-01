"""
Unit Test Suite for SAMUDRANETRA TASK011 — Investigation Engine & Evidence Fusion.

Verifies unified case generation, evidence provenance, synthetic AIS label propagation,
historical validation isolation, absence of guilt wording, decoupled evidence fusion,
timeline playback contract, and GeoJSON validity.
"""

import json
from pathlib import Path
import pytest

from backend.app.services.investigation_engine import (
    build_unified_investigation_case,
    build_evidence_fusion_table,
    build_investigation_timeline,
    build_investigation_geojson,
    build_limitation_matrix,
    generate_human_readable_explanations,
)

R001_DIR = Path(r"C:\Users\tanvi\OneDrive\Documents\Oil Spill\SamudraNetra-Research\R001_WAKASHIO")


def test_unified_case_generation_and_schema():
    """Verifies canonical case object fields, sub-objects, and metadata."""
    c = build_unified_investigation_case(R001_DIR)

    assert c["case_id"] == "R001_WAKASHIO"
    assert "MV Wakashio" in c["case_name"]
    assert c["observation_timestamp"] == "2020-08-10T01:38:07.500Z"
    assert "S1B_IW_GRDH" in c["satellite_product_id"]

    assert "sar" in c
    assert "physics" in c
    assert "historical_validation" in c
    assert "ais" in c
    assert "investigation" in c

    assert c["sar"]["candidate_count"] == 8
    assert c["physics"]["hindcast_status"] == "PHYSICS_UNCERTAIN"


def test_synthetic_ais_label_and_historical_attribution_guards():
    """Verifies synthetic AIS label propagation and false attribution guards."""
    c = build_unified_investigation_case(R001_DIR)

    assert c["ais"]["data_mode"] == "SYNTHETIC_DEMO"
    assert c["ais"]["historical_ais_available"] is False
    assert c["ais"]["historical_attribution_valid"] is False
    assert "Synthetic AIS demonstration" in c["ais"]["presentation_guard"]


def test_historical_validation_isolation():
    """Verifies that historical ground truth is isolated with post_freeze_only = true."""
    c = build_unified_investigation_case(R001_DIR)
    hv = c["historical_validation"]

    assert hv["available"] is True
    assert hv["post_freeze_only"] is True
    assert "Unlocked ONLY after cryptographic pre-truth freezing" in hv["isolation_note"]


def test_absence_of_guilt_wording():
    """Verifies that forbidden guilt terms are absent from unified case object."""
    c = build_unified_investigation_case(R001_DIR)
    text = json.dumps(c)

    forbidden_terms = ["CULPRIT_CONFIRMED", "GUILTY", "CAUSE_PROVEN", "99% RESPONSIBLE"]
    for term in forbidden_terms:
        assert term not in text


def test_decoupled_evidence_fusion_table():
    """Verifies multi-component evidence separation and strength/uncertainty metrics."""
    table = build_evidence_fusion_table(R001_DIR)

    assert len(table) >= 8
    components = [row["component"] for row in table]
    assert "SAR_CANDIDATES" in components
    assert "PHYSICS_HINDCAST" in components
    assert "FORWARD_CLOSURE" in components
    assert "AIS_SPATIAL" in components

    for row in table:
        assert 0.0 <= row["evidence_strength"] <= 1.0
        assert 0.0 <= row["uncertainty"] <= 1.0


def test_timeline_playback_contract():
    """Verifies T-96h to T0 timeline ordering and contract fields."""
    timeline = build_investigation_timeline(R001_DIR)

    assert len(timeline) == 5
    step_ids = [t["step_id"] for t in timeline]
    assert step_ids == ["T-96", "T-72", "T-48", "T-24", "T0"]

    for step in timeline:
        assert "horizon_hours" in step
        assert "timestamp_utc" in step
        assert "active_particle_count" in step
        assert "quality_status" in step


def test_investigation_geojson_validity():
    """Verifies GeoJSON FeatureCollection structure and layers."""
    geojson = build_investigation_geojson(R001_DIR)

    assert geojson["type"] == "FeatureCollection"
    assert geojson["case_id"] == "R001_WAKASHIO"
    assert len(geojson["features"]) > 0

    layers = [f["properties"]["layer"] for f in geojson["features"]]
    assert "HISTORICAL_GROUNDING_POINT" in layers


def test_human_readable_explanations():
    """Verifies explanation generator produces deterministic reason summaries."""
    c = build_unified_investigation_case(R001_DIR)
    exp = generate_human_readable_explanations(c)

    assert "WHY_THIS_CANDIDATE_RANKS_HIGH" in exp
    assert "WHY_EVIDENCE_IS_UNCERTAIN" in exp
    assert "SYNTHETIC_DEMO" in exp["WHY_THIS_CANDIDATE_RANKS_HIGH"]


def test_limitation_matrix_scenarios():
    """Verifies limitation matrix edge state API examples."""
    lim = build_limitation_matrix(R001_DIR)

    scenarios = lim["limitation_scenarios"]
    assert "synthetic_ais_demo" in scenarios
    assert "missing_ais_data" in scenarios
    assert "no_credible_vessel" in scenarios
    assert "ambiguous_attribution" in scenarios
