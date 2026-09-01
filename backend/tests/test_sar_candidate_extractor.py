import json
import numpy as np
import pytest
import rasterio
from pathlib import Path
from rasterio.transform import from_origin

from backend.app.services.sar_candidate_extractor import (
    extract_sar_candidates,
    _validate_input_rasters,
)


def write_test_sar(
    path: Path,
    array: np.ndarray,
    *,
    crs: str = "EPSG:4326",
    transform=None,
    nodata: float | None = None,
):
    transform = transform or from_origin(10.0, 50.0, 0.001, 0.001)
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
        nodata=nodata,
    ) as dst:
        dst.write(array, 1)


def test_alignment_success(tmp_path):
    vv_p = tmp_path / "vv.tif"
    vh_p = tmp_path / "vh.tif"
    write_test_sar(vv_p, np.full((100, 100), -12.0, dtype=np.float32))
    write_test_sar(vh_p, np.full((100, 100), -18.0, dtype=np.float32))

    vv_meta, vh_meta = _validate_input_rasters(vv_p, vh_p)
    assert vv_meta["shape"] == (100, 100)
    assert vh_meta["shape"] == (100, 100)


def test_shape_mismatch_rejection(tmp_path):
    vv_p = tmp_path / "vv.tif"
    vh_p = tmp_path / "vh.tif"
    write_test_sar(vv_p, np.full((100, 100), -12.0, dtype=np.float32))
    write_test_sar(vh_p, np.full((100, 105), -18.0, dtype=np.float32))

    with pytest.raises(ValueError, match="shape"):
        extract_sar_candidates(vv_p, vh_p)


def test_crs_mismatch_rejection(tmp_path):
    vv_p = tmp_path / "vv.tif"
    vh_p = tmp_path / "vh.tif"
    write_test_sar(vv_p, np.full((100, 100), -12.0, dtype=np.float32), crs="EPSG:4326")
    write_test_sar(vh_p, np.full((100, 100), -18.0, dtype=np.float32), crs="EPSG:3857")

    with pytest.raises(ValueError, match="CRS"):
        extract_sar_candidates(vv_p, vh_p)


def test_transform_mismatch_rejection(tmp_path):
    vv_p = tmp_path / "vv.tif"
    vh_p = tmp_path / "vh.tif"
    t1 = from_origin(10.0, 50.0, 0.001, 0.001)
    t2 = from_origin(11.0, 50.0, 0.001, 0.001)
    write_test_sar(vv_p, np.full((100, 100), -12.0, dtype=np.float32), transform=t1)
    write_test_sar(vh_p, np.full((100, 100), -18.0, dtype=np.float32), transform=t2)

    with pytest.raises(ValueError, match="transform"):
        extract_sar_candidates(vv_p, vh_p)


def test_nan_and_inf_handling(tmp_path):
    vv_p = tmp_path / "vv.tif"
    vh_p = tmp_path / "vh.tif"
    vv = np.full((100, 100), -12.0, dtype=np.float32)
    vh = np.full((100, 100), -18.0, dtype=np.float32)
    vv[0:10, 0:10] = np.nan
    vh[0:5, 0:5] = np.inf

    write_test_sar(vv_p, vv)
    write_test_sar(vh_p, vh)

    res = extract_sar_candidates(vv_p, vh_p)
    assert res["status"] in ("PASS", "INSUFFICIENT_DATA")
    assert res["scene_statistics"]["invalid_pixel_count"] >= 100


def test_synthetic_dark_elongated_feature(tmp_path):
    vv = np.full((200, 200), -12.0, dtype=np.float32)
    vh = np.full((200, 200), -18.0, dtype=np.float32)

    # Insert synthetic dark feature (elongated region 10x40 pixels)
    vv[80:90, 80:120] = -22.0
    vh[80:90, 80:120] = -26.0

    vv_p = tmp_path / "vv.tif"
    vh_p = tmp_path / "vh.tif"
    write_test_sar(vv_p, vv)
    write_test_sar(vh_p, vh)

    res = extract_sar_candidates(
        vv_p,
        vh_p,
        config={"min_component_size_pixels": 20, "local_window_sizes_px": [31]},
    )

    assert res["status"] == "PASS"
    assert res["candidate_count"] >= 1
    top_cand = res["candidates"][0]
    assert top_cand["candidate_id"] == "C001"
    assert top_cand["pixel_count"] >= 30
    assert top_cand["sar_evidence"]["local_vv_contrast_db"] >= 5.0
    assert top_cand["candidate_score"] > 0
    assert "score_breakdown" in top_cand


def test_tiny_speckle_removal(tmp_path):
    vv = np.full((100, 100), -12.0, dtype=np.float32)
    vh = np.full((100, 100), -18.0, dtype=np.float32)

    # Insert 3 isolated speckle pixels
    vv[10, 10] = -25.0
    vv[30, 40] = -25.0

    vv_p = tmp_path / "vv.tif"
    vh_p = tmp_path / "vh.tif"
    write_test_sar(vv_p, vv)
    write_test_sar(vh_p, vh)

    res = extract_sar_candidates(
        vv_p, vh_p, config={"min_component_size_pixels": 20}
    )

    assert res["status"] == "PASS"
    assert res["candidate_count"] == 0  # Tiny speckles filtered out


def test_saturation_guard(tmp_path):
    vv = np.full((100, 100), -12.0, dtype=np.float32)
    vh = np.full((100, 100), -18.0, dtype=np.float32)

    # Make 50% of scene extremely dark
    vv[0:50, :] = -30.0

    vv_p = tmp_path / "vv.tif"
    vh_p = tmp_path / "vh.tif"
    write_test_sar(vv_p, vv)
    write_test_sar(vh_p, vh)

    res = extract_sar_candidates(
        vv_p, vh_p, config={"max_scene_candidate_fraction": 0.10}
    )

    assert res["status"] == "INSUFFICIENT_DATA"
    assert res["scene_statistics"]["extraction_saturated"] is True
    assert any("DARK_SPOT_EXTRACTION_SATURATED" in w for w in res["warnings"])
