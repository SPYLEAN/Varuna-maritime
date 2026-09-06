import json
import numpy as np
import pytest
import rasterio
import torch
from pathlib import Path
from rasterio.transform import from_origin

from ml.src.oiltrace_ml.checkpoint import (
    build_checkpoint,
    create_checkpoint_metadata,
    load_model_from_checkpoint,
    unpack_checkpoint,
)
from ml.src.oiltrace_ml.data import (
    Sentinel1Dataset,
    Sentinel1Sample,
    audit_split_leakage,
    extract_aligned_patches,
    load_sentinel1_manifest,
    read_sentinel1_stack,
)
from ml.src.oiltrace_ml.infer import run_windowed_inference
from ml.src.oiltrace_ml.model import SmallUNet
from ml.src.oiltrace_ml.preprocessing import (
    SARPreprocessingConfig,
    config_for_channels,
    preprocess_sar,
)
from ml.src.oiltrace_ml.evaluate import evaluate_checkpoint, evaluate_model


def write_test_geotiff(
    path: Path,
    array: np.ndarray,
    *,
    crs: str = "EPSG:4326",
    transform=None,
    nodata: float | None = None,
):
    transform = transform or from_origin(57.1, -19.7, 0.001, 0.001)
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


# A. V1 SCIENTIFIC INPUT CONTRACT & MISMATCH REJECTION
def test_v1_vv_vh_shape_mismatch_rejected(tmp_path):
    vv_path = tmp_path / "vv.tif"
    vh_path = tmp_path / "vh.tif"
    write_test_geotiff(vv_path, np.full((10, 10), -15.0, dtype=np.float32))
    write_test_geotiff(vh_path, np.full((12, 10), -20.0, dtype=np.float32))

    with pytest.raises(ValueError, match="shape"):
        read_sentinel1_stack(vv_path, vh_path)


def test_v1_vv_vh_crs_mismatch_rejected(tmp_path):
    vv_path = tmp_path / "vv.tif"
    vh_path = tmp_path / "vh.tif"
    write_test_geotiff(vv_path, np.full((10, 10), -15.0, dtype=np.float32), crs="EPSG:4326")
    write_test_geotiff(vh_path, np.full((10, 10), -20.0, dtype=np.float32), crs="EPSG:3857")

    with pytest.raises(ValueError, match="CRS"):
        read_sentinel1_stack(vv_path, vh_path)


def test_v1_vv_vh_affine_mismatch_rejected(tmp_path):
    vv_path = tmp_path / "vv.tif"
    vh_path = tmp_path / "vh.tif"
    t1 = from_origin(57.1, -19.7, 0.001, 0.001)
    t2 = from_origin(57.2, -19.7, 0.001, 0.001)
    write_test_geotiff(vv_path, np.full((10, 10), -15.0, dtype=np.float32), transform=t1)
    write_test_geotiff(vh_path, np.full((10, 10), -20.0, dtype=np.float32), transform=t2)

    with pytest.raises(ValueError, match="affine transform"):
        read_sentinel1_stack(vv_path, vh_path)


# B. REMOVE V0 NORMALIZATION FAILURE MODE & PROFILE REUSE
def test_v1_normalization_profile_reuse():
    config = SARPreprocessingConfig(
        channel_order=("VV", "VH"),
        db_min=(-30.0, -35.0),
        db_max=(0.0, -5.0),
    )
    data_dict = config.to_dict()
    restored = SARPreprocessingConfig.from_dict(data_dict)

    assert restored.channel_order == ("VV", "VH")
    assert restored.db_min == (-30.0, -35.0)
    assert restored.db_max == (0.0, -5.0)

    # Test normalization reproducibility
    sample_input = np.array(
        [[[-15.0, -30.0]], [[-20.0, -35.0]]],
        dtype=np.float32,
    )
    norm1 = preprocess_sar(sample_input, config)
    norm2 = preprocess_sar(sample_input, restored)

    np.testing.assert_allclose(norm1, norm2)
    np.testing.assert_allclose(norm1[0, 0], [0.5, 0.0])
    np.testing.assert_allclose(norm1[1, 0], [0.5, 0.0])


