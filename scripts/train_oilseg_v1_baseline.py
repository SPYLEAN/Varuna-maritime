"""Train and evaluate the baseline SmallUNet model for OilSeg V1.

Strictly adheres to:
- RULE 4 (Train the Baseline First)
- RULE 5 (Record seed, splits, preprocessing, metrics, negative performance)
- Saves versioned checkpoint: models/oil_detection/varuna_oilseg_v1_smallunet.pt
- Evaluates on held-out test split
- Saves 07_results/final_build/oilseg_v1_metrics.json
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
from pathlib import Path
from typing import Any

# Ensure workspace root is in sys.path
workspace_root = Path(__file__).resolve().parents[1]
if str(workspace_root) not in sys.path:
    sys.path.insert(0, str(workspace_root))

import torch

from ml.src.oiltrace_ml.evaluate import evaluate_checkpoint
from ml.src.oiltrace_ml.preprocessing import SARPreprocessingConfig
from ml.src.oiltrace_ml.train import train_model


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def run_training_pipeline() -> dict[str, Any]:
    train_manifest = Path("07_results/final_build/oilseg_train_manifest.json")
    val_manifest = Path("07_results/final_build/oilseg_val_manifest.json")
    test_manifest = Path("07_results/final_build/oilseg_test_manifest.json")
    out_checkpoint = Path("models/oil_detection/varuna_oilseg_v1_smallunet.pt")

    preprocessing = SARPreprocessingConfig(
        channel_order=("VV", "VH"),
        db_min=(-30.0, -35.0),
        db_max=(0.0, -5.0),
    )

    seed = 42
    epochs = 12
    batch_size = 4
    learning_rate = 1e-3

    print("=== Training OilSeg V1 SmallUNet Baseline ===")
    history = train_model(
        epochs=epochs,
        batch_size=batch_size,
        image_size=256,
        lr=learning_rate,
        out_path=out_checkpoint,
        seed=seed,
        manifest_path=train_manifest,
        val_manifest_path=val_manifest,
        input_channels=2,
        channel_order=("VV", "VH"),
        preprocessing=preprocessing,
        dataset_version="oilseg_v1_canonical",
        model_version="varuna-oilseg-v1-smallunet",
    )

    print(f"Checkpoint saved: {out_checkpoint} (SHA256: {sha256_file(out_checkpoint)})")

    print("=== Evaluating on Held-out Test Split ===")
    test_report = evaluate_checkpoint(
        checkpoint_path=out_checkpoint,
        manifest_path=test_manifest,
        batch_size=2,
        threshold=0.5,
        oil_fraction_threshold=0.01,
    )

    print(f"Test IoU: {test_report['iou']:.4f}")
    print(f"Test Dice: {test_report['dice']:.4f}")
    print(f"Test Precision: {test_report['precision']:.4f}")
    print(f"Test Recall: {test_report['recall']:.4f}")
    print(f"Lookalike FP Scene Rate: {test_report['categories']['lookalike']['false_positive_scene_rate']:.4f}")
    print(f"No-Oil FP Scene Rate: {test_report['categories']['no_oil']['false_positive_scene_rate']:.4f}")

    # Compile comprehensive metrics payload per Rule 4
    metrics_payload = {
        "model_architecture": "small_unet",
        "model_version": "varuna-oilseg-v1-smallunet",
        "checkpoint_path": str(out_checkpoint),
        "checkpoint_sha256": sha256_file(out_checkpoint),
        "dataset_version": "oilseg_v1_canonical",
        "train_manifest_sha256": sha256_file(train_manifest),
        "val_manifest_sha256": sha256_file(val_manifest),
        "test_manifest_sha256": sha256_file(test_manifest),
        "training_parameters": {
            "seed": seed,
            "epochs": epochs,
            "batch_size": batch_size,
            "optimizer": "AdamW",
            "learning_rate": learning_rate,
            "weight_decay": 1e-4,
            "loss_function": "BCEWithLogitsLoss + DiceLoss",
            "image_size": [256, 256],
            "input_channels": 2,
            "channel_order": ["VV", "VH"],
            "preprocessing": preprocessing.to_dict(),
        },
        "environment": {
            "os": platform.platform(),
            "python_version": platform.python_version(),
            "torch_version": torch.__version__,
            "cuda_available": torch.cuda.is_available(),
            "device": "cuda" if torch.cuda.is_available() else "cpu",
        },
        "test_metrics": {
            "global_segmentation": test_report["global_segmentation"],
            "oil_evidence_metric": "OIL_EVIDENCE_SCORE",
            "category_performance": test_report["categories"],
            "summary_scores": {
                "oil_iou": test_report["categories"]["oil"]["iou"],
                "oil_dice": test_report["categories"]["oil"]["dice"],
                "oil_precision": test_report["categories"]["oil"]["precision"],
                "oil_recall": test_report["categories"]["oil"]["recall"],
                "lookalike_false_positive_scene_rate": test_report["categories"]["lookalike"]["false_positive_scene_rate"],
                "lookalike_mean_predicted_oil_fraction": test_report["categories"]["lookalike"]["mean_predicted_oil_fraction"],
                "lookalike_max_predicted_oil_fraction": test_report["categories"]["lookalike"]["maximum_predicted_oil_fraction"],
                "no_oil_false_positive_scene_rate": test_report["categories"]["no_oil"]["false_positive_scene_rate"],
                "no_oil_mean_predicted_oil_fraction": test_report["categories"]["no_oil"]["mean_predicted_oil_fraction"],
                "no_oil_max_predicted_oil_fraction": test_report["categories"]["no_oil"]["maximum_predicted_oil_fraction"],
            },
        },
        "scientific_disclaimer": "Raw neural network activations represent an empirical OIL_EVIDENCE_SCORE. Values do NOT constitute calibrated statistical probabilities until empirical Platt/isotonic calibration against in-situ drifter releases is performed.",
    }

    metrics_out = Path("07_results/final_build/oilseg_v1_metrics.json")
    metrics_out.write_text(json.dumps(metrics_payload, indent=2), encoding="utf-8")
    print(f"Metrics saved to: {metrics_out}")

    return metrics_payload


if __name__ == "__main__":
    run_training_pipeline()
