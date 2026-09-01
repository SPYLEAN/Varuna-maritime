"""
Unit Test Suite for SAMUDRANETRA TASK010A — Blind AIS Ingestion + Spatiotemporal Retrieval.

Verifies clean-room enforcement, truth file inaccessibility, AIS schema validation,
track reconstruction, geodesic polygon distance, temporal compatibility, behavioural extraction,
AIS gap handling, zero-candidate support, and absence of guilt attribution language.
"""

import json
from pathlib import Path
import pytest
from shapely.geometry import Polygon

from backend.app.services.ais_engine import (
    create_ais_clean_room_manifest,
    perform_ais_data_inventory,
    validate_and_clean_ais_records,
    reconstruct_vessel_tracks,
    compute_source_region_intersections,
    evaluate_ais_temporal_compatibility,
    extract_vessel_behavioural_features,
    compute_ais_evidence_scores,
    generate_synthetic_demo_ais,
    AISMessage,
    ELIGIBLE_HYPOTHESES,
)

R001_DIR = Path(r"C:\Users\tanvi\OneDrive\Documents\Oil Spill\SamudraNetra-Research\R001_WAKASHIO")


def test_clean_room_enforcement_and_manifest():
    """Verifies that clean-room manifest hashes pre-truth outputs and locks forbidden truth fields."""
    manifest = create_ais_clean_room_manifest(R001_DIR)

    assert manifest["clean_room_protocol_enforced"] is True
    assert manifest["pre_truth_physical_outputs_frozen"] is True
    assert "wakashio_vessel_name" in manifest["forbidden_truth_fields"]
    assert "historical_mmsi" in manifest["forbidden_truth_fields"]
    assert "R001_HISTORICAL_TRUTH_EXTRACT.json" in manifest["forbidden_truth_fields"]
    assert len(manifest["artifact_hashes"]) > 0

    manifest_path = R001_DIR / "07_results" / "ais" / "R001_AIS_CLEAN_ROOM_MANIFEST.json"
    assert manifest_path.exists()


def test_ais_data_inventory_and_requirements():
    """Verifies data inventory output and real AIS requirements markdown generation."""
    inv = perform_ais_data_inventory(R001_DIR)

    assert inv["case_id"] == "R001_WAKASHIO"
    assert inv["ais_data_available"] in ["NO", "PARTIAL", "YES"]
    assert len(inv["known_commercial_providers"]) >= 3

    req_file = R001_DIR / "07_results" / "ais" / "R001_AIS_REAL_DATA_REQUIREMENTS.md"
    assert req_file.exists()
    assert "Kpler / MarineTraffic" in req_file.read_text(encoding="utf-8")


def test_ais_schema_and_validation():
    """Verifies coordinate checks, MMSI syntax validation, SOG/COG bounds, and duplicate detection."""
    records = [
        # Valid record
        {"timestamp_utc": "2020-08-08T10:00:00Z", "mmsi": "538009999", "latitude": -20.5, "longitude": 57.5, "sog_knots": 10.0, "cog_deg": 45.0},
        # Duplicate record
        {"timestamp_utc": "2020-08-08T10:00:00Z", "mmsi": "538009999", "latitude": -20.5, "longitude": 57.5, "sog_knots": 10.0, "cog_deg": 45.0},
        # Out of bounds lat
        {"timestamp_utc": "2020-08-08T11:00:00Z", "mmsi": "538009999", "latitude": -95.0, "longitude": 57.5, "sog_knots": 10.0, "cog_deg": 45.0},
        # Invalid MMSI
        {"timestamp_utc": "2020-08-08T12:00:00Z", "mmsi": "123", "latitude": -20.5, "longitude": 57.5, "sog_knots": 10.0, "cog_deg": 45.0},
        # Impossible SOG
        {"timestamp_utc": "2020-08-08T13:00:00Z", "mmsi": "538009999", "latitude": -20.5, "longitude": 57.5, "sog_knots": 85.0, "cog_deg": 45.0},
    ]

    clean_msgs, anomalies = validate_and_clean_ais_records(records)

    assert len(clean_msgs) == 5
    assert clean_msgs[0].record_quality == "VALID"
    assert "DUPLICATE_RECORD" in clean_msgs[1].record_quality
    assert "LAT_LON_OUT_OF_BOUNDS" in clean_msgs[2].record_quality
    assert "INVALID_MMSI_FORMAT" in clean_msgs[3].record_quality
    assert "IMPOSSIBLE_SOG" in clean_msgs[4].record_quality
    assert len(anomalies) == 4


def test_vessel_track_reconstruction_and_gap_handling():
    """Verifies track grouping, duration, median gap, and max reporting gap calculation."""
    msgs = [
        AISMessage("2020-08-08T00:00:00Z", "538001111", -20.5, 57.5, 10.0, 45.0),
        AISMessage("2020-08-08T01:00:00Z", "538001111", -20.4, 57.6, 10.0, 45.0),
        # 5-hour gap
        AISMessage("2020-08-08T06:00:00Z", "538001111", -20.0, 58.0, 10.0, 45.0),
    ]

    tracks = reconstruct_vessel_tracks(msgs)

    assert len(tracks) == 1
    trk = tracks[0]
    assert trk["mmsi"] == "538001111"
    assert trk["duration_hours"] == 6.0
    assert trk["record_count"] == 3
    assert trk["max_reporting_gap_hours"] == 5.0
    assert trk["has_large_gap"] is True