# C. NODATA / EXTREME VALUE HANDLING
def test_v1_nodata_and_non_finite_handling():
    config_error = SARPreprocessingConfig(invalid_value_policy="error")
    arr_nan = np.array([[[-15.0, np.nan]], [[-20.0, -25.0]]], dtype=np.float32)

    with pytest.raises(ValueError, match="non-finite"):
        preprocess_sar(arr_nan, config_error)

    config_fill = SARPreprocessingConfig(invalid_value_policy="fill", invalid_fill_db=-30.0)
    filled = preprocess_sar(arr_nan, config_fill)
    assert np.isfinite(filled).all()
    assert filled[0, 0, 1] == pytest.approx(0.0)  # -30.0 dB normalized in VV is 0.0


# D & H. NEGATIVE-SCENE EVALUATION METRICS
def test_v1_negative_scene_metrics_reporting(tmp_path):
    # Create simple dummy model and loader
    model = SmallUNet(in_channels=2, out_channels=1)
    
    # Create dummy samples
    vv_path = tmp_path / "vv.tif"
    vh_path = tmp_path / "vh.tif"
    mask_path = tmp_path / "mask.tif"
    write_test_geotiff(vv_path, np.full((16, 16), -15.0, dtype=np.float32))
    write_test_geotiff(vh_path, np.full((16, 16), -20.0, dtype=np.float32))
    write_test_geotiff(mask_path, np.zeros((16, 16), dtype=np.uint8))

    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            [
                {
                    "scene_id": "S1_LOOKALIKE_001",
                    "vv_path": vv_path.name,
                    "vh_path": vh_path.name,
                    "mask_path": mask_path.name,
                    "scene_category": "lookalike",
                }
            ]
        ),
        encoding="utf-8",
    )

    dataset = Sentinel1Dataset(manifest_path, image_size=16)
    loader = torch.utils.data.DataLoader(dataset, batch_size=1)
    report = evaluate_model(model, loader)

    assert "categories" in report
    assert "lookalike" in report["categories"]
    assert report["categories"]["lookalike"]["sample_count"] == 1
    assert "false_positive_scene_rate" in report["categories"]["lookalike"]


# F. SPLIT SAFETY & EVENT-WISE LEAKAGE PROTECTION
def test_v1_split_leakage_protection():
    s1 = Sentinel1Sample("S1_001", Path("vv1"), Path("vh1"), Path("m1"), "oil", "2026-08-10T00:00:00Z")
    s2 = Sentinel1Sample("S1_002", Path("vv2"), Path("vh2"), Path("m2"), "oil", "2026-08-10T01:00:00Z")
    s3 = Sentinel1Sample("S1_003", Path("vv3"), Path("vh3"), Path("m3"), "no_oil", "2026-08-11T00:00:00Z")

    # Audit clean split
    clean_audit = audit_split_leakage(train_samples=[s1], val_samples=[s3])
    assert clean_audit["passed"] is True

    # Audit leaking scene_id
    with pytest.raises(ValueError, match="Split leakage audit FAILED"):
        audit_split_leakage(train_samples=[s1], val_samples=[s1])

    # Audit leaking event date
    with pytest.raises(ValueError, match="Split leakage audit FAILED"):
        audit_split_leakage(train_samples=[s1], val_samples=[s2])


