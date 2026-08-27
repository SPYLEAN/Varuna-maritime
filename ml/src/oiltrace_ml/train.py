from __future__ import annotations
import argparse, random
from pathlib import Path
import torch
from torch import nn
from torch.utils.data import DataLoader
from .data import pair_images_and_masks, OilSpillDataset
from .model import SmallUNet
from .metrics import dice_loss, binary_metrics


def seed_all(seed=42):
    random.seed(seed); torch.manual_seed(seed)
    if torch.cuda.is_available(): torch.cuda.manual_seed_all(seed)


def run_epoch(model, loader, optimizer, device, train=True):
    model.train(train)
    bce = nn.BCEWithLogitsLoss()
    total_loss = 0.0
    totals = {k: 0.0 for k in ["dice","iou","precision","recall"]}
    n = 0
    ctx = torch.enable_grad() if train else torch.no_grad()
    with ctx:
        for images, masks in loader:
            images, masks = images.to(device), masks.to(device)
            if train: optimizer.zero_grad(set_to_none=True)
            logits = model(images)
            loss = bce(logits, masks) + dice_loss(logits, masks)
            if train:
                loss.backward(); optimizer.step()
            m = binary_metrics(logits.detach(), masks)
            total_loss += loss.item(); n += 1
            for k in totals: totals[k] += m[k]
    return total_loss/max(n,1), {k:v/max(n,1) for k,v in totals.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", required=True)
    ap.add_argument("--masks", required=True)
    ap.add_argument("--epochs", type=int, default=5)
    ap.add_argument("--batch-size", type=int, default=8)
    ap.add_argument("--image-size", type=int, default=256)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--val-frac", type=float, default=0.2)
    ap.add_argument("--max-samples", type=int, default=0, help="0 = all; use 100-300 for smoke test")
    ap.add_argument("--out", default="models/oiltrace_unet.pt")
    args = ap.parse_args()

    seed_all(42)
    pairs = pair_images_and_masks(args.images, args.masks)
    random.shuffle(pairs)
    if args.max_samples > 0: pairs = pairs[:args.max_samples]
    if len(pairs) < 10: raise SystemExit(f"Need at least 10 paired samples, found {len(pairs)}")
    cut = max(1, int(len(pairs)*(1-args.val_frac)))
    train_pairs, val_pairs = pairs[:cut], pairs[cut:]
    print(f"train={len(train_pairs)} val={len(val_pairs)}")

    train_ds = OilSpillDataset(train_pairs, args.image_size)
    val_ds = OilSpillDataset(val_pairs, args.image_size)
    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True, num_workers=2, pin_memory=True)
    val_loader = DataLoader(val_ds, batch_size=args.batch_size, shuffle=False, num_workers=2, pin_memory=True)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print("device=", device)
    model = SmallUNet().to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    best = -1.0
    out = Path(args.out); out.parent.mkdir(parents=True, exist_ok=True)

    for epoch in range(1, args.epochs+1):
        tr_loss, tr_m = run_epoch(model, train_loader, optimizer, device, train=True)
        va_loss, va_m = run_epoch(model, val_loader, optimizer, device, train=False)
        print(f"epoch={epoch:02d} train_loss={tr_loss:.4f} val_loss={va_loss:.4f} val_dice={va_m['dice']:.4f} val_iou={va_m['iou']:.4f} val_precision={va_m['precision']:.4f} val_recall={va_m['recall']:.4f}")
        if va_m["dice"] > best:
            best = va_m["dice"]
            torch.save({"model": model.state_dict(), "image_size": args.image_size, "val_metrics": va_m}, out)
            print("saved", out)


if __name__ == "__main__":
    main()
