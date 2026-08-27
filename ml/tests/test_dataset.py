import tempfile
from pathlib import Path
import numpy as np
import cv2
import pytest
from ml.src.oiltrace_ml.data import list_images, pair_images_and_masks, read_grayscale, OilSpillDataset


def test_list_and_pair_images(tmp_path):
    img_dir = tmp_path / "images"
    mask_dir = tmp_path / "masks"
    img_dir.mkdir()
    mask_dir.mkdir()

    # Create dummy images
    img1 = np.ones((64, 64), dtype=np.uint8) * 128
    mask1 = np.zeros((64, 64), dtype=np.uint8)
    mask1[10:30, 10:30] = 255

    cv2.imwrite(str(img_dir / "sample_001.png"), img1)
    cv2.imwrite(str(mask_dir / "sample_001.png"), mask1)
    cv2.imwrite(str(img_dir / "unmatched.png"), img1)

    images = list_images(img_dir)
    masks = list_images(mask_dir)
    assert len(images) == 2
    assert len(masks) == 1

    pairs = pair_images_and_masks(img_dir, mask_dir)
    assert len(pairs) == 1
    assert pairs[0][0].name == "sample_001.png"
    assert pairs[0][1].name == "sample_001.png"


def test_dataset_indexing(tmp_path):
    img_dir = tmp_path / "images"
    mask_dir = tmp_path / "masks"
    img_dir.mkdir()
    mask_dir.mkdir()

    dummy_img = np.ones((128, 128), dtype=np.uint8) * 100
    dummy_mask = np.zeros((128, 128), dtype=np.uint8)
    dummy_mask[20:50, 20:50] = 255

    cv2.imwrite(str(img_dir / "test.png"), dummy_img)
    cv2.imwrite(str(mask_dir / "test.png"), dummy_mask)

    pairs = pair_images_and_masks(img_dir, mask_dir)
    ds = OilSpillDataset(pairs, image_size=256)
    assert len(ds) == 1

    img_tensor, mask_tensor = ds[0]
    assert img_tensor.shape == (1, 256, 256)
    assert mask_tensor.shape == (1, 256, 256)
    assert float(mask_tensor.max()) == 1.0
