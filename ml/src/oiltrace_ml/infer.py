from __future__ import annotations
import argparse
from pathlib import Path
import cv2
import numpy as np
import torch
from .data import read_grayscale
from .model import SmallUNet


def run_inference(
    checkpoint_path: str | Path,
    image_path: str | Path,
    binary_out_path: str | Path,
    prob_out_path: str | Path | None = None,
    threshold: float = 0.5,
) -> dict:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    ckpt = torch.load(checkpoint_path, map_location=device)
    size = int(ckpt.get("image_size", 256)) if isinstance(ckpt, dict) else 256

    model = SmallUNet().to(device)
    state_dict = ckpt["model"] if isinstance(ckpt, dict) and "model" in ckpt else ckpt
    model.load_state_dict(state_dict)
    model.eval()

    raw = read_grayscale(image_path)
    orig_h, orig_w = raw.shape

    # Resize image to model resolution
    img = cv2.resize(raw, (size, size), interpolation=cv2.INTER_LINEAR)
    x = torch.from_numpy(img).unsqueeze(0).unsqueeze(0).float().to(device)

    with torch.no_grad():
        prob = torch.sigmoid(model(x))[0, 0].cpu().numpy()

    # Resize probability map back to original image dimensions
    prob_resized = cv2.resize(prob, (orig_w, orig_h), interpolation=cv2.INTER_LINEAR)
    prob_uint8 = (np.clip(prob_resized, 0, 1) * 255.0).astype(np.uint8)

    # Threshold probability map to produce binary oil-spill mask
    binary_mask = (prob_resized >= threshold).astype(np.uint8) * 255
    oil_pixels_mask = (binary_mask > 0)

    # Compute exact raw model-output statistics
    oil_fraction = float(oil_pixels_mask.sum() / binary_mask.size)
    mean_probability = float(prob_resized.mean())
    max_probability = float(prob_resized.max())
    
    if oil_pixels_mask.sum() > 0:
        mean_oil_probability = float(prob_resized[oil_pixels_mask].mean())
    else:
        mean_oil_probability = None

    # Save thresholded binary oil-spill mask
    bin_out = Path(binary_out_path)
    bin_out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(bin_out), binary_mask)

    # Save continuous probability mask if requested
    prob_saved_path = None
    if prob_out_path:
        p_out = Path(prob_out_path)
        p_out.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(p_out), prob_uint8)
        prob_saved_path = str(p_out)

    return {
        "binary_mask_path": str(bin_out),
        "probability_mask_path": prob_saved_path,
        "oil_fraction": round(oil_fraction, 6),
        "mean_probability": round(mean_probability, 6),
        "mean_oil_probability": round(mean_oil_probability, 6) if mean_oil_probability is not None else None,
        "max_probability": round(max_probability, 6),
        "threshold": round(float(threshold), 4),
        "original_shape": (orig_h, orig_w),
    }


def main():
    ap = argparse.ArgumentParser(description="Run SAR oil-spill U-Net segmentation inference on an unseen image.")
    ap.add_argument("--checkpoint", required=True, help="Path to trained model checkpoint (.pt)")
    ap.add_argument("--image", required=True, help="Path to unseen SAR image file")
    ap.add_argument("--out", required=True, help="Output path for thresholded binary mask PNG")
    ap.add_argument("--prob-out", help="Optional output path for probability mask PNG")
    ap.add_argument("--threshold", type=float, default=0.5, help="Probability decision threshold")
    args = ap.parse_args()

    res = run_inference(
        checkpoint_path=args.checkpoint,
        image_path=args.image,
        binary_out_path=args.out,
        prob_out_path=args.prob_out,
        threshold=args.threshold,
    )

    print(f"Inference complete on {args.image}:")
    print(f"  Binary mask saved to     : {res['binary_mask_path']}")
    if res["probability_mask_path"]:
        print(f"  Probability mask saved to: {res['probability_mask_path']}")
    print(f"  Oil fraction             : {res['oil_fraction']:.6f}")
    print(f"  Mean probability         : {res['mean_probability']:.6f}")
    if res['mean_oil_probability'] is not None:
        print(f"  Mean oil probability     : {res['mean_oil_probability']:.6f}")
    else:
        print("  Mean oil probability     : null (no oil pixels predicted)")
    print(f"  Max probability          : {res['max_probability']:.6f}")
    print(f"  Threshold                : {res['threshold']:.4f}")


if __name__ == "__main__":
    main()
