from __future__ import annotations
import argparse
from pathlib import Path
from typing import Any
import cv2
import numpy as np
import rasterio
import torch
from .checkpoint import load_model_from_checkpoint
from .data import read_grayscale, read_sentinel1_stack
from .preprocessing import SARPreprocessingConfig


def run_inference(
    checkpoint_path: str | Path,
    image_path: str | Path,
    binary_out_path: str | Path,
    prob_out_path: str | Path | None = None,
    threshold: float = 0.5,
    vh_image_path: str | Path | None = None,
    preprocessing: SARPreprocessingConfig | None = None,
) -> dict:
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("threshold must be between 0 and 1")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model, metadata, size = load_model_from_checkpoint(checkpoint_path, device=device)
    model.eval()

    input_channels = int(metadata["input_channels"])
    if input_channels == 1:
        if vh_image_path is not None:
            raise ValueError("A legacy one-channel checkpoint does not accept --vh-image")
        raw = read_grayscale(image_path)
        orig_h, orig_w = raw.shape
        img = cv2.resize(raw, (size, size), interpolation=cv2.INTER_LINEAR)
        x = torch.from_numpy(img).unsqueeze(0).unsqueeze(0).float().to(device)
    elif input_channels == 2:
        if vh_image_path is None:
            raise ValueError("A two-channel checkpoint requires an explicit VH GeoTIFF")
        channel_order = tuple(metadata["channel_order"])
        if preprocessing is None:
            preprocessing_values = metadata.get("preprocessing", {})
            if preprocessing_values.get("method") not in {"fixed_db", "robust_percentile"}:
                raise ValueError("Two-channel checkpoint lacks usable SAR preprocessing metadata")
            preprocessing = SARPreprocessingConfig.from_dict(preprocessing_values)
        stack, raster_metadata = read_sentinel1_stack(
            image_path,
            vh_image_path,
            channel_order=channel_order,
            preprocessing=preprocessing,
        )
        orig_h, orig_w = raster_metadata["shape"]
        resized = np.stack(
            [cv2.resize(channel, (size, size), interpolation=cv2.INTER_LINEAR) for channel in stack],
            axis=0,
        ).astype(np.float32)
        x = torch.from_numpy(resized).unsqueeze(0).float().to(device)
    else:
        raise ValueError(f"Unsupported checkpoint input channel count: {input_channels}")

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
        "input_channels": input_channels,
        "channel_order": metadata["channel_order"],
    }


def main():
    ap = argparse.ArgumentParser(description="Run SAR oil-spill U-Net segmentation inference on an unseen image.")
    ap.add_argument("--checkpoint", required=True, help="Path to trained model checkpoint (.pt)")
    ap.add_argument("--image", required=True, help="Path to unseen SAR image file")
    ap.add_argument("--vh-image", help="V1 VH GeoTIFF; --image is the VV GeoTIFF")
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
        vh_image_path=args.vh_image,
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