def test_geodesic_source_region_intersection():
    """Verifies minimum geodesic distance to source region polygon and containment."""
    poly = Polygon([(57.4, -20.5), (57.6, -20.5), (57.6, -20.3), (57.4, -20.3)])
    envelopes_geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"candidate_id": "C3929", "horizon_hours": 72, "centroid_lat": -20.4, "centroid_lon": 57.5},
                "geometry": {"type": "Polygon", "coordinates": [[[57.4, -20.5], [57.6, -20.5], [57.6, -20.3], [57.4, -20.3], [57.4, -20.5]]]}
            }
        ]
    }

    # Point inside polygon
    msgs_inside = [AISMessage("2020-08-08T10:00:00Z", "538001111", -20.4, 57.5, 10.0, 45.0)]
    tracks_inside = reconstruct_vessel_tracks(msgs_inside)
    ix_inside = compute_source_region_intersections(tracks_inside, envelopes_geojson, spatial_buffer_km=10.0)

    assert len(ix_inside) == 1
    assert ix_inside[0]["intersects_source_region"] is True
    assert ix_inside[0]["min_geodesic_distance_km"] == 0.0

    # Point outside polygon
    msgs_outside = [AISMessage("2020-08-08T10:00:00Z", "538002222", -21.0, 57.5, 10.0, 45.0)]
    tracks_outside = reconstruct_vessel_tracks(msgs_outside)
    ix_outside = compute_source_region_intersections(tracks_outside, envelopes_geojson, spatial_buffer_km=10.0)

    assert len(ix_outside) == 1
    assert ix_outside[0]["min_geodesic_distance_km"] > 50.0


def test_temporal_compatibility():
    """Verifies horizon time window overlap classification."""
    # Window for 72h horizon relative to 2020-08-10T01:38:07.500Z -> starts 2020-08-07T01:38:07Z
    t_comp = evaluate_ais_temporal_compatibility("2020-08-07T10:00:00Z", "2020-08-09T10:00:00Z", 72)
    assert t_comp["temporal_status"] == "TEMPORALLY_COMPATIBLE"
    assert t_comp["overlap_hours"] > 30.0

    t_incomp = evaluate_ais_temporal_compatibility("2020-08-01T00:00:00Z", "2020-08-02T00:00:00Z", 72)
    assert t_incomp["temporal_status"] == "NOT_COMPATIBLE"


def test_behavioural_and_gap_feature_extraction():
    """Verifies SOG, COG, and AIS gap feature extraction with investigative disclaimer."""
    msgs = [
        AISMessage("2020-08-08T00:00:00Z", "538001111", -20.5, 57.5, 12.0, 45.0),
        AISMessage("2020-08-08T01:00:00Z", "538001111", -20.4, 57.6, 2.0, 150.0),  # Slowdown & sharp turn
        AISMessage("2020-08-08T06:00:00Z", "538001111", -20.0, 58.0, 11.0, 45.0),  # 5h gap
    ]
    tracks = reconstruct_vessel_tracks(msgs)
    behav = extract_vessel_behavioural_features(tracks[0])

    assert behav["slowdown_event_detected"] is True
    assert behav["cog_sharp_turns_count"] >= 1
    assert behav["ais_gap_evidence"] == "EXTENDED_SILENCE_INTERVAL"
    assert "INVESTIGATIVE INDICATORS ONLY" in behav["investigative_note"]


def test_no_guilt_language_output():
    """Verifies that AIS evidence output contains individual component scores without guilt probability."""
    raw = generate_synthetic_demo_ais()
    clean_msgs, _ = validate_and_clean_ais_records(raw)
    tracks = reconstruct_vessel_tracks(clean_msgs)
    
    poly = Polygon([(57.0, -21.0), (59.0, -21.0), (59.0, -19.5), (57.0, -19.5)])
    envelopes_geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"candidate_id": "C3929", "horizon_hours": 72, "centroid_lat": -20.4, "centroid_lon": 57.5},
                "geometry": {"type": "Polygon", "coordinates": [[[57.0, -21.0], [59.0, -21.0], [59.0, -19.5], [57.0, -19.5], [57.0, -21.0]]]}
            }
        ]
    }
    
    ixs = compute_source_region_intersections(tracks, envelopes_geojson)
    scores = compute_ais_evidence_scores(ixs, tracks)

    assert len(scores) > 0
    for s in scores:
        assert "spatial_compatibility_score" in s
        assert "temporal_compatibility_score" in s
        # Ensure forbidden guilt terms are absent from keys
        assert "guilt_probability" not in s
        assert "culprit_probability" not in s
        assert "guilt_confidence" not in s
        assert "NO GUILT ATTRIBUTION ASSIGNED" in s["attribution_note"]


def test_zero_candidate_outcome():
    """Verifies graceful handling when zero vessels intersect source envelopes."""
    tracks = []
    envelopes_geojson = {"type": "FeatureCollection", "features": []}

    ixs = compute_source_region_intersections(tracks, envelopes_geojson)
    scores = compute_ais_evidence_scores(ixs, tracks)

    assert len(ixs) == 0
    assert len(scores) == 0
