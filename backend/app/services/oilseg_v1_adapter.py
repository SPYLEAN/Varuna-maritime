"""OilSeg V1 Model Adapter Service.

Executes dual-polarization Sentinel-1 SAR oil segmentation using the canonical
OilSeg V1 2-channel SmallUNet model.

Conforms strictly to:
- RULE 6 (Model Adapter)
- RULE 7 (Evidence Gate compatibility)
- Radiometric truthfulness and source provenance contracts
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.features import shapes
import pyproj
from pyproj import Geod
from pydantic import BaseModel, Field
from shapely.geometry import shape, mapping, Polygon

from ml.src.oiltrace_ml.checkpoint import load_model_from_checkpoint
from ml.src.oiltrace_ml.infer import run_windowed_inference
from ml.src.oiltrace_ml.preprocessing import SARPreprocessingConfig

logger = logging.getLogger("varuna.services.oilseg_v1_adapter")

DEFAULT_V1_CHECKPOINT = Path("models/oil_detection/varuna_oilseg_v1_smallunet.pt")


class OilSegV1PolygonProperties(BaseModel):
    id: str
    area_m2: float
    area_km2: float
    perimeter_m: float
    mean_oil_evidence_score: float
    max_oil_evidence_score: float
    solidity: float
    elongation: float
    centroid_lon: float
    centroid_lat: float


class OilSegV1Statistics(BaseModel):
    total_pixels: int
    oil_pixels: int
    oil_fraction: float
    total_oil_area_km2: float
    mean_oil_evidence_score: float
    max_oil_evidence_score: float
    threshold: float
    polygon_count: int


class OilSegV1Result(BaseModel):
    status: str = Field(..., description="SUCCESS, MODEL_UNAVAILABLE, or VALIDATION_ERROR")
    model_version: Optional[str] = None
    checkpoint_sha256: Optional[str] = None
    inference_timestamp: str
    evidence_raster_path: Optional[str] = None
    binary_mask_path: Optional[str] = None
    geojson_polygons: Optional[Dict[str, Any]] = None
    statistics: Optional[OilSegV1Statistics] = None
    input_provenance: Dict[str, Any] = Field(default_factory=dict)
    reason: Optional[str] = None


def compute_file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def compute_geodetic_polygon_metrics(poly: Polygon, crs_str: str) -> Tuple[float, float, Tuple[float, float]]:
    """Compute ellipsoidal geodesic area (m^2), perimeter (m), and centroid (lon, lat)."""
    geod = Geod(ellps="WGS84")
    # If in EPSG:4326, use coordinates directly
    if "4326" in crs_str.upper() or "WGS 84" in crs_str.upper() or "CRS84" in crs_str.upper():
        lon, lat = poly.exterior.coords.xy
        area_m2, perim_m = geod.polygon_area_perimeter(lon, lat)
        centroid = (float(poly.centroid.x), float(poly.centroid.y))
        return abs(float(area_m2)), abs(float(perim_m)), centroid
    else:
        # Reproject to EPSG:4326 for accurate geodesic metrics
        transformer = pyproj.Transformer.from_crs(crs_str, "EPSG:4326", always_xy=True)
        coords = [transformer.transform(x, y) for x, y in poly.exterior.coords]
        lon, lat = zip(*coords)
        area_m2, perim_m = geod.polygon_area_perimeter(lon, lat)
        cx, cy = transformer.transform(poly.centroid.x, poly.centroid.y)
        return abs(float(area_m2)), abs(float(perim_m)), (float(cx), float(cy))


def calculate_morphology(contour_points: np.ndarray) -> Tuple[float, float]:
    """Calculate solidity and elongation for a contour."""
    if len(contour_points) < 5:
        return 1.0, 1.0
    area = cv2.contourArea(contour_points)
    hull = cv2.convexHull(contour_points)
    hull_area = cv2.contourArea(hull)
    solidity = float(area / (hull_area + 1e-6))
    solidity = min(1.0, max(0.0, solidity))

    ellipse = cv2.fitEllipse(contour_points)
    (_, (minor_axis, major_axis), _) = ellipse
    elongation = float(major_axis / (minor_axis + 1e-6))
    return solidity, elongation


def validate_sar_inputs(
    vv_path: Path,
    vh_path: Path,
) -> Tuple[Dict[str, Any], rasterio.io.DatasetReader, rasterio.io.DatasetReader]:
    """Validate spatial, dimensional, and radiometric contracts of dual-pol GeoTIFFs."""
    if not vv_path.exists():
        raise FileNotFoundError(f"VV GeoTIFF not found: {vv_path}")
    if not vh_path.exists():
        raise FileNotFoundError(f"VH GeoTIFF not found: {vh_path}")

    vv_src = rasterio.open(vv_path)
    vh_src = rasterio.open(vh_path)

    # 1. Spatial CRS validation
    if vv_src.crs is None or vh_src.crs is None:
        raise ValueError("Input GeoTIFF rasters must declare a valid CRS")
    if vv_src.crs != vh_src.crs:
        raise ValueError(f"CRS mismatch: VV={vv_src.crs}, VH={vh_src.crs}")

    # 2. Dimensional validation
    if vv_src.shape != vh_src.shape:
        raise ValueError(f"Raster shape mismatch: VV={vv_src.shape}, VH={vh_src.shape}")

    # 3. Transform validation
    vv_t = list(vv_src.transform)[:6]
    vh_t = list(vh_src.transform)[:6]
    if not np.allclose(vv_t, vh_t, atol=1e-5):
        raise ValueError(f"Affine transform mismatch: VV={vv_t}, VH={vh_t}")

    # 4. Extract provenance from tags
    vv_tags = vv_src.tags()
    vh_tags = vh_src.tags()

    provenance = {
        "vv_path": str(vv_path.resolve()),
        "vh_path": str(vh_path.resolve()),
        "crs": str(vv_src.crs),
        "shape": list(vv_src.shape),
        "transform": list(vv_t),
        "vv_radiometric_mode": vv_tags.get("RADIOMETRIC_MODE", "UNKNOWN"),
        "vh_radiometric_mode": vh_tags.get("RADIOMETRIC_MODE", "UNKNOWN"),
        "source_stac_item_id": vv_tags.get("SOURCE_STAC_ITEM_ID") or vh_tags.get("SOURCE_STAC_ITEM_ID"),
        "source_product_id": vv_tags.get("SOURCE_PRODUCT_ID") or vh_tags.get("SOURCE_PRODUCT_ID"),
        "source_archive_sha256": vv_tags.get("SOURCE_ARCHIVE_SHA256") or vh_tags.get("SOURCE_ARCHIVE_SHA256"),
        "processing_timestamp": vv_tags.get("PROCESSING_TIMESTAMP"),
    }

    return provenance, vv_src, vh_src


def execute_oilseg_v1_inference(
    vv_geotiff_path: str | Path,
    vh_geotiff_path: str | Path,
    output_dir: str | Path,
    checkpoint_path: str | Path | None = None,
    threshold: float = 0.5,
    tile_size: int = 256,
    stride: int = 128,
    min_polygon_pixels: int = 10,
) -> OilSegV1Result:
    """Execute tiled 2-channel OilSeg V1 inference over VV and VH GeoTIFFs."""
    now_utc = datetime.now(timezone.utc).isoformat()
    vv_p = Path(vv_geotiff_path)
    vh_p = Path(vh_geotiff_path)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    ckpt_p = Path(checkpoint_path) if checkpoint_path else DEFAULT_V1_CHECKPOINT

    # RULE 6: No model -> return MODEL_UNAVAILABLE gracefully. Never generate fake masks!
    if not ckpt_p.exists():
        logger.warning(f"OilSeg V1 checkpoint not found: {ckpt_p}")
        return OilSegV1Result(
            status="MODEL_UNAVAILABLE",
            model_version=None,
            checkpoint_sha256=None,
            inference_timestamp=now_utc,
            evidence_raster_path=None,
            binary_mask_path=None,
            geojson_polygons=None,
            statistics=None,
            input_provenance={"vv_path": str(vv_p), "vh_path": str(vh_p)},
            reason=f"Model checkpoint not found at {ckpt_p}. Fake masks will never be generated.",
        )

    # Validate inputs
    try:
        provenance, vv_src, vh_src = validate_sar_inputs(vv_p, vh_p)
    except Exception as err:
        logger.error(f"Input validation error: {err}")
        return OilSegV1Result(
            status="VALIDATION_ERROR",
            inference_timestamp=now_utc,
            input_provenance={"vv_path": str(vv_p), "vh_path": str(vh_p)},
            reason=str(err),
        )

    # Compute checkpoint SHA-256
    checkpoint_sha = compute_file_sha256(ckpt_p)

    evidence_raster_path = out_dir / f"{vv_p.stem}_oil_evidence.tif"
    binary_mask_path = out_dir / f"{vv_p.stem}_oil_binary.tif"

    try:
        # Windowed inference across tiles
        inf_res = run_windowed_inference(
            checkpoint_path=ckpt_p,
            image_path=vv_p,
            vh_image_path=vh_p,
            output_geotiff_path=binary_mask_path,
            prob_geotiff_path=evidence_raster_path,
            threshold=threshold,
            tile_size=tile_size,
            stride=stride,
        )

        # Read back outputs for polygon extraction and stats
        with rasterio.open(evidence_raster_path) as ev_src:
            evidence_arr = ev_src.read(1)
            crs_str = str(ev_src.crs)
            affine = ev_src.transform

        with rasterio.open(binary_mask_path) as bin_src:
            bin_arr = bin_src.read(1)

        total_pixels = int(bin_arr.size)
        oil_pixel_mask = bin_arr > 0
        oil_pixels = int(oil_pixel_mask.sum())
        oil_fraction = float(oil_pixels / max(total_pixels, 1))

        mean_oil_score = float(evidence_arr[oil_pixel_mask].mean()) if oil_pixels > 0 else 0.0
        max_oil_score = float(evidence_arr.max()) if total_pixels > 0 else 0.0

        # Extract GeoJSON polygons using rasterio.features.shapes
        binary_for_shapes = (bin_arr > 0).astype(np.uint8)
        features: List[Dict[str, Any]] = []
        total_oil_area_m2 = 0.0
        polygon_idx = 1

        for geom, val in shapes(binary_for_shapes, mask=binary_for_shapes.astype(bool), transform=affine):
            if val != 1:
                continue
            poly = shape(geom)
            if poly.area <= 0:
                continue

            # Raster pixel mask for this specific polygon to compute mean evidence score
            # Approximate using bounding box slice
            minx, miny, maxx, maxy = poly.bounds
            col_min, row_max = ~affine * (minx, miny)
            col_max, row_min = ~affine * (maxx, maxy)
            r0, r1 = max(0, int(row_min)), min(bin_arr.shape[0], int(row_max) + 1)
            c0, c1 = max(0, int(col_min)), min(bin_arr.shape[1], int(col_max) + 1)

            poly_pixels = binary_for_shapes[r0:r1, c0:c1]
            if poly_pixels.sum() < min_polygon_pixels:
                continue

            ev_sub = evidence_arr[r0:r1, c0:c1]
            poly_mask = poly_pixels > 0
            p_mean_score = float(ev_sub[poly_mask].mean()) if poly_mask.sum() > 0 else 0.0
            p_max_score = float(ev_sub[poly_mask].max()) if poly_mask.sum() > 0 else 0.0

            area_m2, perim_m, centroid = compute_geodetic_polygon_metrics(poly, crs_str)
            total_oil_area_m2 += area_m2

            # Contour for morphology
            # Extract OpenCV contour from subpatch
            contours, _ = cv2.findContours(poly_pixels, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if contours:
                solidity, elongation = calculate_morphology(contours[0])
            else:
                solidity, elongation = 1.0, 1.0

            poly_id = f"SLICK_CANDIDATE_{polygon_idx:03d}"
            props = OilSegV1PolygonProperties(
                id=poly_id,
                area_m2=round(area_m2, 2),
                area_km2=round(area_m2 / 1e6, 6),
                perimeter_m=round(perim_m, 2),
                mean_oil_evidence_score=round(p_mean_score, 4),
                max_oil_evidence_score=round(p_max_score, 4),
                solidity=round(solidity, 4),
                elongation=round(elongation, 4),
                centroid_lon=round(centroid[0], 6),
                centroid_lat=round(centroid[1], 6),
            )

            features.append({
                "type": "Feature",
                "id": poly_id,
                "properties": props.model_dump(),
                "geometry": mapping(poly),
            })
            polygon_idx += 1

        geojson_fc = {
            "type": "FeatureCollection",
            "name": "varuna_oilseg_v1_polygons",
            "crs": {"type": "name", "properties": {"name": crs_str}},
            "features": features,
        }

        # Save GeoJSON
        geojson_path = out_dir / f"{vv_p.stem}_oil_polygons.geojson"
        geojson_path.write_text(json.dumps(geojson_fc, indent=2), encoding="utf-8")

        stats = OilSegV1Statistics(
            total_pixels=total_pixels,
            oil_pixels=oil_pixels,
            oil_fraction=round(oil_fraction, 6),
            total_oil_area_km2=round(total_oil_area_m2 / 1e6, 6),
            mean_oil_evidence_score=round(mean_oil_score, 4),
            max_oil_evidence_score=round(max_oil_score, 4),
            threshold=round(float(threshold), 4),
            polygon_count=len(features),
        )

        return OilSegV1Result(
            status="SUCCESS",
            model_version=inf_res.get("checkpoint_metadata", {}).get("model_version", "varuna-oilseg-v1-smallunet"),
            checkpoint_sha256=checkpoint_sha,
            inference_timestamp=now_utc,
            evidence_raster_path=str(evidence_raster_path.resolve()),
            binary_mask_path=str(binary_mask_path.resolve()),
            geojson_polygons=geojson_fc,
            statistics=stats,
            input_provenance=provenance,
        )

    finally:
        vv_src.close()
        vh_src.close()
