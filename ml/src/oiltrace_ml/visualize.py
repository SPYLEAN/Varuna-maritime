from __future__ import annotations
import argparse
from pathlib import Path
import random
import cv2
import numpy as np
from .data import list_images, pair_images_and_masks, read_grayscale


def create_contact_sheet(
    pairs: list[tuple[Path, Path]],
    num_samples: int = 6,
    out_path: str | Path = "contact_sheet.png",
    sample_size: int = 256,
    seed: int = 42,
) -> Path:
    if not pairs:
        raise ValueError("No image/mask pairs available for contact sheet generation.")

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    rng = random.Random(seed)
    n = min(len(pairs), max(1, num_samples))
    sampled_pairs = rng.sample(pairs, n)

    rows = []
    header_h = 30
    padding = 10

    for img_p, mask_p in sampled_pairs:
        try:
            raw_img = read_grayscale(img_p)
            raw_mask = read_grayscale(mask_p)
        except Exception as err:
            print(f"Warning: Failed to read pair ({img_p.name}, {mask_p.name}): {err}")
            continue

        img_resized = cv2.resize(raw_img, (sample_size, sample_size), interpolation=cv2.INTER_LINEAR)
        mask_resized = cv2.resize(raw_mask, (sample_size, sample_size), interpolation=cv2.INTER_NEAREST)

        # Convert to 8-bit uint8 BGR for visualization
        img_bgr = cv2.cvtColor((img_resized * 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)
        
        # Color overlay mask: red for oil spill (>0.5)
        mask_binary = (mask_resized > 0.5)
        mask_bgr = np.zeros((sample_size, sample_size, 3), dtype=np.uint8)
        mask_bgr[mask_binary] = [0, 0, 255]  # Red for oil pixels
        mask_bgr[~mask_binary] = cv2.cvtColor((mask_resized * 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)[~mask_binary]

        # Combine SAR image and mask side-by-side
        pair_viz = np.hstack([img_bgr, mask_bgr])  # Width = sample_size * 2

        # Add top header with file stem name
        canvas_w = sample_size * 2
        canvas = np.zeros((sample_size + header_h + padding, canvas_w, 3), dtype=np.uint8)
        canvas[:header_h, :] = (40, 40, 40)
        label = f"{img_p.stem} (Left: SAR | Right: GT Mask)"
        cv2.putText(canvas, label, (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)
        canvas[header_h:header_h + sample_size, :] = pair_viz
        rows.append(canvas)

    if not rows:
        raise ValueError("Could not generate any valid visual pairs for contact sheet.")

    contact_sheet = np.vstack(rows)
    cv2.imwrite(str(out_path), contact_sheet)
    return out_path


def main():
    ap = argparse.ArgumentParser(description="Generate a contact sheet of SAR images and ground-truth masks.")
    ap.add_argument("--images", required=True, help="Directory containing SAR images")
    ap.add_argument("--masks", required=True, help="Directory containing ground-truth masks")
    ap.add_argument("--out", default="contact_sheet.png", help="Output contact sheet image path")
    ap.add_argument("--num-samples", type=int, default=6, help="Number of random samples to show")
    ap.add_argument("--seed", type=int, default=42, help="Random seed for sampling")
    args = ap.parse_args()

    pairs = pair_images_and_masks(args.images, args.masks)
    out_file = create_contact_sheet(pairs, num_samples=args.num_samples, out_path=args.out, seed=args.seed)
    print(f"Saved contact sheet with {min(len(pairs), args.num_samples)} sample pairs to {out_file}")


if __name__ == "__main__":
    main()
