from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import torch
from torch.utils.data import DataLoader

from .checkpoint import load_model_from_checkpoint
from .data import OilSpillDataset, Sentinel1Dataset, pair_images_and_masks
from .preprocessing import SARPreprocessingConfig


def _empty_counts() -> dict[str, int]:
    return {"tp": 0, "fp": 0, "fn": 0}


def _metrics_from_counts(counts: dict[str, int]) -> dict[str, float]:
    tp, fp, fn = counts["tp"], counts["fp"], counts["fn"]
    eps = 1e-6
    return {
        "dice": (2 * tp + eps) / (2 * tp + fp + fn + eps),
        "iou": (tp + eps) / (tp + fp + fn + eps),
        "precision": (tp + eps) / (tp + fp + eps),
        "recall": (tp + eps) / (tp + fn + eps),
    }


def _add_counts(counts: dict[str, int], prediction: torch.Tensor, target: torch.Tensor) -> None:
    pred = prediction.bool()
    truth = target.bool()
    counts["tp"] += int((pred & truth).sum().item())
    counts["fp"] += int((pred & ~truth).sum().item())
    counts["fn"] += int((~pred & truth).sum().item())


def _batch_categories(metadata: Any, batch_size: int) -> list[str | None]:
    if not isinstance(metadata, dict) or "scene_category" not in metadata:
        return [None] * batch_size
    values = metadata["scene_category"]
    if isinstance(values, str):
        return [values]
    categories = [str(value) for value in values]
    if len(categories) != batch_size:
        raise ValueError("Batch metadata scene_category length does not match batch size")
    return categories


def evaluate_model(
    model: torch.nn.Module,
    loader: DataLoader,
    *,
    device: torch.device | str = "cpu",
    threshold: float = 0.5,
    oil_fraction_threshold: float = 0.01,
) -> dict[str, Any]:
    """Evaluate global segmentation and category-specific false positives.

    ``false_positive_scene_rate`` is the fraction of negative scenes with at
    least one predicted oil pixel. ``percentage_above_oil_fraction_threshold``
    uses the separately configured predicted-area threshold.
    """

    if not 0.0 <= threshold <= 1.0:
        raise ValueError("threshold must be between 0 and 1")
    if not 0.0 <= oil_fraction_threshold <= 1.0:
        raise ValueError("oil_fraction_threshold must be between 0 and 1")

    model.eval()
    global_counts = _empty_counts()
    oil_counts = _empty_counts()
    category_samples = {"oil": 0, "lookalike": 0, "no_oil": 0}
    negative_fractions: dict[str, list[float]] = {"lookalike": [], "no_oil": []}
    total_samples = 0

    with torch.no_grad():
        for batch in loader:
            if len(batch) not in (2, 3):
                raise ValueError("Evaluation batches must contain image/mask or image/mask/metadata")
            images, masks = batch[:2]
            metadata = batch[2] if len(batch) == 3 else None
            images, masks = images.to(device), masks.to(device)
            probabilities = torch.sigmoid(model(images))
            predictions = probabilities >= threshold
            categories = _batch_categories(metadata, images.shape[0])

            for index, category in enumerate(categories):
                prediction = predictions[index]
                target = masks[index] >= 0.5
                _add_counts(global_counts, prediction, target)
                total_samples += 1

                if category is None:
                    continue
                if category not in category_samples:
                    raise ValueError(f"Unsupported scene_category during evaluation: {category!r}")
                category_samples[category] += 1
                if category == "oil":
                    _add_counts(oil_counts, prediction, target)
                else:
                    negative_fractions[category].append(float(prediction.float().mean().item()))

    if total_samples == 0:
        raise ValueError("Evaluation loader produced no samples")

    global_metrics = {key: round(value, 6) for key, value in _metrics_from_counts(global_counts).items()}
    if category_samples["oil"]:
        oil_metrics: dict[str, Any] = {
            key: round(value, 6) for key, value in _metrics_from_counts(oil_counts).items()
        }
    else:
        oil_metrics = {key: None for key in ("dice", "iou", "precision", "recall")}
    oil_metrics["sample_count"] = category_samples["oil"]

    categories_report: dict[str, Any] = {"oil": oil_metrics}
    for category in ("lookalike", "no_oil"):
        fractions = negative_fractions[category]
        count = len(fractions)
        categories_report[category] = {
            "sample_count": count,
            "false_positive_scene_rate": round(sum(value > 0.0 for value in fractions) / count, 6)
            if count
            else None,
            "mean_predicted_oil_fraction": round(sum(fractions) / count, 6) if count else None,
            "maximum_predicted_oil_fraction": round(max(fractions), 6) if count else None,
            "percentage_above_oil_fraction_threshold": round(
                100.0 * sum(value > oil_fraction_threshold for value in fractions) / count,
                4,
            )
            if count
            else None,
        }

    return {
        "global_segmentation": global_metrics,
        "categories": categories_report,
        "probability_threshold": float(threshold),
        "oil_fraction_threshold": float(oil_fraction_threshold),
        "total_samples": total_samples,
    }


