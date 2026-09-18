"""
VARUNA — Tiled SAR Inference & Vectorisation Engine
Adapted from: m7mdehab/oil-spill-detection (src/oilspill/pipeline/infer.py, vectorize.py, detect.py)
License: MIT (Copyright (c) 2024-2026 Mohammed Ehab)
Source Commit SHA: 6c18c292153b3c617dd1e015dbe00f86272f9437

PIPELINE DESIGNATION:
VARUNA QUICKLOOK SAR ANALYSIS — TILED INFERENCE & VECTORISATION
(Overlapping sliding-window tiled inference, cosine-window logit blending,
land false-positive suppression, geodesic WGS84 polygon area calculation).
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import geopandas as gpd
import numpy as np
import rasterio
from affine import Affine
from pydantic import BaseModel, ConfigDict
from pyproj import CRS as PyprojCRS
from pyproj import Geod
from rasterio.crs import CRS
from rasterio.features import geometry_mask, shapes
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry

try:
    import onnxruntime as ort
    HAS_ONNX = True
except ImportError:
    HAS_ONNX = False
    ort = None  # type: ignore

logger = logging.getLogger(__name__)

# Canonical 5-class scheme
CLASS_NAMES: Tuple[str, ...] = (
    "Sea Surface",
    "Oil Spill",
    "Look-alike",
    "Ship",
    "Land",
)
NUM_CLASSES: int = len(CLASS_NAMES)
OIL_CLASS_INDEX: int = 1

# Class id -> (R, G, B) legend
CLASS_COLORS: Tuple[Tuple[int, int, int], ...] = (
    (0, 0, 0),       # 0 Sea Surface
    (0, 255, 255),   # 1 Oil Spill (Cyan)
    (255, 0, 0),     # 2 Look-alike (Red)
    (153, 76, 0),    # 3 Ship (Brown)
    (0, 153, 0),     # 4 Land (Green)
)
COLOR_LUT: np.ndarray = np.asarray(CLASS_COLORS, dtype=np.uint8)

DEFAULT_MIN_AREA_M2: float = 5000.0  # 0.005 km^2 minimum surface area
WGS84_EPSG: int = 4326
GEOD_WGS84 = Geod(ellps="WGS84")

INPUT_NAME = "input"
OUTPUT_NAME = "logits"


class QuicklookInferenceResult(BaseModel):
    """Immutable record of quicklook SAR inference and vectorisation provenance."""
    model_config = ConfigDict(frozen=True)

    pipeline_label: str = "VARUNA QUICKLOOK SAR ANALYSIS"
    case_id: str
    observation_id: str
    model_path: Optional[str] = None
    model_version: str = "oilspill-segformer-v1"
    status: str  # "SUCCESS" | "MODEL_UNAVAILABLE" | "FAILED"
    class_mask_path: Optional[str] = None
    class_mask_rgb_path: Optional[str] = None
    geojson_path: Optional[str] = None
    num_oil_polygons: int = 0
    total_oil_area_km2: float = 0.0
    tile_size: int = 512
    overlap: int = 64
    min_area_m2: float = DEFAULT_MIN_AREA_M2
    mask_sha256: str = ""
    geojson_sha256: str = ""
    started_at: str
    completed_at: str
    error_message: Optional[str] = None


def load_session(onnx_path: Union[str, Path]) -> ort.InferenceSession:
    """Open an ONNX model as a CPU onnxruntime.InferenceSession."""
    if not HAS_ONNX:
        raise ImportError("onnxruntime is required for tiled ONNX inference.")
    path = Path(onnx_path)
    if not path.exists():
        raise FileNotFoundError(f"ONNX model not found: {path}")
    return ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])


def _cosine_window(tile_size: int) -> np.ndarray:
    """Return a 2-D cosine (Hann) taper (tile_size, tile_size) in (0, 1].

    Weights tile interiors above feathered boundaries to avoid stitch seams.
    """
    if tile_size == 1:
        return np.ones((1, 1), dtype=np.float64)
    n = np.arange(tile_size, dtype=np.float64)
    hann = 0.5 - 0.5 * np.cos(2.0 * np.pi * n / (tile_size - 1))
    hann = hann * (1.0 - 1e-3) + 1e-3
    return np.outer(hann, hann)


def _tile_origins(extent: int, tile_size: int, stride: int) -> List[int]:
    """Calculate top-left tile origins covering [0, extent) exactly."""
    if extent <= tile_size:
        return [0]
    origins = list(range(0, extent - tile_size + 1, stride))
    if origins[-1] != extent - tile_size:
        origins.append(extent - tile_size)
    return origins


def _iter_batches(items: List[Tuple[int, int]], batch_size: int) -> Iterator[List[Tuple[int, int]]]:
    """Yield tile origins in batches."""
    for start in range(0, len(items), batch_size):
        yield items[start : start + batch_size]


def tiled_predict(
    scene_chw: np.ndarray,
    session: Any,
    *,
    tile_size: int = 512,
    overlap: int = 64,
    batch_size: int = 4,
    num_classes: int = NUM_CLASSES,
) -> Tuple[np.ndarray, np.ndarray]:
    """Run overlapping tiled inference over full SAR scene with cosine logit blending.

    Preserves exact 1:1 geospatial pixel alignment with input raster.
    """
    if scene_chw.ndim != 3 or scene_chw.shape[0] != 3:
        raise ValueError(f"scene_chw must have shape (3, H, W), got {scene_chw.shape}")
    if tile_size < 1:
        raise ValueError(f"tile_size must be >= 1, got {tile_size}")
    if not 0 <= overlap < tile_size:
        raise ValueError(f"require 0 <= overlap < tile_size, got overlap={overlap}")
    if batch_size < 1:
        raise ValueError(f"batch_size must be >= 1, got {batch_size}")

    scene = np.ascontiguousarray(scene_chw, dtype=np.float32)
    _, height, width = scene.shape
    stride = tile_size - overlap

    def _padded_extent(extent: int) -> int:
        target = max(extent, tile_size)
        n_strides = (target - tile_size + stride - 1) // stride
        return tile_size + n_strides * stride

    pad_h = _padded_extent(height)
    pad_w = _padded_extent(width)

    pad_mode_h = "reflect" if (pad_h - height) < height else "edge"
    pad_mode_w = "reflect" if (pad_w - width) < width else "edge"
    if pad_mode_h != pad_mode_w:
        mode = "edge"
        padded = np.pad(scene, ((0, 0), (0, pad_h - height), (0, pad_w - width)), mode=mode)
    else:
        padded = np.pad(scene, ((0, 0), (0, pad_h - height), (0, pad_w - width)), mode=pad_mode_h)

    origins_y = _tile_origins(pad_h, tile_size, stride)
    origins_x = _tile_origins(pad_w, tile_size, stride)
    tile_origins = [(y, x) for y in origins_y for x in origins_x]

    window = _cosine_window(tile_size)
    logit_acc = np.zeros((num_classes, pad_h, pad_w), dtype=np.float64)
    weight_acc = np.zeros((pad_h, pad_w), dtype=np.float64)

    for batch in _iter_batches(tile_origins, batch_size):
        tiles = np.stack(
            [padded[:, y : y + tile_size, x : x + tile_size] for (y, x) in batch],
            axis=0,
        ).astype(np.float32)

        if hasattr(session, "run"):
            # ONNX InferenceSession
            input_name = session.get_inputs()[0].name
            output_name = session.get_outputs()[0].name
            outputs = session.run([output_name], {input_name: tiles})[0]
            logits = np.asarray(outputs, dtype=np.float64)
        elif callable(session):
            # Python / PyTorch callable
            logits = np.asarray(session(tiles), dtype=np.float64)
        else:
            raise TypeError("Session must be an onnxruntime InferenceSession or callable.")

        if logits.shape[1] != num_classes:
            raise ValueError(
                f"Model produced {logits.shape[1]} classes, expected num_classes={num_classes}"
            )

        for tile_logits, (y, x) in zip(logits, batch):
            logit_acc[:, y : y + tile_size, x : x + tile_size] += tile_logits * window
            weight_acc[y : y + tile_size, x : x + tile_size] += window

    # Weighted-average overlapping logits
    mean_logits = logit_acc / np.maximum(weight_acc[np.newaxis, :, :], 1e-12)
    mean_logits = mean_logits[:, :height, :width]

    # Stable softmax
    shifted = mean_logits - mean_logits.max(axis=0, keepdims=True)
    exp = np.exp(shifted)
    probs = exp / np.maximum(exp.sum(axis=0, keepdims=True), 1e-12)

    class_mask = np.argmax(mean_logits, axis=0).astype(np.uint8)
    oil_prob = probs[OIL_CLASS_INDEX].astype(np.float32)
    return class_mask, oil_prob


def as_crs(crs: Union[CRS, PyprojCRS, str, int]) -> CRS:
    """Normalize CRS specification to rasterio.crs.CRS."""
    if isinstance(crs, CRS):
        return crs
    if isinstance(crs, PyprojCRS):
        return CRS.from_wkt(crs.to_wkt())
    if isinstance(crs, int):
        return CRS.from_epsg(crs)
    return CRS.from_user_input(crs)


def write_geotiff(
    array: np.ndarray,
    path: Union[Path, str],
    transform: Affine,
    crs: Union[CRS, PyprojCRS, str, int],
    *,
    nodata: Optional[Union[float, int]] = None,
) -> Path:
    """Write array to a single or multiband GeoTIFF."""
    arr = np.asarray(array)
    if arr.ndim == 2:
        arr = arr[np.newaxis, :, :]
    elif arr.ndim != 3:
        raise ValueError(f"array must be 2-D (H, W) or 3-D (bands, H, W), got shape {arr.shape}")

    count, height, width = arr.shape
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    profile = {
        "driver": "GTiff",
        "height": height,
        "width": width,
        "count": count,
        "dtype": arr.dtype,
        "transform": transform,
        "crs": as_crs(crs),
        "compress": "deflate",
    }
    if nodata is not None:
        profile["nodata"] = nodata

    with rasterio.open(out_path, "w", **profile) as dst:
        dst.write(arr)
    return out_path


def polygon_area_km2(geom: BaseGeometry, crs: Union[CRS, PyprojCRS, str, int]) -> float:
    """Calculate physically accurate polygon surface area in km^2.

    Uses WGS84 geodesic area on ellipsoid for geographic CRSs, and planar area for metric CRSs.
    """
    pyproj_crs = PyprojCRS.from_user_input(as_crs(crs).to_wkt())
    if pyproj_crs.is_geographic:
        area_m2, _ = GEOD_WGS84.geometry_area_perimeter(geom)
        return abs(area_m2) / 1e6
    return float(geom.area) / 1e6


def _confidence_stats(
    geom: BaseGeometry,
    oil_prob: np.ndarray,
    transform: Affine,
) -> Tuple[float, float]:
    """Calculate mean and max oil confidence probability over polygon pixels."""
    height, width = oil_prob.shape
    inside = ~geometry_mask(
        [geom],
        out_shape=(height, width),
        transform=transform,
        all_touched=True,
        invert=False,
    )
    if not inside.any():
        return 0.0, 0.0
    values = oil_prob[inside]
    return float(values.mean()), float(values.max())


def vectorize_oil(
    class_mask: np.ndarray,
    transform: Affine,
    crs: Union[CRS, PyprojCRS, str, int],
    *,
    oil_prob: Optional[np.ndarray] = None,
    min_area_m2: float = DEFAULT_MIN_AREA_M2,
) -> gpd.GeoDataFrame:
    """Vectorise oil-spill class pixels into cleaned, area-filtered polygons."""
    mask = np.asarray(class_mask)
    if mask.ndim != 2:
        raise ValueError(f"class_mask must be 2-D (H, W), got shape {mask.shape}")
    scene_crs = as_crs(crs)

    if oil_prob is not None:
        oil_prob = np.asarray(oil_prob, dtype=np.float64)
        if oil_prob.shape != mask.shape:
            raise ValueError(f"oil_prob shape {oil_prob.shape} must match class_mask shape {mask.shape}")

    oil = (mask == OIL_CLASS_INDEX).astype(np.uint8)

    geoms: List[BaseGeometry] = []
    areas: List[float] = []
    mean_conf: List[float] = []
    max_conf: List[float] = []

    for geom_dict, value in shapes(oil, mask=oil.astype(bool), transform=transform):
        if value != 1:
            continue
        geom = shape(geom_dict)
        if not geom.is_valid:
            geom = geom.buffer(0)
        if geom.is_empty or not geom.is_valid:
            continue

        area_km2 = polygon_area_km2(geom, scene_crs)
        if area_km2 * 1e6 < min_area_m2:
            continue

        geoms.append(geom)
        areas.append(area_km2)
        if oil_prob is not None:
            mean_v, max_v = _confidence_stats(geom, oil_prob, transform)
            mean_conf.append(mean_v)
            max_conf.append(max_v)

    data: Dict[str, List[float]] = {"area_km2": areas}
    if oil_prob is not None:
        data["mean_confidence"] = mean_conf
        data["max_confidence"] = max_conf

    return gpd.GeoDataFrame(data, geometry=geoms, crs=scene_crs)


def to_geojson(gdf: gpd.GeoDataFrame, path: Union[Path, str]) -> Path:
    """Write GeoDataFrame to RFC 7946 EPSG:4326 GeoJSON."""
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if gdf.empty:
        # Write empty FeatureCollection GeoJSON
        empty_geojson = '{"type": "FeatureCollection", "features": []}'
        out_path.write_text(empty_geojson, encoding="utf-8")
        return out_path

    if gdf.crs is None:
        raise ValueError("gdf has no CRS; cannot reproject to EPSG:4326")
    wgs84 = gdf.to_crs(epsg=WGS84_EPSG)

    keep = [c for c in ("area_km2", "mean_confidence", "max_confidence") if c in wgs84.columns]
    wgs84 = wgs84[[*keep, "geometry"]]
    wgs84.to_file(out_path, driver="GeoJSON")
    return out_path


def colorized_geotiff_from_mask(
    class_mask: np.ndarray,
    path: Union[Path, str],
    transform: Affine,
    crs: Union[CRS, PyprojCRS, str, int],
) -> Path:
    """Write RGB GeoTIFF colourised with dataset class palette."""
    mask = np.asarray(class_mask, dtype=np.int64)
    clamped = np.clip(mask, 0, NUM_CLASSES - 1)
    rgb = COLOR_LUT[clamped]  # (H, W, 3)
    chw = np.moveaxis(rgb, -1, 0)  # (3, H, W)
    return write_geotiff(chw, path, transform, crs)


def run_quicklook_segmentation(
    case_id: str,
    observation_id: str,
    scene_chw: np.ndarray,
    transform: Affine,
    crs: CRS,
    *,
    model_path: Optional[Union[str, Path]] = None,
    land_mask: Optional[np.ndarray] = None,
    output_base_dir: Union[str, Path] = "data/cases",
    tile_size: int = 512,
    overlap: int = 64,
    batch_size: int = 4,
    min_area_m2: float = DEFAULT_MIN_AREA_M2,
) -> QuicklookInferenceResult:
    """Execute complete VARUNA QUICKLOOK inference and vectorisation workflow:

    MODEL READY CHW -> TILED PREDICT (or MODEL_UNAVAILABLE) -> LAND SUPPRESSION ->
    CLASS GEOTIFF -> RGB GEOTIFF -> OIL POLYGON GEOJSON
    Outputs:
    - data/cases/<case_id>/observations/<observation_id>/inference/
    - data/cases/<case_id>/observations/<observation_id>/vectors/
    """
    started_at = datetime.now(timezone.utc).isoformat()
    obs_dir = Path(output_base_dir) / case_id / "observations" / observation_id
    inf_dir = obs_dir / "inference"
    vec_dir = obs_dir / "vectors"
    inf_dir.mkdir(parents=True, exist_ok=True)
    vec_dir.mkdir(parents=True, exist_ok=True)

    # If model_path is None or does not exist, halt gracefully at MODEL_UNAVAILABLE
    if not model_path or not Path(model_path).exists():
        logger.info(f"Segmentation model weights unavailable at '{model_path}'; returning MODEL_UNAVAILABLE.")
        completed_at = datetime.now(timezone.utc).isoformat()
        return QuicklookInferenceResult(
            case_id=case_id,
            observation_id=observation_id,
            model_path=str(model_path) if model_path else None,
            status="MODEL_UNAVAILABLE",
            tile_size=tile_size,
            overlap=overlap,
            min_area_m2=min_area_m2,
            started_at=started_at,
            completed_at=completed_at,
            error_message="Model weights are not present on local machine. Satellite acquisition and preprocessing preserved.",
        )

    try:
        session = load_session(model_path)
        class_mask, oil_prob = tiled_predict(
            scene_chw,
            session,
            tile_size=tile_size,
            overlap=overlap,
            batch_size=batch_size,
        )

        # Land false-positive suppression
        if land_mask is not None:
            land = np.asarray(land_mask, dtype=bool)
            if land.shape == class_mask.shape:
                oil_on_land = land & (class_mask == OIL_CLASS_INDEX)
                class_mask = class_mask.copy()
                oil_prob = oil_prob.copy()
                class_mask[oil_on_land] = 0
                oil_prob[land] = 0.0

        # Export inference GeoTIFFs
        mask_path = inf_dir / f"{observation_id}_class_mask.tif"
        rgb_path = inf_dir / f"{observation_id}_class_mask_rgb.tif"
        write_geotiff(class_mask, mask_path, transform, crs)
        colorized_geotiff_from_mask(class_mask, rgb_path, transform, crs)

        # Vectorize oil
        gdf = vectorize_oil(
            class_mask,
            transform,
            crs,
            oil_prob=oil_prob,
            min_area_m2=min_area_m2,
        )
        geojson_path = vec_dir / f"{observation_id}_oil_polygons.geojson"
        to_geojson(gdf, geojson_path)

        total_area = float(gdf["area_km2"].sum()) if len(gdf) else 0.0

        # Compute SHA256 hashes
        h_mask = hashlib.sha256()
        with mask_path.open("rb") as f:
            while chunk := f.read(65536):
                h_mask.update(chunk)

        h_geo = hashlib.sha256()
        with geojson_path.open("rb") as f:
            while chunk := f.read(65536):
                h_geo.update(chunk)

        completed_at = datetime.now(timezone.utc).isoformat()
        return QuicklookInferenceResult(
            case_id=case_id,
            observation_id=observation_id,
            model_path=str(model_path),
            status="SUCCESS",
            class_mask_path=str(mask_path),
            class_mask_rgb_path=str(rgb_path),
            geojson_path=str(geojson_path),
            num_oil_polygons=len(gdf),
            total_oil_area_km2=round(total_area, 4),
            tile_size=tile_size,
            overlap=overlap,
            min_area_m2=min_area_m2,
            mask_sha256=h_mask.hexdigest(),
            geojson_sha256=h_geo.hexdigest(),
            started_at=started_at,
            completed_at=completed_at,
        )
    except Exception as exc:
        completed_at = datetime.now(timezone.utc).isoformat()
        logger.error(f"Quicklook segmentation failed: {exc}", exc_info=True)
        return QuicklookInferenceResult(
            case_id=case_id,
            observation_id=observation_id,
            model_path=str(model_path),
            status="FAILED",
            started_at=started_at,
            completed_at=completed_at,
            error_message=str(exc),
        )
