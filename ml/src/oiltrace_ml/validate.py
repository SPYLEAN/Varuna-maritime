from __future__ import annotations
import argparse
from collections import Counter
from .data import list_images, pair_images_and_masks, read_grayscale


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", required=True)
    ap.add_argument("--masks", required=True)
    ap.add_argument("--sample", type=int, default=25)
    args = ap.parse_args()

    images = list_images(args.images)
    masks = list_images(args.masks)
    pairs = pair_images_and_masks(args.images, args.masks)
    print(f"images={len(images)} masks={len(masks)} paired={len(pairs)}")
    if not pairs:
        raise SystemExit("No paired files found. Ensure image and mask basenames match.")

    shape_counts = Counter()
    oil_fracs = []
    for img_p, mask_p in pairs[:args.sample]:
        img = read_grayscale(img_p)
        mask = read_grayscale(mask_p)
        shape_counts[(img.shape, mask.shape)] += 1
        oil_fracs.append(float((mask > 0.5).mean()))
    print("sample shape pairs:", dict(shape_counts))
    print(f"sample oil-pixel fraction: min={min(oil_fracs):.4f} mean={sum(oil_fracs)/len(oil_fracs):.4f} max={max(oil_fracs):.4f}")


if __name__ == "__main__":
    main()
