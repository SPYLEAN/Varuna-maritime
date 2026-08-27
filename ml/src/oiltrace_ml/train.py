from __future__ import annotations
import argparse
import random
from pathlib import Path
import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader
from .data import pair_images_and_masks, OilSpillDataset
from .model import SmallUNet
from .metrics import dice_loss, binary_metrics


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
    totals = {k: 0.0 for k in ["dice", "iou", "precision", "recall"]}
    n = 0
    ctx = torch.enable_grad() if train else torch.no_grad()
    with ctx:
        for images, masks in loader:
            images, masks = images.to(device), masks.to(device)
            if train:
                optimizer.zero_grad(set_to_none=True)
            logits = model(images)
            loss = bce(logits, masks) + dice_loss(logits, masks)
            if train:
                loss.backward()
                optimizer.step()
            m = binary_metrics(logits.detach(), masks)
            total_loss += loss.item()
            n += 1
            for k in totals:
                totals[k] += m[k]
    return total_loss / max(n, 1), {k: v / max(n, 1) for k, v in totals.items()}


def train_model(
    images_dir: str | Path,
    masks_dir: str | Path,
    epochs: int = 5,
    batch_size: int = 8,
    image_size: int = 256,
    lr: float = 1e-3,
    val_frac: float = 0.2,
    max_samples: int = 0,
    out_path: str | Path = "models/oiltrace_unet.pt",
    seed: int = 42,
    num_workers: int = 0,
) -> dict:
    seed_all(seed)
    pairs = pair_images_and_masks(images_dir, masks_dir)
    random.shuffle(pairs)

    if max_samples > 0:
        pairs = pairs[:max_samples]

    if len(pairs) < 2:
        raise ValueError(f"Dataset must contain at least 2 paired samples, found {len(pairs)}")

    cut = max(1, int(len(pairs) * (1 - val_frac)))
    if cut >= len(pairs):
        cut = max(1, len(pairs) - 1)

    train_pairs, val_pairs = pairs[:cut], pairs[cut:]
    print(f"Dataset split: train={len(train_pairs)} val={len(val_pairs)}")

    train_ds = OilSpillDataset(train_pairs, image_size)
    val_ds = OilSpillDataset(val_pairs, image_size)

    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True, num_workers=num_workers)
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False, num_workers=num_workers)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device} ({torch.cuda.get_device_name(0) if device.type == 'cuda' else 'CPU'})")

    model = SmallUNet().to(device)
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
            torch.save(
                {
                    "model": model.state_dict(),
                    "image_size": image_size,
                    "val_metrics": va_m,
                    "epoch": epoch,
                },
                out,
            )
            print(f"  --> Saved new best checkpoint to {out} (val_dice: {best_val_dice:.4f})")

    return {"best_val_dice": best_val_dice, "best_metrics": best_metrics, "checkpoint": str(out)}


def main():
    ap = argparse.ArgumentParser(description="Train U-Net for SAR oil-spill segmentation.")
    ap.add_argument("--images", required=True, help="Path to SAR images directory")
    ap.add_argument("--masks", required=True, help="Path to ground-truth masks directory")
    ap.add_argument("--epochs", type=int, default=5, help="Number of epochs")
    ap.add_argument("--batch-size", type=int, default=8, help="Batch size")
    ap.add_argument("--image-size", type=int, default=256, help="Target image size")
    ap.add_argument("--lr", type=float, default=1e-3, help="Learning rate")
    ap.add_argument("--val-frac", type=float, default=0.2, help="Validation fraction")
    ap.add_argument("--max-samples", type=int, default=0, help="Limit max samples for quick smoke tests")
    ap.add_argument("--out", default="models/oiltrace_unet.pt", help="Output model checkpoint path")
    ap.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    ap.add_argument("--num-workers", type=int, default=0, help="DataLoader num_workers")
    args = ap.parse_args()

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
    )


if __name__ == "__main__":
    main()