def evaluate_checkpoint(
    checkpoint_path: str | Path,
    images_dir: str | Path | None = None,
    masks_dir: str | Path | None = None,
    batch_size: int = 8,
    image_size: int | None = None,
    threshold: float = 0.5,
    num_workers: int = 0,
    *,
    manifest_path: str | Path | None = None,
    oil_fraction_threshold: float = 0.01,
    preprocessing: SARPreprocessingConfig | None = None,
) -> dict[str, Any]:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model, metadata, checkpoint_image_size = load_model_from_checkpoint(checkpoint_path, device=device)
    resolved_image_size = checkpoint_image_size if image_size is None else int(image_size)

    if manifest_path is not None:
        if images_dir is not None or masks_dir is not None:
            raise ValueError("Use either manifest_path or legacy images_dir/masks_dir, not both")
        if int(metadata["input_channels"]) != 2:
            raise ValueError("Sentinel-1 manifest evaluation requires a two-channel checkpoint")
        channel_order = tuple(metadata["channel_order"])
        if preprocessing is None:
            preprocessing_values = metadata.get("preprocessing", {})
            if preprocessing_values.get("method") not in {"fixed_db", "robust_percentile"}:
                raise ValueError("Two-channel checkpoint lacks usable SAR preprocessing metadata")
            preprocessing = SARPreprocessingConfig.from_dict(preprocessing_values)
        dataset = Sentinel1Dataset(
            manifest_path,
            image_size=resolved_image_size,
            channel_order=channel_order,
            preprocessing=preprocessing,
        )
    else:
        if images_dir is None or masks_dir is None:
            raise ValueError("Legacy evaluation requires images_dir and masks_dir")
        if int(metadata["input_channels"]) != 1:
            raise ValueError("Legacy image-folder evaluation only supports one-channel checkpoints")
        pairs = pair_images_and_masks(images_dir, masks_dir)
        if not pairs:
            raise ValueError(f"No paired image/mask files found between {images_dir} and {masks_dir}")
        dataset = OilSpillDataset(pairs, image_size=resolved_image_size)

    loader = DataLoader(dataset, batch_size=batch_size, shuffle=False, num_workers=num_workers)
    report = evaluate_model(
        model,
        loader,
        device=device,
        threshold=threshold,
        oil_fraction_threshold=oil_fraction_threshold,
    )
    report["checkpoint"] = str(Path(checkpoint_path))
    report["checkpoint_metadata"] = metadata

    # Keep the V0 API's top-level segmentation keys intact.
    report.update({key: round(value, 4) for key, value in report["global_segmentation"].items()})
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate an OilSeg checkpoint on held-out data.")
    parser.add_argument("--checkpoint", required=True, help="Path to saved model checkpoint (.pt)")
    parser.add_argument("--images", help="Legacy V0 held-out image directory")
    parser.add_argument("--masks", help="Legacy V0 held-out mask directory")
    parser.add_argument("--manifest", help="V1 Sentinel-1 held-out manifest")
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--image-size", type=int, default=None)
    parser.add_argument("--threshold", type=float, default=0.5, help="Pixel probability threshold")
    parser.add_argument(
        "--oil-fraction-threshold",
        type=float,
        default=0.01,
        help="Predicted oil area fraction used for negative-scene exceedance analysis",
    )
    parser.add_argument("--num-workers", type=int, default=0)
    parser.add_argument("--out-json", help="Optional metrics JSON output")
    args = parser.parse_args()

    report = evaluate_checkpoint(
        checkpoint_path=args.checkpoint,
        images_dir=args.images,
        masks_dir=args.masks,
        manifest_path=args.manifest,
        batch_size=args.batch_size,
        image_size=args.image_size,
        threshold=args.threshold,
        oil_fraction_threshold=args.oil_fraction_threshold,
        num_workers=args.num_workers,
    )

    print(json.dumps(report, indent=2))
    if args.out_json:
        output_path = Path(args.out_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Saved evaluation metrics JSON to {output_path}")


if __name__ == "__main__":
    main()
