from __future__ import annotations
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import cv2
import numpy as np
import rasterio
from rasterio.crs import CRS
import pyproj
from shapely.geometry import Polygon, mapping
from shapely.ops import transform


def analyze_spill_geometry(
    binary_mask_path: str | Path,
    source_image_path: str | Path,
    overlay_out_path: str | Path,
    min_component_size_pixels: int = 1,
) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]], str]:
    """
    Computes morphological and geospatial spill geometry characterisation from a binary oil mask.
    Returns:
        (results_dict, geojson_dict_or_none, overlay_out_path_str)
    """
    bin_p = Path(binary_mask_path)
    src_p = Path(source_image_path)
    over_p = Path(overlay_out_path)

    # 1. Read binary mask
    mask = cv2.imread(str(bin_p), cv2.IMREAD_GRAYSCALE)
    if mask is None:
        raise ValueError(f"Unable to read binary mask image from: {bin_p}")

    h, w = mask.shape
    total_pixels = h * w
    bin_mask = (mask >= 128).astype(np.uint8) * 255
    total_oil_pixels = int((bin_mask > 0).sum())

    # Read base source image for visualization overlay
    sar_raw = cv2.imread(str(src_p), cv2.IMREAD_GRAYSCALE)
    if sar_raw is not None and sar_raw.shape == (h, w):
        overlay_img = cv2.cvtColor(sar_raw, cv2.COLOR_GRAY2BGR)
    else:
        overlay_img = cv2.cvtColor(bin_mask, cv2.COLOR_GRAY2BGR)

    # 2. Connected Component Labeling & Contours
    num_labels, labels, cc_stats, cc_centroids = cv2.connectedComponentsWithStats(bin_mask)
    
    components: List[Dict[str, Any]] = []
    valid_contours: List[np.ndarray] = []
    
    comp_counter = 0

    for label_idx in range(1, num_labels):
        area_px = int(cc_stats[label_idx, cv2.CC_STAT_AREA])

        if area_px < min_component_size_pixels:
            continue

        comp_counter += 1

        # Extract contour matching this component
        comp_mask = (labels == label_idx).astype(np.uint8) * 255
        cnts, _ = cv2.findContours(comp_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        
        if cnts:
            cnt = max(cnts, key=cv2.contourArea)
        else:
            cnt = np.array([[[cc_stats[label_idx, cv2.CC_STAT_LEFT], cc_stats[label_idx, cv2.CC_STAT_TOP]]]])

        valid_contours.append(cnt)
        perimeter = float(cv2.arcLength(cnt, True))
        
        cx = float(cc_centroids[label_idx][0])
        cy = float(cc_centroids[label_idx][1])

        bx = int(cc_stats[label_idx, cv2.CC_STAT_LEFT])
        by = int(cc_stats[label_idx, cv2.CC_STAT_TOP])
        bw = int(cc_stats[label_idx, cv2.CC_STAT_WIDTH])
        bh = int(cc_stats[label_idx, cv2.CC_STAT_HEIGHT])
        bbox = [bx, by, bw, bh]

        # Minimum bounding rotated rectangle for major/minor axes and horizontal orientation angle
        if len(cnt) >= 3:
            try:
                rect = cv2.minAreaRect(cnt)
                (_, _), (rw, rh), rangle = rect
                if rw >= rh:
                    major_axis = float(rw)
                    minor_axis = float(rh)
                    orient = float(rangle) % 180.0
                else:
                    major_axis = float(rh)
                    minor_axis = float(rw)
                    orient = float(rangle + 90.0) % 180.0
                    
                orientation_angle = float(orient)
            except Exception:
                major_axis = float(max(bw, bh))
                minor_axis = float(min(bw, bh))
                orientation_angle = 0.0 if bw >= bh else 90.0
        else:
            major_axis = float(max(bw, bh))
            minor_axis = float(min(bw, bh))
            orientation_angle = 0.0 if bw >= bh else 90.0

        elongation_ratio = float(major_axis / max(minor_axis, 1e-6))
        
        if perimeter > 0:
            compactness = float((4.0 * math.pi * area_px) / (perimeter ** 2))
        else:
            compactness = 1.0

        equivalent_diameter = float(2.0 * math.sqrt(area_px / math.pi))

        # Store component metrics
        comp_info = {
            "component_id": f"comp_{comp_counter}",
            "pixel_area": area_px,
            "perimeter": round(perimeter, 2),
            "centroid_pixel": [round(cx, 2), round(cy, 2)],
            "bbox_pixel": bbox,
            "major_axis_length_px": round(major_axis, 2),
            "minor_axis_length_px": round(minor_axis, 2),
            "orientation_angle_deg": round(orientation_angle, 2),
            "elongation_ratio": round(elongation_ratio, 4),
            "compactness": round(compactness, 4),
            "equivalent_diameter_px": round(equivalent_diameter, 2),
        }
        components.append(comp_info)

        # Draw contour & label on overlay
        cv2.drawContours(overlay_img, [cnt], -1, (0, 255, 0), 2)
        cv2.circle(overlay_img, (int(cx), int(cy)), 4, (0, 0, 255), -1)
        cv2.putText(
            overlay_img,
            f"C{comp_counter}",
            (int(cx) + 5, int(cy) - 5),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )

    # 3. Save Overlay PNG
    over_p.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(over_p), overlay_img)

    # 4. Scene-Level Metrics
    num_components = len(components)
    oil_fraction = float(total_oil_pixels / total_pixels)

    if total_oil_pixels > 0 and num_components > 0:
        largest_comp_px = max(c["pixel_area"] for c in components)
        largest_comp_fraction = round(float(largest_comp_px / total_oil_pixels), 6)
        fragmentation_index = round(float(num_components / total_oil_pixels), 6)
        components_per_10k_oil_px = round(float((num_components * 10000.0) / total_oil_pixels), 4)
        
        # Scene-level weighted centroid
        y_indices, x_indices = np.where(bin_mask > 0)
        if len(x_indices) > 0:
            scene_cx = round(float(x_indices.mean()), 2)
            scene_cy = round(float(y_indices.mean()), 2)
        else:
            scene_cx = None
            scene_cy = None
    else:
        largest_comp_px = 0
        largest_comp_fraction = None
        fragmentation_index = None
        components_per_10k_oil_px = None
        scene_cx = None
        scene_cy = None

    # 5. Georeferenced Mode & Area Strategy
    georeferenced = False
    source_crs_str = None
    analysis_crs_str = None
    area_calc_method = None
    total_area_m2 = None
    total_area_km2 = None
    geo_centroid = None
    geojson_dict = None

    try:
        with rasterio.open(src_p) as raster_src:
            if raster_src.crs is not None:
                georeferenced = True
                source_crs_str = str(raster_src.crs)

                # Transform scene centroid to spatial coordinates
                if scene_cx is not None and scene_cy is not None:
                    world_x, world_y = raster_src.xy(scene_cy, scene_cx)
                    
                    # Convert to WGS84 (lat, lon) if projected
                    if raster_src.crs.is_projected:
                        transformer_wgs84 = pyproj.Transformer.from_crs(raster_src.crs, "EPSG:4326", always_xy=True)
                        lon_val, lat_val = transformer_wgs84.transform(world_x, world_y)
                        geo_centroid = [round(float(lat_val), 6), round(float(lon_val), 6)]
                    else:
                        geo_centroid = [round(float(world_y), 6), round(float(world_x), 6)]

                # Determine Scientifically Sound Area Calculation Strategy
                # Web Mercator (EPSG:3857) has severe latitude scale distortion and cannot be used directly for physical m2!
                is_web_mercator = "3857" in source_crs_str or "Mercator" in source_crs_str
                is_equal_area_or_utm = ("UTM" in source_crs_str or "Equal Area" in source_crs_str or "54034" in source_crs_str or "6933" in source_crs_str) and not is_web_mercator

                if raster_src.crs.is_projected and is_equal_area_or_utm:
                    analysis_crs_str = source_crs_str
                    calc_m2 = 0.0
                    for cnt in valid_contours:
                        pts = cnt[:, 0, :]
                        if len(pts) >= 3:
                            world_pts = [raster_src.xy(r, c) for c, r in pts]
                            poly_world = Polygon(world_pts)
                            if poly_world.is_valid:
                                calc_m2 += poly_world.area
                    total_area_m2 = round(calc_m2, 2)
                    total_area_km2 = round(calc_m2 / 1_000_000.0, 6)
                    area_calc_method = f"Native low-distortion projected CRS ({source_crs_str})"
                else:
                    # Web Mercator or Geographic CRS (EPSG:4326) -> Reproject polygons to World Equal-Area Cylindrical (ESRI:54034)
                    analysis_crs_str = "ESRI:54034"
                    transformer_equal = pyproj.Transformer.from_crs(raster_src.crs, "ESRI:54034", always_xy=True)
                    calc_m2 = 0.0
                    for cnt in valid_contours:
                        pts = cnt[:, 0, :]
                        if len(pts) >= 3:
                            world_pts = [raster_src.xy(r, c) for c, r in pts]
                            poly_geo = Polygon(world_pts)
                            if poly_geo.is_valid:
                                poly_equal = transform(transformer_equal.transform, poly_geo)
                                calc_m2 += poly_equal.area
                    total_area_m2 = round(calc_m2, 2)
                    total_area_km2 = round(calc_m2 / 1_000_000.0, 6)
                    area_calc_method = "World Equal-Area Cylindrical Projection (ESRI:54034)"

                # Build GeoJSON
                features = []
                transformer_wgs84 = pyproj.Transformer.from_crs(raster_src.crs, "EPSG:4326", always_xy=True) if raster_src.crs.is_projected else None

                for comp, cnt in zip(components, valid_contours):
                    pts = cnt[:, 0, :]
                    if len(pts) >= 3:
                        world_pts = [raster_src.xy(r, c) for c, r in pts]
                        poly_world = Polygon(world_pts)
                        if poly_world.is_valid:
                            if transformer_wgs84:
                                poly_wgs84 = transform(transformer_wgs84.transform, poly_world)
                            else:
                                poly_wgs84 = poly_world

                            feat = {
                                "type": "Feature",
                                "geometry": mapping(poly_wgs84),
                                "properties": comp,
                            }
                            features.append(feat)

                geojson_dict = {
                    "type": "FeatureCollection",
                    "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
                    "features": features,
                }
    except Exception:
        # File is not a valid GeoTIFF or rasterio unable to read spatial CRS -> default to pixel-space mode
        georeferenced = False

    # Structure final result dictionary
    results_summary = {
        "georeferenced": georeferenced,
        "source_crs": source_crs_str,
        "analysis_crs": analysis_crs_str,
        "area_calculation_method": area_calc_method,
        "total_area_m2": total_area_m2 if total_oil_pixels > 0 else (0.0 if georeferenced else None),
        "total_area_km2": total_area_km2 if total_oil_pixels > 0 else (0.0 if georeferenced else None),
        "geographic_centroid": geo_centroid,
        "scene_level_statistics": {
            "total_oil_pixels": total_oil_pixels,
            "total_oil_fraction": round(oil_fraction, 6),
            "num_components": num_components,
            "largest_component_pixels": largest_comp_px,
            "largest_component_fraction": largest_comp_fraction,
            "fragmentation_index_per_pixel": fragmentation_index,
            "components_per_10000_oil_pixels": components_per_10k_oil_px,
            "scene_centroid_pixel": [scene_cx, scene_cy] if scene_cx is not None and scene_cy is not None else None,
            "min_component_size_pixels": min_component_size_pixels,
            "image_shape": [h, w],
        },
        "components": components,
        "contour_overlay_path": str(over_p),
        "has_geojson": geojson_dict is not None,
    }

    return results_summary, geojson_dict, str(over_p)
