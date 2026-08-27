from pathlib import Path
import numpy as np
import cv2
import pytest
from ml.src.oiltrace_ml.validate import validate_dataset
from ml.src.oiltrace_ml.visualize import create_contact_sheet
from ml.src.oiltrace_ml.train import train_model
from ml.src.oiltrace_ml.evaluate import evaluate_checkpoint
from ml.src.oiltrace_ml.infer import run_inference


@pytest.fixture
def synthetic_data(tmp_path):
    img_dir = tmp_path / "images"
    mask_dir = tmp_path / "masks"
    img_dir.mkdir()
    mask_dir.mkdir()

    # Generate 5 synthetic SAR image and mask pairs
    for i in range(5):
        stem = f"sar_sample_{i:03d}"
        img = (np.random.rand(128, 128) * 255).astype(np.uint8)
        mask = np.zeros((128, 128), dtype=np.uint8)
        if i % 2 == 0:
            mask[30:70, 30:70] = 255  # Positive oil spill

        cv2.imwrite(str(img_dir / f"{stem}.png"), img)
        cv2.imwrite(str(mask_dir / f"{stem}.png"), mask)

    # Add 1 unmatched image and 1 unmatched mask to test validation
    cv2.imwrite(str(img_dir / "unmatched_img.png"), (np.random.rand(128, 128) * 255).astype(np.uint8))
    cv2.imwrite(str(mask_dir / "unmatched_mask.png"), np.zeros((128, 128), dtype=np.uint8))

    return img_dir, mask_dir, tmp_path


def test_full_ml_pipeline(synthetic_data):
    img_dir, mask_dir, work_dir = synthetic_data

    # 1. Test Dataset Validation Report
    report = validate_dataset(img_dir, mask_dir)
    assert report["image_count"] == 6
    assert report["mask_count"] == 6
    assert report["paired_samples"] == 5
    assert len(report["unmatched_images"]) == 1
    assert len(report["unmatched_masks"]) == 1
    assert report["empty_masks"] == 2
    assert "percentage_positive_oil_pixels" in report

    # 2. Test Contact Sheet Visualization
    pairs = [(img_dir / f"sar_sample_{i:03d}.png", mask_dir / f"sar_sample_{i:03d}.png") for i in range(5)]
    contact_sheet_path = work_dir / "contact_sheet.png"
    out_sheet = create_contact_sheet(pairs, num_samples=3, out_path=contact_sheet_path)
    assert out_sheet.exists()
    assert out_sheet.stat().st_size > 0

    # 3. Test Training Loop & Checkpoint Saving
    ckpt_path = work_dir / "models" / "best_model.pt"
    train_res = train_model(
        images_dir=img_dir,
        masks_dir=mask_dir,
        epochs=2,
        batch_size=2,
        image_size=128,
        max_samples=4,
        out_path=ckpt_path,
        seed=42,
    )
    assert ckpt_path.exists()
    assert train_res["best_val_dice"] >= 0.0

    # 4. Test Model Evaluation
    eval_res = evaluate_checkpoint(
        checkpoint_path=ckpt_path,
        images_dir=img_dir,
        masks_dir=mask_dir,
        batch_size=2,
        image_size=128,
    )
    assert "dice" in eval_res
    assert "iou" in eval_res
    assert "precision" in eval_res
    assert "recall" in eval_res
    assert eval_res["total_samples"] == 5

    # 5. Test Inference (Probability Mask + Binary Mask)
    bin_out = work_dir / "pred_binary.png"
    prob_out = work_dir / "pred_prob.png"
    sample_img = img_dir / "sar_sample_000.png"

    inf_res = run_inference(
        checkpoint_path=ckpt_path,
        image_path=sample_img,
        binary_out_path=bin_out,
        prob_out_path=prob_out,
        threshold=0.5,
    )
    assert bin_out.exists()
    assert prob_out.exists()
    assert bin_out.stat().st_size > 0
    assert prob_out.stat().st_size > 0
    assert 0.0 <= inf_res["oil_fraction"] <= 1.0
    assert 0.0 <= inf_res["mean_probability"] <= 1.0
    assert 0.0 <= inf_res["max_probability"] <= 1.0
    assert inf_res["threshold"] == 0.5
