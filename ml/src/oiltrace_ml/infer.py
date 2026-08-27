from __future__ import annotations
import argparse
from pathlib import Path
import cv2
import numpy as np
import torch
from .data import read_grayscale
from .model import SmallUNet


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkpoint", required=True)
    ap.add_argument("--image", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--threshold", type=float, default=0.5)
    args = ap.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    ckpt = torch.load(args.checkpoint, map_location=device)
    size = int(ckpt.get("image_size", 256))
    model = SmallUNet().to(device)
    model.load_state_dict(ckpt["model"] if isinstance(ckpt, dict) and "model" in ckpt else ckpt)
    model.eval()

    raw = read_grayscale(args.image)
    h, w = raw.shape
    img = cv2.resize(raw, (size, size), interpolation=cv2.INTER_LINEAR)
    x = torch.from_numpy(img).unsqueeze(0).unsqueeze(0).float().to(device)
    with torch.no_grad():
        prob = torch.sigmoid(model(x))[0,0].cpu().numpy()
    mask = (prob >= args.threshold).astype(np.uint8) * 255
    mask = cv2.resize(mask, (w, h), interpolation=cv2.INTER_NEAREST)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(args.out, mask)
    print(f"wrote {args.out}; oil_fraction={(mask>0).mean():.4f}")


if __name__ == "__main__":
    main()
