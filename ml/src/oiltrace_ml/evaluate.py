from __future__ import annotations
import argparse
import json
from pathlib import Path
import torch
from torch.utils.data import DataLoader
from .data import pair_images_and_masks, OilSpillDataset
from .model import SmallUNet
from .metrics import binary_metrics


def evaluate_checkpoint(
    checkpoint_path: str | Path,
    images_dir: str | Path,
    masks_dir: str | Path,
    batch_size: int = 8,
    image_size: int | None = None,
    threshold: float = 0.5,
    num_workers: int = 0,
) -> dict:
    checkpoint_path = Path(checkpoint_path)
    if not checkpoint_path.exists():
        raise FileNotFoundError(f"Checkpoint file not found: {checkpoint_path}")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    ckpt = torch.load(checkpoint_path, map_location=device)

    # Determine image size from checkpoint if not specified
    if image_size is None:
        image_size = int(ckpt.get("image_size", 256)) if isinstance(ckpt, dict) else 256

    model = SmallUNet().to(device)
    state_dict = ckpt["model"] if isinstance(ckpt, dict) and "model" in ckpt else ckpt
    model.load_state_dict(state_dict)
    model.eval()

    pairs = pair_images_and_masks(images_dir, masks_dir)
    if not pairs:
        raise ValueError(f"No paired image/mask files found between {images_dir} and {masks_dir}")

    dataset = OilSpillDataset(pairs, image_size=image_size)
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=False, num_workers=num_workers)

    totals = {"dice": 0.0, "iou": 0.0, "precision": 0.0, "recall": 0.0}
    n_batches = 0

    with torch.no_grad():
        for images, masks in loader:
            images, masks = images.to(device), masks.to(device)
            logits = model(images)
            m = binary_metrics(logits, masks, threshold=threshold)
            for k in totals:
                totals[k] += m[k]
            n_batches += 1

    avg_metrics = {k: round(v / max(n_batches, 1), 4) for k, v in totals.items()}
    avg_metrics["total_samples"] = len(pairs)
    avg_metrics["checkpoint"] = str(checkpoint_path)
    return avg_metrics


def main():
    ap = argparse.ArgumentParser(description="Evaluate a trained U-Net checkpoint on a held-out dataset.")
    ap.add_argument("--checkpoint", required=True, help="Path to saved model checkpoint (.pt)")
    ap.add_argument("--images", required=True, help="Path to held-out test SAR images directory")
    ap.add_argument("--masks", required=True, help="Path to held-out test ground-truth masks directory")
    ap.add_argument("--batch-size", type=int, default=8, help="Batch size for evaluation")
    ap.add_argument("--image-size", type=int, default=None, help="Image resize dimension (default: from checkpoint)")
    ap.add_argument("--threshold", type=float, default=0.5, help="Binary decision threshold")
    ap.add_argument("--out-json", help="Optional path to export metrics JSON report")
    args = ap.parse_args()

    metrics = evaluate_checkpoint(
        checkpoint_path=args.checkpoint,
        images_dir=args.images,
        masks_dir=args.masks,
        batch_size=args.batch_size,
        image_size=args.image_size,
        threshold=args.threshold,
    )

    print("==================================================")
    print("           MODEL EVALUATION REPORT                ")
    print("==================================================")
    print(f"Checkpoint               : {metrics['checkpoint']}")
    print(f"Evaluated Samples        : {metrics['total_samples']}")
    print(f"Dice Coefficient         : {metrics['dice']:.4f}")
    print(f"IoU (Jaccard Index)      : {metrics['iou']:.4f}")
    print(f"Precision                : {metrics['precision']:.4f}")
    print(f"Recall                   : {metrics['recall']:.4f}")
    print("==================================================")

    if args.out_json:
        out_p = Path(args.out_json)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(json.dumps(metrics, indent=2))
        print(f"Saved evaluation metrics JSON to {out_p}")


if __name__ == "__main__":
    main()
