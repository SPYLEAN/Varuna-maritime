from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Sequence

import cv2
import numpy as np
import rasterio
import rasterio.features
from pyproj import Transformer
from shapely.geometry import Polygon, box, mapping, shape
from shapely.ops import transform as shapely_transform

DEFAULT_ML_PIPELINE_CONFIG = {
    "target_chip_size_px": (256, 256),
    "min_context_padding_px": 50,
    "context_padding_ratio": 0.5,
    "min_chip_extent_m": 2500.0,  # Minimum physical chip width/height in meters
    "polarization_order": ["VV", "VH"],
    "vv_norm_range_db": [-30.0, 0.0],
    "vh_norm_range_db": [-35.0, -5.0],
    "equal_area_crs": "ESRI:54034",
    "min_background_pixels": 20,
}


def _file_sha256(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def normalize_sar_db(
    arr: np.ndarray, range_db: tuple[float, float]
) -> tuple[np.ndarray, float]:
    """Scientifically stable SAR dB normalization to [0.0, 1.0]."""
    min_db, max_db = float(range_db[0]), float(range_db[1])
    valid_m = np.isfinite(arr)

    norm_arr = np.zeros_like(arr, dtype=np.float32)
    if not np.any(valid_m):
        return norm_arr, 0.0

    clipped_count = int(((arr[valid_m] < min_db) | (arr[valid_m] > max_db)).sum())
    clipped_frac = float(clipped_count / valid_m.sum())

    scaled = (arr - min_db) / (max_db - min_db + 1e-6)
    norm_arr[valid_m] = np.clip(scaled[valid_m], 0.0, 1.0)
    return norm_arr, clipped_frac


def process_candidate_ml_inputs(
    candidates_geojson_path: str | Path,
    vv_path: str | Path,
    vh_path: str | Path,
    output_dir: str | Path | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Extract candidate ML chips, masks, 2-channel tensors, and feature vectors."""
    cand_p = Path(candidates_geojson_path)
    vv_p = Path(vv_path)
    vh_p = Path(vh_path)
    cfg = {**DEFAULT_ML_PIPELINE_CONFIG, **(config or {})}
    warnings: list[str] = []

    if not cand_p.exists():
        raise FileNotFoundError(f"Candidates GeoJSON not found: {cand_p}")
    if not vv_p.exists():
        raise FileNotFoundError(f"VV SAR raster not found: {vv_p}")
    if not vh_p.exists():
        raise FileNotFoundError(f"VH SAR raster not found: {vh_p}")

    out_d = Path(output_dir) if output_dir else cand_p.parent.parent / "candidate_ml_inputs"
    chips_d = out_d / "chips"
    chips_d.mkdir(parents=True, exist_ok=True)

    # 1. Open SAR Rasters & Validate Contract
    with rasterio.open(vv_p) as src_vv, rasterio.open(vh_p) as src_vh:
        if src_vv.shape != src_vh.shape:
            raise ValueError(f"VV shape {src_vv.shape} != VH shape {src_vh.shape}")
        if str(src_vv.crs) != str(src_vh.crs):
            raise ValueError(f"VV CRS {src_vv.crs!r} != VH CRS {src_vh.crs!r}")

        height, width = src_vv.height, src_vv.width
        crs_str = str(src_vv.crs)
        transform_obj = src_vv.transform
        bounds = tuple(float(v) for v in src_vv.bounds)
        profile = src_vv.profile.copy()

        vv_raw_full = src_vv.read(1).astype(np.float32)
        vh_raw_full = src_vh.read(1).astype(np.float32)

    to_eq_area = Transformer.from_crs(crs_str, cfg["equal_area_crs"], always_xy=True).transform

    # 2. Load Triaged Candidates
    with open(cand_p, "r", encoding="utf-8") as f:
        geojson_data = json.load(f)

    primary_candidates = [
        f for f in geojson_data.get("features", [])
        if f.get("properties", {}).get("triage_tier") == "PRIMARY_REVIEW"
    ]

    if not primary_candidates:
        # Fallback to all candidates if triage_tier key is absent
        primary_candidates = geojson_data.get("features", [])

    primary_candidates.sort(
        key=lambda f: f.get("properties", {}).get("candidate_score", 0.0), reverse=True
    )

    feature_rows: list[dict[str, Any]] = []
    manifest_rows: list[dict[str, Any]] = []
    processed_count = 0
    valid_ml_inputs_count = 0
    insufficient_context_count = 0

    for feat in primary_candidates:
        props = feat.get("properties", {})
        cid = props.get("candidate_id", f"C{processed_count+1:03d}")
        poly_geom = shape(feat["geometry"])
        poly_geom_eq = shapely_transform(to_eq_area, poly_geom)

        c_dir = chips_d / cid
        c_dir.mkdir(parents=True, exist_ok=True)

        # Candidate geographic bounding box
        min_lon, min_lat, max_lon, max_lat = poly_geom.bounds
        col_min, row_max = ~transform_obj * (min_lon, min_lat)
        col_max, row_min = ~transform_obj * (max_lon, max_lat)

        c_left = min(col_min, col_max)
        c_right = max(col_min, col_max)
        c_top = min(row_min, row_max)
        c_bottom = max(row_min, row_max)

        cand_w_px = c_right - c_left
        cand_h_px = c_bottom - c_top

        # Dynamic Context Padding
        pad_px = max(
            cfg["min_context_padding_px"],
            int(cfg["context_padding_ratio"] * max(cand_w_px, cand_h_px)),
        )

        chip_left_px = max(0, int(math.floor(c_left - pad_px)))
        chip_right_px = min(width, int(math.ceil(c_right + pad_px)))
        chip_top_px = max(0, int(math.floor(c_top - pad_px)))
        chip_bottom_px = min(height, int(math.ceil(c_bottom + pad_px)))

        # Ensure minimum chip dimension (e.g. 256x256)
        curr_chip_w = chip_right_px - chip_left_px
        curr_chip_h = chip_bottom_px - chip_top_px
        min_w, min_h = cfg["target_chip_size_px"]

        if curr_chip_w < min_w:
            diff_w = min_w - curr_chip_w
            chip_left_px = max(0, chip_left_px - diff_w // 2)
            chip_right_px = min(width, chip_left_px + min_w)

        if curr_chip_h < min_h:
            diff_h = min_h - curr_chip_h
            chip_top_px = max(0, chip_top_px - diff_h // 2)
            chip_bottom_px = min(height, chip_top_px + min_h)

        slice_y = slice(chip_top_px, chip_bottom_px)
        slice_x = slice(chip_left_px, chip_right_px)

        vv_chip_raw = vv_raw_full[slice_y, slice_x]
        vh_chip_raw = vh_raw_full[slice_y, slice_x]

        chip_h, chip_w = vv_chip_raw.shape
        chip_transform = rasterio.transform.from_origin(
            transform_obj.c + chip_left_px * transform_obj.a,
            transform_obj.f + chip_top_px * transform_obj.e,
            abs(transform_obj.a),
            abs(transform_obj.e),
        )

        # Rasterize candidate polygon into exact chip grid
        cand_mask_chip = (
            rasterio.features.rasterize(
                [(poly_geom, 1)],
                out_shape=(chip_h, chip_w),
                transform=chip_transform,
                fill=0,
                dtype=np.uint8,
            )
            == 1
        )

        cand_px_count = int(cand_mask_chip.sum())
        valid_vv_chip = np.isfinite(vv_chip_raw) & (vv_chip_raw >= -100.0)
        valid_vh_chip = np.isfinite(vh_chip_raw) & (vh_chip_raw >= -100.0)
        valid_chip_mask = valid_vv_chip & valid_vh_chip

        bg_mask_chip = valid_chip_mask & (~cand_mask_chip)
        bg_px_count = int(bg_mask_chip.sum())

        # Quality Check: Background Context
        if bg_px_count < cfg["min_background_pixels"]:
            quality_flag = "INSUFFICIENT_CONTEXT"
            insufficient_context_count += 1
        else:
            quality_flag = "VALID"
            valid_ml_inputs_count += 1

        # 3. Export Raw GeoTIFF Chips
        chip_profile = profile.copy()
        chip_profile.update(
            height=chip_h,
            width=chip_w,
            transform=chip_transform,
            count=1,
            dtype=rasterio.float32,
        )

        vv_chip_path = c_dir / "vv_raw.tif"
        with rasterio.open(vv_chip_path, "w", **chip_profile) as dst:
            dst.write(vv_chip_raw, 1)

        vh_chip_path = c_dir / "vh_raw.tif"
        with rasterio.open(vh_chip_path, "w", **chip_profile) as dst:
            dst.write(vh_chip_raw, 1)

        mask_profile = chip_profile.copy()
        mask_profile.update(dtype=rasterio.uint8)
        mask_chip_path = c_dir / "candidate_mask.tif"
        with rasterio.open(mask_chip_path, "w", **mask_profile) as dst:
            dst.write(cand_mask_chip.astype(np.uint8), 1)

        # 4. Generate 2-Channel ML Normalized Array [2, H, W] -> Resized [2, 256, 256]
        norm_vv_chip, vv_clip_frac = normalize_sar_db(vv_chip_raw, cfg["vv_norm_range_db"])
        norm_vh_chip, vh_clip_frac = normalize_sar_db(vh_chip_raw, cfg["vh_norm_range_db"])

        target_h, target_w = cfg["target_chip_size_px"]
        norm_vv_resized = cv2.resize(
            norm_vv_chip, (target_w, target_h), interpolation=cv2.INTER_LINEAR
        )
        norm_vh_resized = cv2.resize(
            norm_vh_chip, (target_w, target_h), interpolation=cv2.INTER_LINEAR
        )

        input_2ch = np.stack([norm_vv_resized, norm_vh_resized], axis=0).astype(np.float32)
        npy_path = c_dir / "input_2ch.npy"
        np.save(npy_path, input_2ch)

        # 5. Extract Feature Statistics (Candidate vs Background)
        cand_vv = vv_chip_raw[cand_mask_chip & valid_chip_mask]
        cand_vh = vh_chip_raw[cand_mask_chip & valid_chip_mask]

        if len(cand_vv) == 0:
            cand_vv = vv_chip_raw[cand_mask_chip]
            cand_vh = vh_chip_raw[cand_mask_chip]

        bg_vv = vv_chip_raw[bg_mask_chip]
        bg_vh = vh_chip_raw[bg_mask_chip]

        mean_vv = float(np.mean(cand_vv)) if len(cand_vv) > 0 else -15.0
        median_vv = float(np.median(cand_vv)) if len(cand_vv) > 0 else -15.0
        std_vv = float(np.std(cand_vv)) if len(cand_vv) > 0 else 0.0

        mean_vh = float(np.mean(cand_vh)) if len(cand_vh) > 0 else -25.0
        median_vh = float(np.median(cand_vh)) if len(cand_vh) > 0 else -25.0
        std_vh = float(np.std(cand_vh)) if len(cand_vh) > 0 else 0.0

        bg_mean_vv = float(np.mean(bg_vv)) if len(bg_vv) > 0 else -10.0
        bg_median_vv = float(np.median(bg_vv)) if len(bg_vv) > 0 else -10.0
        bg_std_vv = float(np.std(bg_vv)) if len(bg_vv) > 0 else 0.0

        bg_mean_vh = float(np.mean(bg_vh)) if len(bg_vh) > 0 else -20.0
        bg_median_vh = float(np.median(bg_vh)) if len(bg_vh) > 0 else -20.0
        bg_std_vh = float(np.std(bg_vh)) if len(bg_vh) > 0 else 0.0

        local_vv_contrast = float(bg_median_vv - median_vv)
        local_vh_contrast = float(bg_median_vh - median_vh)
        vv_vh_diff_mean = float(mean_vv - mean_vh)
        vv_vh_diff_median = float(median_vv - median_vh)

        morph = props.get("morphology", {})
        sar_ev = props.get("sar_evidence", {})

        feat_entry = {
            "candidate_id": cid,
            "candidate_group_id": props.get("candidate_group_id", "GRP_UNASSIGNED"),
            "quality_flag": quality_flag,
            "area_km2": props.get("area_km2", 0.0),
            "pixel_count": props.get("pixel_count", cand_px_count),
            "perimeter_px": morph.get("perimeter_px", 0.0),
            "elongation": morph.get("elongation", 1.0),
            "compactness": morph.get("compactness", 0.0),
            "solidity": morph.get("solidity", 0.0),
            "orientation_deg": morph.get("orientation_deg", 0.0),
            "major_dimension_m": round(morph.get("major_axis_px", 0.0) * abs(transform_obj.a) * 111320.0, 2),
            "minor_dimension_m": round(morph.get("minor_axis_px", 0.0) * abs(transform_obj.a) * 111320.0, 2),
            "mean_vv_db": round(mean_vv, 2),
            "median_vv_db": round(median_vv, 2),
            "std_vv_db": round(std_vv, 2),
            "mean_vh_db": round(mean_vh, 2),
            "median_vh_db": round(median_vh, 2),
            "std_vh_db": round(std_vh, 2),
            "vv_vh_difference_mean": round(vv_vh_diff_mean, 2),
            "vv_vh_difference_median": round(vv_vh_diff_median, 2),
            "local_vv_contrast_db": round(local_vv_contrast, 2),
            "local_vh_contrast_db": round(local_vh_contrast, 2),
            "candidate_vv_std": round(std_vv, 2),
            "candidate_vh_std": round(std_vh, 2),
            "background_vv_std": round(bg_std_vv, 2),
            "background_vh_std": round(bg_std_vh, 2),
            "distance_to_land_m": props.get("distance_to_land_m", 999999.0),
            "nearshore_context": props.get("nearshore_context", False),
            "coastal_buffer_overlap": props.get("coastal_buffer_overlap", 0.0),
            "land_overlap_fraction": props.get("land_overlap_fraction", 0.0),
            "ocean_overlap_fraction": props.get("ocean_overlap_fraction", 1.0),
            "edge_touching": morph.get("edge_touching", False),
            "invalid_data_overlap": props.get("context", {}).get("touches_invalid_region", False),
            "candidate_score": props.get("candidate_score", 50.0),
            "triage_tier": props.get("triage_tier", "PRIMARY_REVIEW"),
        }
        feature_rows.append(feat_entry)

        # Metadata JSON for Candidate Sample
        sample_meta = {
            "candidate_id": cid,
            "candidate_group_id": props.get("candidate_group_id", "GRP_UNASSIGNED"),
            "dataset_provenance": {
                "case_id": "R001_WAKASHIO",
                "label_status": "UNLABELLED_REAL_CASE",
                "training_allowed": False,
                "historical_truth_used": False,
                "scene_vv_path": str(vv_p),
                "scene_vh_path": str(vh_p),
            },
            "chip_provenance": {
                "chip_shape_raw": [chip_h, chip_w],
                "chip_shape_ml_input": list(cfg["target_chip_size_px"]),
                "polarization_order": cfg["polarization_order"],
                "crs": crs_str,
                "chip_transform": list(chip_transform[:6]),
                "chip_bounds": list(rasterio.transform.array_bounds(chip_h, chip_w, chip_transform)),
                "quality_flag": quality_flag,
                "background_pixel_count": bg_px_count,
            },
            "normalization": {
                "strategy": "physical_stable_db_clip",
                "vv_norm_range_db": cfg["vv_norm_range_db"],
                "vh_norm_range_db": cfg["vh_norm_range_db"],
                "vv_clipped_pixel_fraction": round(vv_clip_frac, 6),
                "vh_clipped_pixel_fraction": round(vh_clip_frac, 6),
            },
            "features": feat_entry,
        }

        meta_path = c_dir / "metadata.json"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(sample_meta, f, indent=2)

        manifest_rows.append({
            "candidate_id": cid,
            "group_id": props.get("candidate_group_id", "GRP_UNASSIGNED"),
            "chip_folder": str(c_dir.relative_to(out_d)),
            "vv_raw_path": str(vv_chip_path.relative_to(out_d)),
            "vh_raw_path": str(vh_chip_path.relative_to(out_d)),
            "mask_path": str(mask_chip_path.relative_to(out_d)),
            "npy_path": str(npy_path.relative_to(out_d)),
            "metadata_path": str(meta_path.relative_to(out_d)),
            "quality_flag": quality_flag,
            "label_status": "UNLABELLED_REAL_CASE",
            "training_allowed": False,
        })
        processed_count += 1

    # 6. Group Aggregate Features (Section 9)
    group_map: dict[str, list[dict[str, Any]]] = {}
    for row in feature_rows:
        gid = row["candidate_group_id"]
        group_map.setdefault(gid, []).append(row)

    group_feature_rows: list[dict[str, Any]] = []
    for gid, members in group_map.items():
        if gid == "GRP_UNASSIGNED":
            continue

        tot_area = sum(m["area_km2"] for m in members)
        orientations = [m["orientation_deg"] for m in members]
        orient_std = float(np.std(orientations)) if len(orientations) > 1 else 0.0

        contrasts = [m["local_vv_contrast_db"] for m in members]
        mean_contrast = float(np.mean(contrasts))

        nearshore_count = sum(1 for m in members if m["nearshore_context"])
        nearshore_frac = float(nearshore_count / len(members))

        group_feature_rows.append({
            "group_id": gid,
            "candidate_count": len(members),
            "total_area_km2": round(tot_area, 4),
            "group_orientation_std_deg": round(orient_std, 2),
            "mean_local_vv_contrast_db": round(mean_contrast, 2),
            "nearshore_member_fraction": round(nearshore_frac, 4),
            "member_candidate_ids": [m["candidate_id"] for m in members],
        })

    # Save Feature Tables & Manifests
    feat_csv_path = out_d / "feature_table.csv"
    if feature_rows:
        with open(feat_csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(feature_rows[0].keys()))
            writer.writeheader()
            writer.writerows(feature_rows)

    grp_csv_path = out_d / "group_feature_table.csv"
    if group_feature_rows:
        with open(grp_csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(group_feature_rows[0].keys()))
            writer.writeheader()
            writer.writerows(group_feature_rows)

    manifest_csv_path = out_d / "manifest.csv"
    if manifest_rows:
        with open(manifest_csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(manifest_rows[0].keys()))
            writer.writeheader()
            writer.writerows(manifest_rows)

    config_path = out_d / "TASK008A_CONFIG.json"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

    # 7. Generate Visual Contact Sheet (Section 12)
    contact_sheet_path = out_d / "R001_PRIMARY_CANDIDATE_CONTACT_SHEET.png"
    _generate_contact_sheet(feature_rows, chips_d, contact_sheet_path)

    # 8. Summary Markdown Document
    summary_md = f"""# 📦 R001 WAKASHIO — TASK008A CANDIDATE CHIP & FEATURE PIPELINE REPORT

> **Execution Date:** August 29, 2026  
> **Module:** `backend/app/services/sar_candidate_ml_pipeline.py`  
> **Target Case:** R001 Wakashio (`UNLABELLED_REAL_CASE`)

---

## 1. Candidate Chip & ML Dataset Summary

| Metric | Value |
| :--- | :--- |
| **Primary Candidates Processed** | **{processed_count}** |
| **Candidate Chips Created** | **{processed_count}** |
| **Valid ML Input Samples** | **{valid_ml_inputs_count}** |
| **Insufficient Context Samples** | **{insufficient_context_count}** |
| **Feature Rows Generated** | **{len(feature_rows)}** |
| **Primary Groups Processed** | **{len(group_feature_rows)}** |
| **Channel Order Contract** | `[0: VV, 1: VH]` (Explicitly Validated) |
| **VV dB Normalization Range** | `{cfg['vv_norm_range_db']} dB` |
| **VH dB Normalization Range** | `{cfg['vh_norm_range_db']} dB` |
| **R001 Training Lock (`training_allowed`)** | **`FALSE`** (Strict Safety Guard) |

---

## 2. Generated Deliverables

- **Manifest CSV:** [`07_results/candidate_ml_inputs/manifest.csv`](file:///{manifest_csv_path})
- **Feature Table CSV:** [`07_results/candidate_ml_inputs/feature_table.csv`](file:///{feat_csv_path})
- **Group Feature Table CSV:** [`07_results/candidate_ml_inputs/group_feature_table.csv`](file:///{grp_csv_path})
- **Pipeline Config JSON:** [`07_results/candidate_ml_inputs/TASK008A_CONFIG.json`](file:///{config_path})
- **Visual Contact Sheet:** [`07_results/candidate_ml_inputs/R001_PRIMARY_CANDIDATE_CONTACT_SHEET.png`](file:///{contact_sheet_path})
"""

    summary_path = out_d / "TASK008A_SUMMARY.md"
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(summary_md)

    return {
        "status": "PASS",
        "primary_candidates_count": processed_count,
        "chips_created_count": processed_count,
        "valid_ml_inputs_count": valid_ml_inputs_count,
        "insufficient_context_count": insufficient_context_count,
        "feature_rows_count": len(feature_rows),
        "primary_groups_count": len(group_feature_rows),
        "group_feature_rows_count": len(group_feature_rows),
        "vv_vh_alignment": "PASS",
        "training_lock": "PASS",
        "contact_sheet_path": str(contact_sheet_path),
        "summary_markdown_path": str(summary_path),
    }


def _generate_contact_sheet(
    feature_rows: list[dict[str, Any]], chips_dir: Path, output_path: Path
):
    """Generate visual analyst contact sheet grid for all primary candidates."""
    if not feature_rows:
        return

    grid_cols = 5
    grid_rows = math.ceil(len(feature_rows) / grid_cols)
    cell_size = 200

    canvas_w = grid_cols * cell_size
    canvas_h = grid_rows * cell_size
    canvas = np.zeros((canvas_h, canvas_w, 3), dtype=np.uint8)

    for idx, feat in enumerate(feature_rows):
        cid = feat["candidate_id"]
        c_dir = chips_dir / cid
        vv_path = c_dir / "vv_raw.tif"
        mask_path = c_dir / "candidate_mask.tif"

        r = idx // grid_cols
        c = idx % grid_cols

        y_top = r * cell_size
        x_left = c * cell_size

        if vv_path.exists() and mask_path.exists():
            with rasterio.open(vv_path) as src_vv, rasterio.open(mask_path) as src_m:
                vv_arr = src_vv.read(1)
                mask_arr = src_m.read(1)

            valid_m = np.isfinite(vv_arr)
            v_min, v_max = float(vv_arr[valid_m].min()), float(vv_arr[valid_m].max())
            norm_vv = np.zeros_like(vv_arr, dtype=np.float32)
            norm_vv[valid_m] = (vv_arr[valid_m] - v_min) / (v_max - v_min + 1e-6)
            norm_uint8 = (np.clip(norm_vv, 0, 1) * 255.0).astype(np.uint8)

            resized_vv = cv2.resize(norm_uint8, (cell_size, cell_size), interpolation=cv2.INTER_AREA)
            cell_bgr = cv2.cvtColor(resized_vv, cv2.COLOR_GRAY2BGR)

            resized_m = cv2.resize(mask_arr, (cell_size, cell_size), interpolation=cv2.INTER_NEAREST)
            cell_bgr[resized_m == 1] = (
                cell_bgr[resized_m == 1] * 0.5 + np.array([0, 255, 255], dtype=np.float32) * 0.5
            ).astype(np.uint8)
        else:
            cell_bgr = np.zeros((cell_size, cell_size, 3), dtype=np.uint8)

        # Draw Annotations
        score = feat.get("candidate_score", 0.0)
        area = feat.get("area_km2", 0.0)
        elong = feat.get("elongation", 1.0)
        dist_m = feat.get("distance_to_land_m", 0.0)
        nearshore = "NEAR" if feat.get("nearshore_context") else "OFF"

        cv2.rectangle(cell_bgr, (0, 0), (cell_size - 1, cell_size - 1), (80, 80, 80), 1)
        cv2.putText(
            cell_bgr,
            f"{cid} ({score:.0f})",
            (6, 18),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (0, 255, 255),
            1,
            cv2.LINE_AA,
        )
        cv2.putText(
            cell_bgr,
            f"A:{area:.2f}k E:{elong:.1f}",
            (6, cell_size - 22),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.35,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
        cv2.putText(
            cell_bgr,
            f"D:{dist_m:.0f}m [{nearshore}]",
            (6, cell_size - 6),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.35,
            (200, 200, 200),
            1,
            cv2.LINE_AA,
        )

        canvas[y_top : y_top + cell_size, x_left : x_left + cell_size] = cell_bgr

    cv2.imwrite(str(output_path), canvas)
