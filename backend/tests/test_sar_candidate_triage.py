import json
from pathlib import Path
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import Polygon, box, mapping

from backend.app.services.sar_candidate_triage import (
    load_coastline_land_geom,
    triage_sar_candidates,
)


def write_synthetic_geotiff(
    path: Path, array: np.ndarray, transform=None, crs: str = "EPSG:4326"
):
    transform = transform or from_origin(57.0, -20.0, 0.001, 0.001)
    height, width = array.shape
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=1,
        dtype=array.dtype,
        crs=crs,
        transform=transform,
    ) as dst:
        dst.write(array, 1)


def write_synthetic_coastline_geojson(path: Path, land_polys: list[Polygon]):
    features = [
        {"type": "Feature", "geometry": mapping(p), "properties": {"name": "TestLand"}}
        for p in land_polys
    ]
    geojson_dict = {"type": "FeatureCollection", "features": features}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(geojson_dict, f, indent=2)


def write_synthetic_candidates_geojson(path: Path, candidates: list[dict]):
    features = []
    for c in candidates:
        poly_geom = c["polygon"]
        props = {k: v for k, v in c.items() if k != "polygon"}
        features.append({"type": "Feature", "geometry": poly_geom, "properties": props})

    geojson_dict = {"type": "FeatureCollection", "features": features}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(geojson_dict, f, indent=2)


def test_land_polygon_rasterization_and_coastal_buffer(tmp_path):
    vv_p = tmp_path / "vv.tif"
    vh_p = tmp_path / "vh.tif"
    write_synthetic_geotiff(vv_p, np.full((100, 100), -12.0, dtype=np.float32))
    write_synthetic_geotiff(vh_p, np.full((100, 100), -18.0, dtype=np.float32))

    coast_p = tmp_path / "coast.geojson"
    land_poly = box(57.0, -20.02, 57.02, -20.0)
    write_synthetic_coastline_geojson(coast_p, [land_poly])

    cand_p = tmp_path / "candidates.geojson"
    cand_1 = {
        "candidate_id": "C001",
        "polygon": mapping(box(57.05, -20.05, 57.06, -20.04)),
        "area_km2": 1.2,
        "pixel_count": 100,
        "centroid_lat": -20.045,
        "centroid_lon": 57.055,
        "bounds": [57.05, -20.05, 57.06, -20.04],
        "candidate_score": 80.0,
        "sar_evidence": {"local_vv_contrast_db": 5.0, "median_vv_db": -16.0},
        "morphology": {"elongation": 2.5, "compactness": 0.3},
        "context": {"touches_invalid_region": False},
    }
    cand_2 = {
        "candidate_id": "C002",
        "polygon": mapping(box(57.005, -20.015, 57.015, -20.005)),
        "area_km2": 0.8,
        "pixel_count": 60,
        "centroid_lat": -20.01,
        "centroid_lon": 57.01,
        "bounds": [57.005, -20.015, 57.015, -20.005],
        "candidate_score": 75.0,
        "sar_evidence": {"local_vv_contrast_db": 4.5, "median_vv_db": -16.0},
        "morphology": {"elongation": 2.0, "compactness": 0.4},
        "context": {"touches_invalid_region": False},
    }
    write_synthetic_candidates_geojson(cand_p, [cand_1, cand_2])

    out_dir = tmp_path / "triaged_out"
    res = triage_sar_candidates(
        cand_p, vv_p, vh_p, coastline_geojson_path=coast_p, output_dir=out_dir
    )

    assert res["status"] == "PASS"
    assert (out_dir / "R001_OCEAN_MASK.tif").exists()
    assert (out_dir / "R001_TRIAGED_CANDIDATES.geojson").exists()
    assert (out_dir / "R001_PRIMARY_REVIEW.csv").exists()
    assert (out_dir / "R001_TRIAGE_INTEGRITY_AUDIT.json").exists()

    cands = res["candidates"]
    c1 = next(c for c in cands if c["candidate_id"] == "C001")
    c2 = next(c for c in cands if c["candidate_id"] == "C002")

    assert c1["triage_tier"] == "PRIMARY_REVIEW"
    assert c1["land_overlap_fraction"] == 0.0
    assert c1["distance_to_land_m"] > 3000.0
    assert c1["nearshore_context"] is False

    assert c2["land_overlap_fraction"] > 0.0 or c2["location_category"] in ("on_land", "coastal_buffer")


