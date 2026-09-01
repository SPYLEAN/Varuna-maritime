import json
from pathlib import Path
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box, mapping

from backend.app.services.sar_candidate_ml_pipeline import (
    normalize_sar_db,
    process_candidate_ml_inputs,
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


def write_synthetic_candidates_geojson(path: Path, candidates: list[dict]):
    features = []
    for c in candidates:
        poly_geom = c["polygon"]
        props = {k: v for k, v in c.items() if k != "polygon"}
        features.append({"type": "Feature", "geometry": poly_geom, "properties": props})

    geojson_dict = {"type": "FeatureCollection", "features": features}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(geojson_dict, f, indent=2)


def test_sar_db_physical_normalization():
    vv_data = np.array([-35.0, -30.0, -15.0, 0.0, 5.0, np.nan], dtype=np.float32)
    norm, clip_frac = normalize_sar_db(vv_data, (-30.0, 0.0))

    assert norm[1] == pytest.approx(0.0, abs=1e-5)
    assert norm[2] == pytest.approx(0.5, abs=1e-3)
    assert norm[3] == pytest.approx(1.0, abs=1e-5)
    assert norm[0] == 0.0  # -35 dB clipped to 0.0
    assert norm[4] == 1.0  # 5 dB clipped to 1.0
    assert clip_frac > 0.0


def test_candidate_ml_pipeline_extraction_and_contracts(tmp_path):
    vv_p = tmp_path / "vv.tif"
    vh_p = tmp_path / "vh.tif"
    write_synthetic_geotiff(vv_p, np.full((300, 300), -12.0, dtype=np.float32))
    write_synthetic_geotiff(vh_p, np.full((300, 300), -22.0, dtype=np.float32))

    cand_p = tmp_path / "triaged_candidates.geojson"
    cand_1 = {
        "candidate_id": "C001",
        "candidate_group_id": "GRP001",
        "polygon": mapping(box(57.05, -20.15, 57.08, -20.12)),
        "area_km2": 2.5,
        "pixel_count": 250,
        "centroid_lat": -20.135,
        "centroid_lon": 57.065,
        "bounds": [57.05, -20.15, 57.08, -20.12],
        "distance_to_land_m": 800.0,
        "nearshore_context": True,
        "land_overlap_fraction": 0.0,
        "coastal_buffer_overlap": 0.0,
        "ocean_overlap_fraction": 1.0,
        "candidate_score": 85.0,
        "triage_tier": "PRIMARY_REVIEW",
        "sar_evidence": {
            "mean_vv_db": -16.5,
            "median_vv_db": -16.5,
            "std_vv_db": 1.2,
            "mean_vh_db": -28.0,
            "median_vh_db": -28.0,
            "std_vh_db": 1.5,
            "local_vv_contrast_db": 4.5,
        },
        "morphology": {
            "perimeter_px": 80.0,
            "elongation": 3.5,
            "compactness": 0.3,
            "solidity": 0.85,
            "orientation_deg": 42.0,
            "major_axis_px": 50.0,
            "minor_axis_px": 14.0,
            "edge_touching": False,
        },
        "context": {"touches_invalid_region": False},
    }

    write_synthetic_candidates_geojson(cand_p, [cand_1])

    out_dir = tmp_path / "ml_inputs_out"
    res = process_candidate_ml_inputs(cand_p, vv_p, vh_p, output_dir=out_dir)

    assert res["status"] == "PASS"
    assert res["primary_candidates_count"] == 1
    assert res["vv_vh_alignment"] == "PASS"
    assert res["training_lock"] == "PASS"

    c1_dir = out_dir / "chips" / "C001"
    assert (c1_dir / "vv_raw.tif").exists()
    assert (c1_dir / "vh_raw.tif").exists()
    assert (c1_dir / "candidate_mask.tif").exists()
    assert (c1_dir / "input_2ch.npy").exists()
    assert (c1_dir / "metadata.json").exists()

    # Verify 2-channel numpy array shape [2, 256, 256]
    npy_arr = np.load(c1_dir / "input_2ch.npy")
    assert npy_arr.shape == (2, 256, 256)
    assert np.all(np.isfinite(npy_arr))
    assert np.min(npy_arr) >= 0.0 and np.max(npy_arr) <= 1.0

    # Verify Metadata & Training Lock Safeguard
    with open(c1_dir / "metadata.json", "r", encoding="utf-8") as f:
        meta = json.load(f)

    assert meta["dataset_provenance"]["label_status"] == "UNLABELLED_REAL_CASE"
    assert meta["dataset_provenance"]["training_allowed"] is False
    assert meta["dataset_provenance"]["historical_truth_used"] is False
    assert meta["chip_provenance"]["polarization_order"] == ["VV", "VH"]
    assert meta["features"]["nearshore_context"] is True


def test_insufficient_context_handling(tmp_path):
    # Small raster where candidate fills almost entire scene
    vv_p = tmp_path / "vv.tif"
    vh_p = tmp_path / "vh.tif"
    write_synthetic_geotiff(vv_p, np.full((20, 20), -12.0, dtype=np.float32))
    write_synthetic_geotiff(vh_p, np.full((20, 20), -22.0, dtype=np.float32))

    cand_p = tmp_path / "triaged_candidates.geojson"
    cand_1 = {
        "candidate_id": "C001",
        "polygon": mapping(box(57.0, -20.02, 57.02, -20.0)),  # Fills scene
        "area_km2": 0.1,
        "pixel_count": 400,
        "candidate_score": 80.0,
        "triage_tier": "PRIMARY_REVIEW",
    }

    write_synthetic_candidates_geojson(cand_p, [cand_1])

    out_dir = tmp_path / "ml_inputs_out"
    res = process_candidate_ml_inputs(cand_p, vv_p, vh_p, output_dir=out_dir)

    assert res["insufficient_context_count"] == 1
    with open(out_dir / "chips" / "C001" / "metadata.json", "r", encoding="utf-8") as f:
        meta = json.load(f)
    assert meta["chip_provenance"]["quality_flag"] == "INSUFFICIENT_CONTEXT"
