import json

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from torch.utils.data import DataLoader

from ml.src.oiltrace_ml.data import Sentinel1Dataset, load_sentinel1_manifest
from ml.src.oiltrace_ml.preprocessing import (
    SARPreprocessingConfig,
    config_for_channels,
    preprocess_sar,
)
from ml.src.oiltrace_ml.validate import validate_sentinel1_dataset


def write_geotiff(path, array, *, transform=None):
    transform = transform or from_origin(72.0, 19.0, 0.001, 0.001)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=array.shape[0],
        width=array.shape[1],
        count=1,
        dtype=array.dtype,
        crs="EPSG:4326",
        transform=transform,
    ) as dst:
        dst.write(array, 1)


def make_manifest(tmp_path, *, category="oil", mask=None):
    vv_path = tmp_path / "scene_vv.tif"
    vh_path = tmp_path / "scene_vh.tif"
    mask_path = tmp_path / "scene_mask.tif"
    write_geotiff(vv_path, np.full((8, 10), 0.0, dtype=np.float32))
    write_geotiff(vh_path, np.full((8, 10), -35.0, dtype=np.float32))
    write_geotiff(
        mask_path,
        np.zeros((8, 10), dtype=np.uint8) if mask is None else mask,
    )
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            [
                {
                    "scene_id": "S1_TEST_001",
                    "vv_path": vv_path.name,
                    "vh_path": vh_path.name,
                    "mask_path": mask_path.name,
                    "scene_category": category,
                    "acquisition_timestamp": "2026-08-28T01:02:03Z",
                }
            ]
        ),
        encoding="utf-8",
    )
    return manifest_path, vv_path, vh_path, mask_path


def test_dual_channel_loading_and_explicit_vv_vh_order(tmp_path):
    manifest, _, _, _ = make_manifest(tmp_path)
    dataset = Sentinel1Dataset(manifest, image_size=16, channel_order=("VV", "VH"))

    image, mask, metadata = dataset[0]

    assert image.shape == (2, 16, 16)
    assert mask.shape == (1, 16, 16)
    assert image[0].unique().item() == pytest.approx(1.0)
    assert image[1].unique().item() == pytest.approx(0.0)
    assert metadata["channel_order"] == ["VV", "VH"]
    assert metadata["scene_id"] == "S1_TEST_001"
    assert metadata["scene_category"] == "oil"
    assert metadata["crs"] == "EPSG:4326"
    assert metadata["acquisition_timestamp"] == "2026-08-28T01:02:03Z"

    batch_image, batch_mask, batch_metadata = next(iter(DataLoader(dataset, batch_size=1)))
    assert batch_image.shape == (1, 2, 16, 16)
    assert batch_mask.shape == (1, 1, 16, 16)
    assert batch_metadata["scene_category"] == ["oil"]


def test_explicit_reversed_order_is_not_silently_swapped(tmp_path):
    manifest, _, _, _ = make_manifest(tmp_path)
    order = ("VH", "VV")
    dataset = Sentinel1Dataset(
        manifest,
        image_size=8,
        channel_order=order,
        preprocessing=config_for_channels(order),
    )

    image, _, metadata = dataset[0]

    assert image[0].unique().item() == pytest.approx(0.0)
    assert image[1].unique().item() == pytest.approx(1.0)
    assert metadata["channel_order"] == ["VH", "VV"]


def test_missing_vh_is_rejected(tmp_path):
    manifest, _, vh_path, _ = make_manifest(tmp_path)
    vh_path.unlink()

    with pytest.raises(FileNotFoundError, match="missing VH"):
        Sentinel1Dataset(manifest)


def test_malformed_tiff_is_rejected_on_read(tmp_path):
    manifest, _, vh_path, _ = make_manifest(tmp_path)
    vh_path.write_bytes(b"not-a-tiff")
    dataset = Sentinel1Dataset(manifest)

    with pytest.raises(ValueError, match="Could not read VH GeoTIFF"):
        dataset[0]


def test_image_mask_shape_mismatch_is_rejected(tmp_path):
    manifest, _, _, mask_path = make_manifest(tmp_path)
    write_geotiff(mask_path, np.zeros((7, 10), dtype=np.uint8))
    dataset = Sentinel1Dataset(manifest)

    with pytest.raises(ValueError, match="mask shape"):
        dataset[0]


@pytest.mark.parametrize("category", ["lookalike", "no_oil"])
def test_negative_scene_categories_preserve_valid_empty_masks(tmp_path, category):
    manifest, _, _, _ = make_manifest(tmp_path, category=category)
    dataset = Sentinel1Dataset(manifest, image_size=8)

    _, mask, metadata = dataset[0]

    assert mask.sum().item() == 0.0
    assert metadata["scene_category"] == category
    assert metadata["mask_is_empty"] is True


def test_manifest_requires_valid_scene_category(tmp_path):
    manifest, _, _, _ = make_manifest(tmp_path)
    records = json.loads(manifest.read_text(encoding="utf-8"))
    records[0]["scene_category"] = "ship"
    manifest.write_text(json.dumps(records), encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid scene_category"):
        load_sentinel1_manifest(manifest)


def test_fixed_db_preprocessing_and_invalid_values():
    config = SARPreprocessingConfig(
        channel_order=("VV", "VH"),
        db_min=(-30.0, -35.0),
        db_max=(0.0, -5.0),
    )
    image = np.array(
        [
            [[-40.0, -15.0, 10.0]],
            [[-40.0, -20.0, 0.0]],
        ],
        dtype=np.float32,
    )

    result = preprocess_sar(image, config)

    np.testing.assert_allclose(result[0, 0], [0.0, 0.5, 1.0])
    np.testing.assert_allclose(result[1, 0], [0.0, 0.5, 1.0])

    invalid = image.copy()
    invalid[1, 0, 1] = np.nan
    with pytest.raises(ValueError, match="non-finite"):
        preprocess_sar(invalid, config)


def test_preprocessing_configuration_rejects_mismatched_channel_count():
    with pytest.raises(ValueError, match="one value per channel"):
        SARPreprocessingConfig(channel_order=("VV", "VH"), db_min=(-30.0,), db_max=(0.0,))


def test_sentinel1_validation_reports_category_and_empty_mask(tmp_path):
    manifest, _, _, _ = make_manifest(tmp_path, category="lookalike")

    report = validate_sentinel1_dataset(manifest)

    assert report["sample_count"] == 1
    assert report["valid_samples"] == 1
    assert report["invalid_samples"] == 0
    assert report["category_counts"] == {"oil": 0, "lookalike": 1, "no_oil": 0}
    assert report["empty_masks_by_category"]["lookalike"] == 1
