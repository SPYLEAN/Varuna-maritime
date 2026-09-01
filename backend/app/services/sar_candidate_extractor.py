from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import rasterio
from pyproj import Transformer
from shapely.geometry import Polygon, mapping
from shapely.ops import transform as shapely_transform

DEFAULT_CONFIG = {
    "local_window_sizes_px": [51, 151],
    "min_contrast_db": 3.0,
    "vh_min_contrast_db": 2.0,
    "min_component_size_pixels": 50,
    "max_scene_candidate_fraction": 0.15,
    "valid_db_min": -100.0,
    "valid_db_max": 30.0,
    "equal_area_crs": "ESRI:54034",
}


def _file_sha256(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def _validate_input_rasters(
    vv_path: Path, vh_path: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not vv_path.exists():
        raise FileNotFoundError(f"VV SAR raster does not exist: {vv_path}")
    if not vh_path.exists():
        raise FileNotFoundError(f"VH SAR raster does not exist: {vh_path}")

    with rasterio.open(vv_path) as vv_src, rasterio.open(vh_path) as vh_src:
        if vv_src.count < 1 or vh_src.count < 1:
            raise ValueError(f"Raster band count must be >= 1. VV={vv_src.count}, VH={vh_src.count}")

        vv_dtype = str(vv_src.dtypes[0]).lower()
        vh_dtype = str(vh_src.dtypes[0]).lower()
        if "float" not in vv_dtype or "float" not in vh_dtype:
            raise ValueError(f"SAR rasters must be floating-point. VV={vv_dtype}, VH={vh_dtype}")

        if vv_src.shape != vh_src.shape:
            raise ValueError(f"VV shape {vv_src.shape} does not match VH shape {vh_src.shape}")
        if str(vv_src.crs) != str(vh_src.crs):
            raise ValueError(f"VV CRS {vv_src.crs!r} does not match VH CRS {vh_src.crs!r}")
        if not np.allclose(vv_src.transform[:6], vh_src.transform[:6], rtol=0.0, atol=1e-9):
            raise ValueError("VV affine transform does not match VH transform")
        if not np.allclose(vv_src.bounds, vh_src.bounds, rtol=0.0, atol=1e-6):
            raise ValueError("VV bounds do not match VH bounds")

        vv_meta = {
            "shape": (vv_src.height, vv_src.width),
            "crs": str(vv_src.crs),
            "transform": tuple(float(v) for v in vv_src.transform[:6]),
            "bounds": tuple(float(v) for v in vv_src.bounds),
            "driver": vv_src.driver,
        }
        vh_meta = {
            "shape": (vh_src.height, vh_src.width),
            "crs": str(vh_src.crs),
            "transform": tuple(float(v) for v in vh_src.transform[:6]),
            "bounds": tuple(float(v) for v in vh_src.bounds),
            "driver": vh_src.driver,
        }

    return vv_meta, vh_meta


def _calculate_equal_area_km2(geom: Polygon, source_crs: str, target_crs: str = "ESRI:54034") -> float:
    try:
        transformer = Transformer.from_crs(source_crs, target_crs, always_xy=True)
        reprojected = shapely_transform(transformer.transform, geom)
        return float(reprojected.area / 1e6)
    except Exception:
        return float(geom.area * 111.32 * 111.32 * math.cos(math.radians(-20.0)))


def extract_sar_candidates(
    vv_path: str | Path,
    vh_path: str | Path,
    ocean_mask_path: str | Path | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Extract SAR dark-spot candidates from calibrated VV/VH Sigma0 dB rasters."""
    vv_p = Path(vv_path)
    vh_p = Path(vh_path)
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    warnings: list[str] = []

    # 1. Input Contract Validation
    vv_meta, vh_meta = _validate_input_rasters(vv_p, vh_p)
    height, width = vv_meta["shape"]
    total_pixels = height * width

    # Calculate SHA256 hashes via chunking
    vv_sha256 = _file_sha256(vv_p)
    vh_sha256 = _file_sha256(vh_p)

    # 2. Read SAR rasters
    with rasterio.open(vv_p) as src_vv, rasterio.open(vh_p) as src_vh:
        vv_arr = src_vv.read(1).astype(np.float32)
        vh_arr = src_vh.read(1).astype(np.float32)
        transform_obj = src_vv.transform

    # 3. Invalid Value & Nodata Masking
    valid_vv = np.isfinite(vv_arr) & (vv_arr >= cfg["valid_db_min"]) & (vv_arr <= cfg["valid_db_max"])
    valid_vh = np.isfinite(vh_arr) & (vh_arr >= cfg["valid_db_min"]) & (vh_arr <= cfg["valid_db_max"])
    usable_mask = valid_vv & valid_vh

    # Land/Ocean Mask Handling
    land_mask_status = "unavailable"
    if ocean_mask_path is not None:
        ocean_p = Path(ocean_mask_path)
        if ocean_p.exists():
            with rasterio.open(ocean_p) as ocean_src:
                ocean_mask = ocean_src.read(1)
                usable_mask = usable_mask & (ocean_mask > 0)
                land_mask_status = "applied"
        else:
            warnings.append(f"Ocean mask path specified but not found: {ocean_mask_path}")

    valid_pixel_count = int(usable_mask.sum())
    valid_pixel_fraction = float(valid_pixel_count / total_pixels)

    if valid_pixel_count == 0:
        warnings.append("No valid usable pixels found in input rasters")
        return {
            "status": "INSUFFICIENT_DATA",
            "input_provenance": {
                "vv_path": str(vv_p),
                "vh_path": str(vh_p),
                "ocean_mask_path": str(ocean_mask_path) if ocean_mask_path else None,
                "vv_sha256": vv_sha256,
                "vh_sha256": vh_sha256,
                "shape": (height, width),
                "crs": vv_meta["crs"],
                "transform": list(vv_meta["transform"]),
                "bounds": list(vv_meta["bounds"]),
            },
            "processing_config": cfg,
            "candidate_count": 0,
            "candidates": [],
            "scene_statistics": {
                "total_raster_pixels": total_pixels,
                "valid_ocean_pixels": 0,
                "valid_pixel_fraction": 0.0,
                "invalid_pixel_count": total_pixels,
                "candidate_pixel_count": 0,
                "candidate_pixel_fraction": 0.0,
                "extraction_saturated": False,
                "land_mask_status": land_mask_status,
            },
            "warnings": warnings,
        }

    # 4. Fast Multi-Scale Local Background Dark-Spot Anomaly Extraction
    scale_factor = 4 if max(height, width) > 2000 else 1
    ds_h, ds_w = height // scale_factor, width // scale_factor

    valid_samples_vv = vv_arr[usable_mask]
    global_vv_med = float(np.median(valid_samples_vv[::100])) if len(valid_samples_vv) > 0 else -12.0

    valid_samples_vh = vh_arr[usable_mask]
    global_vh_med = float(np.median(valid_samples_vh[::100])) if len(valid_samples_vh) > 0 else -18.0

    vv_filled = np.where(usable_mask, vv_arr, global_vv_med).astype(np.float32)
    vh_filled = np.where(usable_mask, vh_arr, global_vh_med).astype(np.float32)

    vv_ds = cv2.resize(vv_filled, (ds_w, ds_h), interpolation=cv2.INTER_AREA)
    vh_ds = cv2.resize(vh_filled, (ds_w, ds_h), interpolation=cv2.INTER_AREA)

    combined_seed_mask = np.zeros((height, width), dtype=bool)

    for w_size in cfg["local_window_sizes_px"]:
        w_size_ds = max(3, int(w_size / scale_factor))
        if w_size_ds % 2 == 0:
            w_size_ds += 1

        bg_vv_ds = cv2.boxFilter(
            vv_ds, ddepth=-1, ksize=(w_size_ds, w_size_ds), borderType=cv2.BORDER_REPLICATE
        )
        bg_vv = cv2.resize(bg_vv_ds, (width, height), interpolation=cv2.INTER_LINEAR)

        local_contrast = bg_vv - vv_filled
        seed_scale = (local_contrast >= cfg["min_contrast_db"]) & usable_mask
        combined_seed_mask = combined_seed_mask | seed_scale

    # 5. Saturation Safeguard Audit
    candidate_pixels = int(combined_seed_mask.sum())
    candidate_fraction = float(candidate_pixels / valid_pixel_count)

    is_saturated = candidate_fraction > cfg["max_scene_candidate_fraction"]
    if is_saturated:
        warnings.append(
            f"DARK_SPOT_EXTRACTION_SATURATED: Candidate fraction {candidate_fraction:.4f} "
            f"exceeds safety threshold {cfg['max_scene_candidate_fraction']:.4f}"
        )
        return {
            "status": "INSUFFICIENT_DATA",
            "input_provenance": {
                "vv_path": str(vv_p),
                "vh_path": str(vh_p),
                "ocean_mask_path": str(ocean_mask_path) if ocean_mask_path else None,
                "vv_sha256": vv_sha256,
                "vh_sha256": vh_sha256,
                "shape": (height, width),
                "crs": vv_meta["crs"],
                "transform": list(vv_meta["transform"]),
                "bounds": list(vv_meta["bounds"]),
            },
            "processing_config": cfg,
            "candidate_count": 0,
            "candidates": [],
            "scene_statistics": {
                "total_raster_pixels": total_pixels,
                "valid_ocean_pixels": valid_pixel_count,
                "valid_pixel_fraction": valid_pixel_fraction,
                "invalid_pixel_count": total_pixels - valid_pixel_count,
                "candidate_pixel_count": candidate_pixels,
                "candidate_pixel_fraction": candidate_fraction,
                "extraction_saturated": True,
                "land_mask_status": land_mask_status,
            },
            "warnings": warnings,
        }

    # 6. Morphological Cleanup (Speckle removal)
    binary_uint8 = combined_seed_mask.astype(np.uint8) * 255
    kernel_3x3 = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    cleaned_mask = cv2.morphologyEx(binary_uint8, cv2.MORPH_OPEN, kernel_3x3)

    # 7. Connected Component & Feature Extraction
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(cleaned_mask)

    bg_vv_global_ds = cv2.boxFilter(
        vv_ds, ddepth=-1, ksize=(37, 37), borderType=cv2.BORDER_REPLICATE
    )
    bg_vv_global = cv2.resize(bg_vv_global_ds, (width, height), interpolation=cv2.INTER_LINEAR)

    bg_vh_global_ds = cv2.boxFilter(
        vh_ds, ddepth=-1, ksize=(37, 37), borderType=cv2.BORDER_REPLICATE
    )
    bg_vh_global = cv2.resize(bg_vh_global_ds, (width, height), interpolation=cv2.INTER_LINEAR)

    raw_candidates = []

    for i in range(1, num_labels):
        px_count = int(stats[i, cv2.CC_STAT_AREA])
        if px_count < cfg["min_component_size_pixels"]:
            continue

        cy_px, cx_px = centroids[i]

        left, top, w_comp, h_comp = (
            int(stats[i, cv2.CC_STAT_LEFT]),
            int(stats[i, cv2.CC_STAT_TOP]),
            int(stats[i, cv2.CC_STAT_WIDTH]),
            int(stats[i, cv2.CC_STAT_HEIGHT]),
        )
        edge_touching = (
            left == 0 or top == 0 or (left + w_comp) >= width or (top + h_comp) >= height
        )

        slice_y = slice(top, top + h_comp)
        slice_x = slice(left, left + w_comp)
        sub_labels = labels[slice_y, slice_x]
        comp_mask_sub = sub_labels == i

        comp_uint8 = comp_mask_sub.astype(np.uint8) * 255
        contours, _ = cv2.findContours(comp_uint8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            continue

        main_contour = max(contours, key=cv2.contourArea)
        perimeter_px = float(cv2.arcLength(main_contour, True))

        if len(main_contour) >= 5:
            (center_x, center_y), (rect_w, rect_h), angle = cv2.minAreaRect(main_contour)
            major_px = max(rect_w, rect_h)
            minor_px = min(rect_w, rect_h)
            elongation = float(major_px / max(minor_px, 1.0))
        else:
            major_px = float(max(w_comp, h_comp))
            minor_px = float(min(w_comp, h_comp))
            angle = 0.0
            elongation = float(major_px / max(minor_px, 1.0))

        compactness = float((4.0 * math.pi * px_count) / (perimeter_px**2 + 1e-6))
        hull = cv2.convexHull(main_contour)
        hull_area = float(cv2.contourArea(hull))
        solidity = float(px_count / max(hull_area, 1.0))

        centroid_lon, centroid_lat = transform_obj * (cx_px, cy_px)

        poly_coords = []
        for pt in main_contour[:, 0, :]:
            px_x, px_y = float(pt[0] + left), float(pt[1] + top)
            lon, lat = transform_obj * (px_x, px_y)
            poly_coords.append([float(lon), float(lat)])

        if len(poly_coords) < 3:
            continue
        if poly_coords[0] != poly_coords[-1]:
            poly_coords.append(poly_coords[0])

        polygon_geom = Polygon(poly_coords)
        if not polygon_geom.is_valid:
            polygon_geom = polygon_geom.buffer(0)

        area_km2 = _calculate_equal_area_km2(polygon_geom, vv_meta["crs"])
        min_lon, min_lat, max_lon, max_lat = polygon_geom.bounds

        # Bounding box sub-slice evidence extraction (Ultra fast)
        sub_vv = vv_arr[slice_y, slice_x][comp_mask_sub]
        sub_vh = vh_arr[slice_y, slice_x][comp_mask_sub]
        sub_bg_vv = bg_vv_global[slice_y, slice_x][comp_mask_sub]
        sub_bg_vh = bg_vh_global[slice_y, slice_x][comp_mask_sub]

        mean_vv = float(np.mean(sub_vv))
        median_vv = float(np.median(sub_vv))
        mean_vh = float(np.mean(sub_vh))
        median_vh = float(np.median(sub_vh))

        local_vv_contrast = float(np.median(sub_bg_vv - sub_vv))
        local_vh_contrast = float(np.median(sub_bg_vh - sub_vh))
        vv_vh_diff = float(np.mean(sub_vv - sub_vh))
        vv_std = float(np.std(sub_vv))

        sub_usable = usable_mask[slice_y, slice_x][comp_mask_sub]
        cand_valid_frac = float(sub_usable.sum() / px_count)
        touches_invalid = bool(cand_valid_frac < 1.0)

        # Candidate Priority Scoring (Heuristic Prioritization Only)
        c_score = min(max(local_vv_contrast * 8.0, 0.0), 30.0)
        e_score = min(max((elongation - 1.0) * 5.0, 0.0), 25.0)

        if 0.05 <= area_km2 <= 50.0:
            a_score = min(area_km2 * 2.0, 20.0)
        else:
            a_score = 5.0

        coh_score = min(solidity * 15.0, 15.0)
        edge_pen = -30.0 if edge_touching else 0.0
        size_pen = -30.0 if (area_km2 > 200.0 or px_count < 40) else 0.0
        comp_pen = -15.0 if compactness > 0.8 else 0.0

        total_score = max(
            0.0,
            min(
                100.0,
                c_score + e_score + a_score + coh_score + edge_pen + size_pen + comp_pen,
            ),
        )

        raw_candidates.append(
            {
                "pixel_count": px_count,
                "area_km2": round(area_km2, 6),
                "centroid_lat": round(centroid_lat, 6),
                "centroid_lon": round(centroid_lon, 6),
                "bounds": [round(v, 6) for v in [min_lon, min_lat, max_lon, max_lat]],
                "polygon": mapping(polygon_geom),
                "morphology": {
                    "perimeter_px": round(perimeter_px, 2),
                    "elongation": round(elongation, 4),
                    "compactness": round(compactness, 4),
                    "solidity": round(solidity, 4),
                    "major_axis_px": round(major_px, 2),
                    "minor_axis_px": round(minor_px, 2),
                    "orientation_deg": round(angle, 2),
                    "edge_touching": edge_touching,
                },
                "sar_evidence": {
                    "mean_vv_db": round(mean_vv, 2),
                    "median_vv_db": round(median_vv, 2),
                    "mean_vh_db": round(mean_vh, 2),
                    "median_vh_db": round(median_vh, 2),
                    "local_vv_contrast_db": round(local_vv_contrast, 2),
                    "local_vh_contrast_db": round(local_vh_contrast, 2),
                    "vv_vh_diff_mean_db": round(vv_vh_diff, 2),
                    "vv_std_db": round(vv_std, 2),
                },
                "context": {
                    "valid_pixel_fraction": round(cand_valid_frac, 4),
                    "land_mask_status": land_mask_status,
                    "touches_invalid_region": touches_invalid,
                },
                "candidate_score": round(total_score, 2),
                "score_breakdown": {
                    "contrast_score": round(c_score, 2),
                    "elongation_score": round(e_score, 2),
                    "area_score": round(a_score, 2),
                    "coherence_score": round(coh_score, 2),
                    "edge_penalty": round(edge_pen, 2),
                    "size_penalty": round(size_pen, 2),
                    "compactness_penalty": round(comp_pen, 2),
                },
            }
        )

    # Sort candidates by score descending and assign IDs C001, C002...
    raw_candidates.sort(key=lambda c: c["candidate_score"], reverse=True)
    for idx, cand in enumerate(raw_candidates, 1):
        cand["candidate_id"] = f"C{idx:03d}"

    return {
        "status": "PASS",
        "input_provenance": {
            "vv_path": str(vv_p),
            "vh_path": str(vh_p),
            "ocean_mask_path": str(ocean_mask_path) if ocean_mask_path else None,
            "vv_sha256": vv_sha256,
            "vh_sha256": vh_sha256,
            "shape": (height, width),
            "crs": vv_meta["crs"],
            "transform": list(vv_meta["transform"]),
            "bounds": list(vv_meta["bounds"]),
        },
        "processing_config": cfg,
        "candidate_count": len(raw_candidates),
        "candidates": raw_candidates,
        "scene_statistics": {
            "total_raster_pixels": total_pixels,
            "valid_ocean_pixels": valid_pixel_count,
            "valid_pixel_fraction": round(valid_pixel_fraction, 6),
            "invalid_pixel_count": total_pixels - valid_pixel_count,
            "candidate_pixel_count": candidate_pixels,
            "candidate_pixel_fraction": round(candidate_fraction, 6),
            "extraction_saturated": False,
            "land_mask_status": land_mask_status,
        },
        "warnings": warnings,
    }
