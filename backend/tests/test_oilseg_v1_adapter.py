"""Unit tests for OilSeg V1 model adapter service."""

import json
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from backend.app.services.oilseg_v1_adapter import (
    DEFAULT_V1_CHECKPOINT,
    OilSegV1Result,
    execute_oilseg_v1_inference,
    validate_sar_inputs,
)


def create_test_geotiff(
    path: Path,
    array: np.ndarray,
    *,
    crs: str = "EPSG:4326",
    transform=None,
    tags: dict | None = None,
):
    path.parent.mkdir(parents=True, exist_ok=True)
    transform = transform or from_origin(2.0, 53.0, 0.001, 0.001)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=array.shape[0],
        width=array.shape[1],
        count=1,
        dtype=array.dtype,
        crs=crs,
        transform=transform,
    ) as dst:
        dst.write(array, 1)
        if tags:
            dst.update_tags(**tags)


def test_model_unavailable_when_checkpoint_missing(tmp_path):
    vv_p = tmp_path / "vv.tif"
    vh_p = tmp_path / "vh.tif"
    arr = np.full((64, 64), -14.0, dtype=np.float32)
    create_test_geotiff(vv_p, arr)
    create_test_geotiff(vh_p, arr)

    non_existent_ckpt = tmp_path / "missing_model.pt"
    res = execute_oilseg_v1_inference(
        vv_p,
        vh_p,
        output_dir=tmp_path / "out",
        checkpoint_path=non_existent_ckpt,
    )

    assert res.status == "MODEL_UNAVAILABLE"
    assert res.model_version is None
    assert res.evidence_raster_path is None
    assert res.binary_mask_path is None
    assert res.geojson_polygons is None
    assert "not found" in res.reason.lower()


def test_input_validation_shape_mismatch(tmp_path):
    vv_p = tmp_path / "vv.tif"
    vh_p = tmp_path / "vh.tif"
    create_test_geotiff(vv_p, np.full((64, 64), -14.0, dtype=np.float32))
    create_test_geotiff(vh_p, np.full((80, 64), -24.0, dtype=np.float32))

    res = execute_oilseg_v1_inference(
        vv_p,
        vh_p,
        output_dir=tmp_path / "out",
        checkpoint_path=DEFAULT_V1_CHECKPOINT,
    )
    assert res.status == "VALIDATION_ERROR"
    assert "shape mismatch" in res.reason.lower()


def test_input_validation_crs_mismatch(tmp_path):
    vv_p = tmp_path / "vv.tif"
    vh_p = tmp_path / "vh.tif"
    create_test_geotiff(vv_p, np.full((64, 64), -14.0, dtype=np.float32), crs="EPSG:4326")
    create_test_geotiff(vh_p, np.full((64, 64), -24.0, dtype=np.float32), crs="EPSG:3857")

    res = execute_oilseg_v1_inference(
        vv_p,
        vh_p,
        output_dir=tmp_path / "out",
        checkpoint_path=DEFAULT_V1_CHECKPOINT,
    )
    assert res.status == "VALIDATION_ERROR"
    assert "crs mismatch" in res.reason.lower()


def test_successful_v1_inference_with_trained_checkpoint(tmp_path):
    if not DEFAULT_V1_CHECKPOINT.exists():
        pytest.skip("Trained V1 checkpoint not yet present")

    # Construct synthetic oil scene
    h, w = 128, 128
    vv = np.full((h, w), -14.0, dtype=np.float32)
    vh = np.full((h, w), -24.0, dtype=np.float32)

    # Insert slick patch
    vv[40:70, 40:80] = -26.0
    vh[40:70, 40:80] = -32.0

    tags = {
        "SOURCE_STAC_ITEM_ID": "S1A_IW_GRDH_TEST",
        "SOURCE_PRODUCT_ID": "S1A_IW_GRDH_TEST_PROD",
        "SOURCE_ARCHIVE_SHA256": "abcdef123456",
        "RADIOMETRIC_MODE": "SIGMA0_CALIBRATED_DB",
        "PROCESSING_TIMESTAMP": "2026-09-19T12:00:00Z",
    }

    vv_p = tmp_path / "vv_test.tif"
    vh_p = tmp_path / "vh_test.tif"
    create_test_geotiff(vv_p, vv, tags=tags)
    create_test_geotiff(vh_p, vh, tags=tags)

    out_dir = tmp_path / "inference_out"
    res = execute_oilseg_v1_inference(
        vv_geotiff_path=vv_p,
        vh_geotiff_path=vh_p,
        output_dir=out_dir,
        checkpoint_path=DEFAULT_V1_CHECKPOINT,
        threshold=0.5,
        tile_size=128,
        stride=64,
        min_polygon_pixels=5,
    )

    assert res.status == "SUCCESS"
    assert res.model_version is not None
    assert res.checkpoint_sha256 is not None
    assert res.evidence_raster_path is not None
    assert Path(res.evidence_raster_path).exists()
    assert res.binary_mask_path is not None
    assert Path(res.binary_mask_path).exists()
    assert res.geojson_polygons is not None
    assert "features" in res.geojson_polygons
    assert len(res.geojson_polygons["features"]) > 0

    poly = res.geojson_polygons["features"][0]
    props = poly["properties"]
    assert "id" in props
    assert props["area_km2"] > 0
    assert props["mean_oil_evidence_score"] > 0.5
    assert "solidity" in props
    assert "elongation" in props

    assert res.statistics is not None
    assert res.statistics.oil_pixels > 0
    assert res.statistics.mean_oil_evidence_score > 0.5

    assert res.input_provenance["source_stac_item_id"] == "S1A_IW_GRDH_TEST"
    assert res.input_provenance["source_archive_sha256"] == "abcdef123456"
    assert res.input_provenance["vv_radiometric_mode"] == "SIGMA0_CALIBRATED_DB"