# G. PATCH DATA PIPELINE & ALIGNMENT
def test_v1_patch_extraction_alignment():
    image = np.random.randn(2, 64, 64).astype(np.float32)
    mask = np.zeros((64, 64), dtype=np.float32)
    mask[10:20, 10:20] = 1.0

    patches = extract_aligned_patches(image, mask, patch_size=32, stride=16, min_oil_pixels=1)

    assert len(patches) > 0
    for img_p, mask_p, coords in patches:
        assert img_p.shape == (2, 32, 32)
        assert mask_p.shape == (32, 32)
        y1, y2, x1, x2 = coords
        np.testing.assert_allclose(img_p, image[:, y1:y2, x1:x2])
        np.testing.assert_allclose(mask_p, mask[y1:y2, x1:x2])


# H. MODEL BASELINE 2-CHANNEL TENSOR SHAPE
def test_v1_small_unet_two_channel_shape():
    model = SmallUNet(in_channels=2, out_channels=1, base=16)
    x = torch.randn(2, 2, 64, 64)
    y = model(x)

    assert y.shape == (2, 1, 64, 64)


# I. FULL-SCENE WINDOWED INFERENCE & GEOREFERENCE PRESERVATION
def test_v1_windowed_full_scene_inference_stitching(tmp_path):
    vv_path = tmp_path / "scene_vv.tif"
    vh_path = tmp_path / "scene_vh.tif"
    out_bin_path = tmp_path / "out_mask.tif"
    out_prob_path = tmp_path / "out_prob.tif"
    ckpt_path = tmp_path / "v1_checkpoint.pt"

    transform = from_origin(57.1, -19.7, 0.001, 0.001)
    write_test_geotiff(vv_path, np.full((64, 64), -15.0, dtype=np.float32), transform=transform)
    write_test_geotiff(vh_path, np.full((64, 64), -20.0, dtype=np.float32), transform=transform)

    # Build and save dummy 2-channel checkpoint
    model = SmallUNet(in_channels=2, out_channels=1)
    meta = create_checkpoint_metadata(
        model_architecture="small_unet",
        model_version="v1-test",
        input_channels=2,
        channel_order=["VV", "VH"],
        preprocessing=config_for_channels(["VV", "VH"]).to_dict(),
        training_dataset_version="v1-test-ds",
        epoch=1,
        validation_metrics={"dice": 0.95},
    )
    ckpt_dict = build_checkpoint(model, image_size=32, metadata=meta)
    torch.save(ckpt_dict, ckpt_path)

    # Execute windowed inference
    res = run_windowed_inference(
        checkpoint_path=ckpt_path,
        image_path=vv_path,
        vh_image_path=vh_path,
        output_geotiff_path=out_bin_path,
        prob_geotiff_path=out_prob_path,
        tile_size=32,
        stride=16,
    )

    assert Path(res["binary_geotiff_path"]).exists()
    assert Path(res["probability_geotiff_path"]).exists()
    assert res["shape"] == (64, 64)
    assert res["crs"] == "EPSG:4326"

    # Verify georeference preservation in written output GeoTIFF
    with rasterio.open(out_bin_path) as dst:
        assert dst.shape == (64, 64)
        assert dst.crs.to_string() == "EPSG:4326"
        assert dst.transform == transform


# J. CHECKPOINT METADATA SCHEMA & UNPACKING
def test_v1_checkpoint_metadata_schema():
    meta = create_checkpoint_metadata(
        model_architecture="small_unet",
        model_version="v1-prod",
        input_channels=2,
        channel_order=["VV", "VH"],
        preprocessing=SARPreprocessingConfig().to_dict(),
        training_dataset_version="v1-dataset-2026",
        epoch=5,
        validation_metrics={"dice": 0.88, "iou": 0.79},
    )
    model = SmallUNet(in_channels=2, out_channels=1)
    ckpt = build_checkpoint(model, image_size=256, metadata=meta)

    state, unpacked_meta, img_size = unpack_checkpoint(ckpt)
    assert unpacked_meta["model_version"] == "v1-prod"
    assert unpacked_meta["input_channels"] == 2
    assert unpacked_meta["channel_order"] == ["VV", "VH"]
    assert img_size == 256
