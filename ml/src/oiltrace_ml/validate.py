from __future__ import annotations
import argparse
import json
from pathlib import Path
from typing import Any, TypedDict
from .data import (
    Sentinel1Dataset,
    list_images,
    load_sentinel1_manifest,
    pair_images_and_masks,
    read_grayscale,
)
from .preprocessing import SARPreprocessingConfig, config_for_channels
from .visualize import create_contact_sheet


class ValidationReport(TypedDict):
    image_count: int
    mask_count: int
    paired_samples: int
    unmatched_images: list[str]
    unmatched_masks: list[str]
    unreadable_corrupt_files: list[str]
    shape_mismatches: list[dict]
    empty_masks: int
    empty_masks_pct: float
    total_oil_pixels: int
    total_pixels: int
    percentage_positive_oil_pixels: float


def validate_dataset(image_root: str | Path, mask_root: str | Path) -> ValidationReport:
    image_paths = list_images(image_root)
    mask_paths = list_images(mask_root)

    img_map = {p.stem: p for p in image_paths}
    mask_map = {p.stem: p for p in mask_paths}

    unmatched_imgs = [str(p) for stem, p in img_map.items() if stem not in mask_map]
    unmatched_msks = [str(p) for stem, p in mask_map.items() if stem not in img_map]

    common_stems = sorted(set(img_map.keys()) & set(mask_map.keys()))
    pairs = [(img_map[s], mask_map[s]) for s in common_stems]

    corrupt_files: list[str] = []
    shape_mismatches: list[dict] = []
    empty_masks_count = 0
    valid_pairs_count = 0
    total_oil_pixels = 0
    total_pixels = 0

    for img_p, mask_p in pairs:
        try:
            img = read_grayscale(img_p)
        except Exception as err:
            corrupt_files.append(f"Image: {img_p} ({err})")
            continue

        try:
            mask = read_grayscale(mask_p)
        except Exception as err:
            corrupt_files.append(f"Mask: {mask_p} ({err})")
            continue

        if img.shape != mask.shape:
            shape_mismatches.append({
                "image": str(img_p),
                "image_shape": img.shape,
                "mask": str(mask_p),
                "mask_shape": mask.shape,
            })

        pos_pixels = int((mask > 0.5).sum())
        pix_count = int(mask.size)

        if pos_pixels == 0:
            empty_masks_count += 1

        total_oil_pixels += pos_pixels
        total_pixels += pix_count
        valid_pairs_count += 1

    empty_pct = (empty_masks_count / valid_pairs_count * 100.0) if valid_pairs_count > 0 else 0.0
    oil_pixel_pct = (total_oil_pixels / total_pixels * 100.0) if total_pixels > 0 else 0.0

    report: ValidationReport = {
        "image_count": len(image_paths),
        "mask_count": len(mask_paths),
        "paired_samples": len(pairs),
        "unmatched_images": unmatched_imgs,
        "unmatched_masks": unmatched_msks,
        "unreadable_corrupt_files": corrupt_files,
        "shape_mismatches": shape_mismatches,
        "empty_masks": empty_masks_count,
        "empty_masks_pct": round(empty_pct, 2),
        "total_oil_pixels": total_oil_pixels,
        "total_pixels": total_pixels,
        "percentage_positive_oil_pixels": round(oil_pixel_pct, 4),
    }
    return report