def run_windowed_inference(
    checkpoint_path: str | Path,
    image_path: str | Path,
    vh_image_path: str | Path,
    output_geotiff_path: str | Path,
    prob_geotiff_path: str | Path | None = None,
    threshold: float = 0.5,
    tile_size: int = 256,
    stride: int = 128,
    preprocessing: SARPreprocessingConfig | None = None,
) -> dict[str, Any]:
    """Execute windowed/tiled dual-channel inference over a large GeoTIFF.

    Reconstructs full floating-point probability map using sliding window tiles,
    thresholds only after reconstruction, and writes georeferenced GeoTIFF(s)
    preserving exact CRS, transform, bounds, and resolution.
    """
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("threshold must be between 0 and 1")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model, metadata, model_tile_size = load_model_from_checkpoint(checkpoint_path, device=device)
    model.eval()

    if int(metadata["input_channels"]) != 2:
        raise ValueError("Windowed dual-channel inference requires a 2-channel checkpoint")

    channel_order = tuple(metadata["channel_order"])
    if preprocessing is None:
        preprocessing_values = metadata.get("preprocessing", {})
        if preprocessing_values.get("method") not in {"fixed_db", "robust_percentile"}:
            raise ValueError("Two-channel checkpoint lacks usable SAR preprocessing metadata")
        preprocessing = SARPreprocessingConfig.from_dict(preprocessing_values)

    stack, raster_meta = read_sentinel1_stack(
        image_path,
        vh_image_path,
        channel_order=channel_order,
        preprocessing=preprocessing,
    )

    _, orig_h, orig_w = stack.shape
    patch_sz = min(tile_size, orig_h, orig_w)
    st = min(stride, patch_sz)

    prob_accum = np.zeros((orig_h, orig_w), dtype=np.float32)
    weight_accum = np.zeros((orig_h, orig_w), dtype=np.float32)

    window_1d = np.hanning(patch_sz)
    window_2d = np.outer(window_1d, window_1d).astype(np.float32)
    window_2d = np.maximum(window_2d, 1e-4)

    y_steps = list(range(0, orig_h - patch_sz + 1, st))
    if not y_steps or y_steps[-1] + patch_sz < orig_h:
        y_steps.append(max(0, orig_h - patch_sz))

    x_steps = list(range(0, orig_w - patch_sz + 1, st))
    if not x_steps or x_steps[-1] + patch_sz < orig_w:
        x_steps.append(max(0, orig_w - patch_sz))

    with torch.no_grad():
        for y in y_steps:
            for x in x_steps:
                tile = stack[:, y : y + patch_sz, x : x + patch_sz]
                if patch_sz != model_tile_size:
                    resized_channels = [
                        cv2.resize(ch, (model_tile_size, model_tile_size), interpolation=cv2.INTER_LINEAR)
                        for ch in tile
                    ]
                    tile_tensor = torch.from_numpy(np.stack(resized_channels, axis=0)).unsqueeze(0).float().to(device)
                else:
                    tile_tensor = torch.from_numpy(tile).unsqueeze(0).float().to(device)

                prob_tile = torch.sigmoid(model(tile_tensor))[0, 0].cpu().numpy()
                if patch_sz != model_tile_size:
                    prob_tile = cv2.resize(prob_tile, (patch_sz, patch_sz), interpolation=cv2.INTER_LINEAR)

                prob_accum[y : y + patch_sz, x : x + patch_sz] += prob_tile * window_2d
                weight_accum[y : y + patch_sz, x : x + patch_sz] += window_2d

    weight_accum = np.maximum(weight_accum, 1e-6)
    full_prob = prob_accum / weight_accum
    binary_mask = (full_prob >= threshold).astype(np.uint8) * 255

    out_p = Path(output_geotiff_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)

    with rasterio.open(Path(image_path)) as src:
        profile = src.profile.copy()

    profile.update(dtype=rasterio.uint8, count=1, driver="GTiff")
    with rasterio.open(out_p, "w", **profile) as dst:
        dst.write(binary_mask, 1)

    prob_out_str = None
    if prob_geotiff_path:
        prob_p = Path(prob_geotiff_path)
        prob_p.parent.mkdir(parents=True, exist_ok=True)
        prob_profile = profile.copy()
        prob_profile.update(dtype=rasterio.float32, count=1, driver="GTiff")
        with rasterio.open(prob_p, "w", **prob_profile) as dst:
            dst.write(full_prob.astype(np.float32), 1)
        prob_out_str = str(prob_p)

    oil_px = int((binary_mask > 0).sum())
    return {
        "binary_geotiff_path": str(out_p),
        "probability_geotiff_path": prob_out_str,
        "oil_pixels": oil_px,
        "oil_fraction": float(oil_px / binary_mask.size),
        "mean_probability": float(full_prob.mean()),
        "max_probability": float(full_prob.max()),
        "threshold": float(threshold),
        "shape": (orig_h, orig_w),
        "crs": raster_meta["crs"],
        "transform": raster_meta["transform"],
        "bounds": raster_meta["bounds"],
    }


if __name__ == "__main__":
    main()