def test_candidate_grouping_and_identity_preservation(tmp_path):
    vv_p = tmp_path / "vv.tif"
    vh_p = tmp_path / "vh.tif"
    write_synthetic_geotiff(vv_p, np.full((100, 100), -12.0, dtype=np.float32))
    write_synthetic_geotiff(vh_p, np.full((100, 100), -18.0, dtype=np.float32))

    coast_p = tmp_path / "coast.geojson"
    write_synthetic_coastline_geojson(coast_p, [box(56.0, -21.0, 56.1, -20.9)])

    cand_p = tmp_path / "candidates.geojson"
    cand_1 = {
        "candidate_id": "C001",
        "polygon": mapping(box(57.05, -20.05, 57.055, -20.045)),
        "area_km2": 0.5,
        "pixel_count": 50,
        "centroid_lat": -20.0475,
        "centroid_lon": 57.0525,
        "bounds": [57.05, -20.05, 57.055, -20.045],
        "candidate_score": 80.0,
        "sar_evidence": {"local_vv_contrast_db": 5.0},
        "morphology": {"elongation": 2.0, "orientation_deg": 45.0},
        "context": {"touches_invalid_region": False},
    }
    cand_2 = {
        "candidate_id": "C002",
        "polygon": mapping(box(57.056, -20.044, 57.06, -20.04)),
        "area_km2": 0.4,
        "pixel_count": 40,
        "centroid_lat": -20.042,
        "centroid_lon": 57.058,
        "bounds": [57.056, -20.044, 57.06, -20.04],
        "candidate_score": 78.0,
        "sar_evidence": {"local_vv_contrast_db": 4.8},
        "morphology": {"elongation": 1.9, "orientation_deg": 48.0},
        "context": {"touches_invalid_region": False},
    }
    write_synthetic_candidates_geojson(cand_p, [cand_1, cand_2])

    out_dir = tmp_path / "triaged_out"
    res = triage_sar_candidates(
        cand_p, vv_p, vh_p, coastline_geojson_path=coast_p, output_dir=out_dir
    )

    cands = res["candidates"]
    c1 = next(c for c in cands if c["candidate_id"] == "C001")
    c2 = next(c for c in cands if c["candidate_id"] == "C002")

    # Original candidate identity preserved
    assert c1["candidate_id"] == "C001"
    assert c2["candidate_id"] == "C002"
    # Grouping assigned
    assert c1["candidate_group_id"] == c2["candidate_group_id"]


def test_triage_integrity_audit_metrics(tmp_path):
    vv_p = tmp_path / "vv.tif"
    vh_p = tmp_path / "vh.tif"
    write_synthetic_geotiff(vv_p, np.full((100, 100), -12.0, dtype=np.float32))
    write_synthetic_geotiff(vh_p, np.full((100, 100), -18.0, dtype=np.float32))

    coast_p = tmp_path / "coast.geojson"
    write_synthetic_coastline_geojson(coast_p, [box(56.0, -21.0, 56.1, -20.9)])

    cand_p = tmp_path / "candidates.geojson"
    cand_1 = {
        "candidate_id": "C001",
        "polygon": mapping(box(57.05, -20.05, 57.06, -20.04)),
        "area_km2": 1.2,
        "pixel_count": 100,
        "centroid_lat": -20.045,
        "centroid_lon": 57.055,
        "bounds": [57.05, -20.05, 57.06, -20.04],
        "candidate_score": 85.0,
        "sar_evidence": {"local_vv_contrast_db": 5.5},
        "morphology": {"elongation": 2.2},
        "context": {"touches_invalid_region": False},
    }
    write_synthetic_candidates_geojson(cand_p, [cand_1])

    out_dir = tmp_path / "triaged_out"
    res = triage_sar_candidates(
        cand_p, vv_p, vh_p, coastline_geojson_path=coast_p, output_dir=out_dir
    )

    t_stats = res["triage_statistics"]
    audit = res["integrity_audit"]

    # Nonzero primary pixel fraction audit
    assert t_stats["primary_pixel_union_count"] > 0
    assert t_stats["primary_pixel_fraction_total"] > 0.0
    assert t_stats["primary_pixel_fraction_valid"] > 0.0
    assert t_stats["primary_pixel_fraction_ocean"] > 0.0
    assert audit["area_pixel_consistency_pass"] is True
