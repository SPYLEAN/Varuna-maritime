from __future__ import annotations
import argparse
import random
from pathlib import Path
import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader
from .checkpoint import (
    FROZEN_V0_CHECKPOINT_NAME,
    SMALL_UNET_ARCHITECTURE,
    build_checkpoint,
    create_checkpoint_metadata,
)
from .data import OilSpillDataset, Sentinel1Dataset, load_sentinel1_manifest, pair_images_and_masks
from .model import SmallUNet
from .metrics import binary_confusion_counts, dice_loss, segmentation_metrics_from_counts
from .preprocessing import SARPreprocessingConfig, config_for_channels


def seed_all(seed: int = 42):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False


def run_epoch(model, loader, optimizer, device, train=True):
    model.train(train)
    bce = nn.BCEWithLogitsLoss()
    total_loss = 0.0
    counts = {"tp": 0, "fp": 0, "fn": 0}
    n = 0
    ctx = torch.enable_grad() if train else torch.no_grad()
    with ctx:
        for batch in loader:
            images, masks = batch[:2]
            images, masks = images.to(device), masks.to(device)
            if train:
                optimizer.zero_grad(set_to_none=True)
            logits = model(images)
            loss = bce(logits, masks) + dice_loss(logits, masks)
            if train:
                loss.backward()
                optimizer.step()
            batch_counts = binary_confusion_counts(logits.detach(), masks)
            total_loss += loss.item()
            n += 1
            for key in counts:
                counts[key] += batch_counts[key]
    return total_loss / max(n, 1), segmentation_metrics_from_counts(**counts)


def train_model(
    images_dir: str | Path | None = None,
    masks_dir: str | Path | None = None,
    epochs: int = 5,
    batch_size: int = 8,
    image_size: int = 256,
    lr: float = 1e-3,
    val_frac: float = 0.2,
    max_samples: int = 0,
    out_path: str | Path = "models/oiltrace_unet.pt",
    seed: int = 42,
    num_workers: int = 0,
    manifest_path: str | Path | None = None,
    val_manifest_path: str | Path | None = None,
    input_channels: int | None = None,
    channel_order: tuple[str, ...] = ("VV", "VH"),
    preprocessing: SARPreprocessingConfig | None = None,
    dataset_version: str | None = None,
    model_version: str | None = None,
) -> dict:
    if Path(out_path).name.casefold() == FROZEN_V0_CHECKPOINT_NAME.casefold():
        raise ValueError(f"Refusing to overwrite frozen V0 checkpoint: {out_path}")
    seed_all(seed)
    if not 0.0 < val_frac < 1.0:
        raise ValueError("val_frac must be between 0 and 1")
    if manifest_path is not None:
        if images_dir is not None or masks_dir is not None:
            raise ValueError("Use either manifest_path or legacy images_dir/masks_dir, not both")
        samples = load_sentinel1_manifest(manifest_path)
        random.shuffle(samples)
        if max_samples > 0:
            samples = samples[:max_samples]
        if val_manifest_path is not None:
            train_samples = samples
            val_samples = load_sentinel1_manifest(val_manifest_path)
            overlap = {sample.scene_id for sample in train_samples} & {sample.scene_id for sample in val_samples}
            if overlap:
                raise ValueError(f"Train/validation manifests share scene_id values: {sorted(overlap)}")
            if not train_samples or not val_samples:
                raise ValueError("Train and validation manifests must both contain samples")
        else:
            if len(samples) < 2:
                raise ValueError(f"Dataset must contain at least 2 samples, found {len(samples)}")
            cut = max(1, min(len(samples) - 1, int(len(samples) * (1 - val_frac))))
            train_samples, val_samples = samples[:cut], samples[cut:]
        resolved_input_channels = 2 if input_channels is None else int(input_channels)
        if resolved_input_channels != 2:
            raise ValueError("The Sentinel-1 VV/VH adapter requires input_channels=2")
        resolved_order = tuple(str(value).upper() for value in channel_order)
        resolved_preprocessing = preprocessing or config_for_channels(resolved_order)
        train_ds = Sentinel1Dataset(
            train_samples, image_size, channel_order=resolved_order, preprocessing=resolved_preprocessing
        )
        val_ds = Sentinel1Dataset(
            val_samples, image_size, channel_order=resolved_order, preprocessing=resolved_preprocessing
        )
        preprocessing_metadata = resolved_preprocessing.to_dict()
        resolved_model_version = model_version or "oilseg-v1"
        if not dataset_version:
            raise ValueError("V1 training requires an explicit dataset_version")
        resolved_dataset_version = dataset_version
    else:
        if val_manifest_path is not None:
            raise ValueError("val_manifest_path requires manifest_path")
        if images_dir is None or masks_dir is None:
            raise ValueError("Legacy training requires both images_dir and masks_dir")
        pairs = pair_images_and_masks(images_dir, masks_dir)
        random.shuffle(pairs)
        if max_samples > 0:
            pairs = pairs[:max_samples]
        if len(pairs) < 2:
            raise ValueError(f"Dataset must contain at least 2 paired samples, found {len(pairs)}")
        resolved_input_channels = 1 if input_channels is None else int(input_channels)
        if resolved_input_channels != 1:
            raise ValueError("The legacy OilSpillDataset produces exactly one input channel")
        resolved_order = ("GRAYSCALE",)
        cut = max(1, min(len(pairs) - 1, int(len(pairs) * (1 - val_frac))))
        train_ds = OilSpillDataset(pairs[:cut], image_size)
        val_ds = OilSpillDataset(pairs[cut:], image_size)
        preprocessing_metadata = {"method": "legacy_per_image_minmax", "output_range": [0.0, 1.0]}
        resolved_model_version = model_version or "oilseg-v0-compatible"
        resolved_dataset_version = dataset_version or "legacy-v0-compatible"

    print(f"Dataset split: train={len(train_ds)} val={len(val_ds)}")

    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True, num_workers=num_workers)
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False, num_workers=num_workers)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device} ({torch.cuda.get_device_name(0) if device.type == 'cuda' else 'CPU'})")

    model = SmallUNet(in_channels=resolved_input_channels).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)

    best_val_dice = -1.0
    best_metrics = {}
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    for epoch in range(1, epochs + 1):
        tr_loss, tr_m = run_epoch(model, train_loader, optimizer, device, train=True)
        va_loss, va_m = run_epoch(model, val_loader, optimizer, device, train=False)

        print(
            f"Epoch {epoch:02d}/{epochs:02d} | "
            f"train_loss: {tr_loss:.4f} | val_loss: {va_loss:.4f} | "
            f"val_dice: {va_m['dice']:.4f} | val_iou: {va_m['iou']:.4f} | "
            f"val_precision: {va_m['precision']:.4f} | val_recall: {va_m['recall']:.4f}"
        )

        if va_m["dice"] > best_val_dice:
            best_val_dice = va_m["dice"]
            best_metrics = va_m
            metadata = create_checkpoint_metadata(
                model_architecture=SMALL_UNET_ARCHITECTURE,
                model_version=resolved_model_version,
                input_channels=resolved_input_channels,
                channel_order=resolved_order,
                preprocessing=preprocessing_metadata,
                training_dataset_version=resolved_dataset_version,
                epoch=epoch,
                validation_metrics=va_m,
            )
            torch.save(build_checkpoint(model, image_size=image_size, metadata=metadata), out)
            print(f"  --> Saved new best checkpoint to {out} (val_dice: {best_val_dice:.4f})")

    return {"best_val_dice": best_val_dice, "best_metrics": best_metrics, "checkpoint": str(out)}