def validate_sentinel1_dataset(
    manifest_path: str | Path,
    *,
    preprocessing: SARPreprocessingConfig | None = None,
    channel_order: tuple[str, ...] = ("VV", "VH"),
) -> dict[str, Any]:
    """Exhaustively read a V1 manifest and collect integrity/category results."""

    samples = load_sentinel1_manifest(manifest_path)
    config = preprocessing or config_for_channels(channel_order)
    categories = {"oil": 0, "lookalike": 0, "no_oil": 0}
    empty_masks = {"oil": 0, "lookalike": 0, "no_oil": 0}
    errors: list[dict[str, str]] = []
    valid_samples = 0

    for sample in samples:
        categories[sample.scene_category] += 1
        try:
            dataset = Sentinel1Dataset(
                [sample],
                image_size=1,
                channel_order=channel_order,
                preprocessing=config,
            )
            _, _, metadata = dataset[0]
            if metadata["mask_is_empty"]:
                empty_masks[sample.scene_category] += 1
            valid_samples += 1
        except (FileNotFoundError, ValueError) as err:
            errors.append({"scene_id": sample.scene_id, "error": str(err)})

    return {
        "manifest": str(Path(manifest_path)),
        "sample_count": len(samples),
        "valid_samples": valid_samples,
        "invalid_samples": len(errors),
        "channel_order": list(channel_order),
        "preprocessing": config.to_dict(),
        "category_counts": categories,
        "empty_masks_by_category": empty_masks,
        "errors": errors,
    }


def main():
    ap = argparse.ArgumentParser(description="Validate SAR oil-spill dataset integrity and stats.")
    ap.add_argument("--images", help="Legacy directory containing SAR images")
    ap.add_argument("--masks", help="Legacy directory containing ground-truth masks")
    ap.add_argument("--manifest", help="V1 Sentinel-1 CSV/JSON/JSONL manifest")
    ap.add_argument("--channel-order", nargs="+", default=["VV", "VH"])
    ap.add_argument("--preprocessing-method", choices=["fixed_db", "robust_percentile"], default="fixed_db")
    ap.add_argument("--db-min", nargs="+", type=float, default=None)
    ap.add_argument("--db-max", nargs="+", type=float, default=None)
    ap.add_argument("--visualize-out", help="Optional path to save contact sheet PNG")
    ap.add_argument("--num-samples", type=int, default=6, help="Number of samples for contact sheet")
    args = ap.parse_args()

    if args.manifest:
        config = config_for_channels(
            args.channel_order,
            method=args.preprocessing_method,
            db_min=args.db_min,
            db_max=args.db_max,
        )
        report = validate_sentinel1_dataset(
            args.manifest,
            preprocessing=config,
            channel_order=tuple(args.channel_order),
        )
        print(json.dumps(report, indent=2))
        return
    if not args.images or not args.masks:
        ap.error("Provide --manifest for V1 or both --images and --masks for legacy V0 validation")

    report = validate_dataset(args.images, args.masks)

    print("==================================================")
    print("           DATASET VALIDATION REPORT              ")
    print("==================================================")
    print(f"Image count                      : {report['image_count']}")
    print(f"Mask count                       : {report['mask_count']}")
    print(f"Paired samples                   : {report['paired_samples']}")
    print(f"Unmatched images                 : {len(report['unmatched_images'])}")
    print(f"Unmatched masks                  : {len(report['unmatched_masks'])}")
    print(f"Unreadable/corrupt files         : {len(report['unreadable_corrupt_files'])}")
    print(f"Image/mask shape mismatches     : {len(report['shape_mismatches'])}")
    print(f"Empty masks                      : {report['empty_masks']} ({report['empty_masks_pct']}%)")
    print(f"Percentage of positive oil pixels: {report['percentage_positive_oil_pixels']}%")
    print("==================================================")

    if report["unmatched_images"]:
        print(f"\nUnmatched Images Sample: {report['unmatched_images'][:5]}")
    if report["unmatched_masks"]:
        print(f"Unmatched Masks Sample: {report['unmatched_masks'][:5]}")
    if report["unreadable_corrupt_files"]:
        print(f"Corrupt Files: {report['unreadable_corrupt_files']}")
    if report["shape_mismatches"]:
        print(f"Shape Mismatches: {report['shape_mismatches'][:5]}")

    if args.visualize_out:
        pairs = pair_images_and_masks(args.images, args.masks)
        if pairs:
            out_file = create_contact_sheet(pairs, num_samples=args.num_samples, out_path=args.visualize_out)
            print(f"\nSaved visualization contact sheet to {out_file}")


if __name__ == "__main__":
    main()