def main():
    ap = argparse.ArgumentParser(description="Train U-Net for SAR oil-spill segmentation.")
    ap.add_argument("--images", help="Legacy V0 path to single-channel SAR images directory")
    ap.add_argument("--masks", help="Legacy V0 path to ground-truth masks directory")
    ap.add_argument("--manifest", help="V1 Sentinel-1 CSV/JSON/JSONL manifest")
    ap.add_argument("--val-manifest", help="Recommended explicit held-out V1 validation manifest")
    ap.add_argument("--epochs", type=int, default=5, help="Number of epochs")
    ap.add_argument("--batch-size", type=int, default=8, help="Batch size")
    ap.add_argument("--image-size", type=int, default=256, help="Target image size")
    ap.add_argument("--lr", type=float, default=1e-3, help="Learning rate")
    ap.add_argument("--val-frac", type=float, default=0.2, help="Validation fraction")
    ap.add_argument("--max-samples", type=int, default=0, help="Limit max samples for quick smoke tests")
    ap.add_argument("--out", default="models/oiltrace_unet.pt", help="Output model checkpoint path")
    ap.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    ap.add_argument("--num-workers", type=int, default=0, help="DataLoader num_workers")
    ap.add_argument("--dataset-version", help="Required versioned dataset identifier for V1")
    ap.add_argument("--model-version", help="Checkpoint model version (defaults by dataset mode)")
    ap.add_argument("--input-channels", type=int, help="Explicit model inputs: 1 for V0, 2 for V1 VV/VH")
    ap.add_argument("--channel-order", nargs="+", default=["VV", "VH"], help="Explicit V1 channel order")
    ap.add_argument(
        "--preprocessing-method",
        choices=["fixed_db", "robust_percentile"],
        default="fixed_db",
        help="V1 Sigma0 dB normalization method",
    )
    ap.add_argument("--db-min", nargs="+", type=float, default=None, help="Per-channel lower dB bounds")
    ap.add_argument("--db-max", nargs="+", type=float, default=None, help="Per-channel upper dB bounds")
    ap.add_argument("--lower-percentile", type=float, default=1.0)
    ap.add_argument("--upper-percentile", type=float, default=99.0)
    args = ap.parse_args()

    if args.manifest:
        preprocessing = config_for_channels(
            args.channel_order,
            method=args.preprocessing_method,
            db_min=args.db_min,
            db_max=args.db_max,
            lower_percentile=args.lower_percentile,
            upper_percentile=args.upper_percentile,
        )
    else:
        preprocessing = None

    train_model(
        images_dir=args.images,
        masks_dir=args.masks,
        epochs=args.epochs,
        batch_size=args.batch_size,
        image_size=args.image_size,
        lr=args.lr,
        val_frac=args.val_frac,
        max_samples=args.max_samples,
        out_path=args.out,
        seed=args.seed,
        num_workers=args.num_workers,
        manifest_path=args.manifest,
        val_manifest_path=args.val_manifest,
        input_channels=args.input_channels,
        channel_order=tuple(args.channel_order),
        preprocessing=preprocessing,
        dataset_version=args.dataset_version,
        model_version=args.model_version,
    )


if __name__ == "__main__":
    main()
