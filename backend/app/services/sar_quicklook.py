"""
VARUNA — SAR Quicklook Preprocessing & Calibration Service
Adapted from: m7mdehab/oil-spill-detection (src/oilspill/pipeline/preprocess.py)
License: MIT (Copyright (c) 2024-2026 Mohammed Ehab)
Source Commit SHA: 6c18c292153b3c617dd1e015dbe00f86272f9437

PIPELINE DESIGNATION:
VARUNA QUICKLOOK SAR ANALYSIS
(Radiometric calibration, Lee speckle filtering, decibel scaling, and land suppression).
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Optional, Tuple, Union

import numpy as np
from scipy.ndimage import uniform_filter
import rasterio
from affine import Affine
from rasterio.crs import CRS
from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)

# ImageNet statistics matching training distributions
IMAGENET_MEAN: Tuple[float, float, float] = (0.485, 0.456, 0.406)
IMAGENET_STD: Tuple[float, float, float] = (0.229, 0.224, 0.225)

# Default dB window for ocean Sentinel-1 VV backscatter
DEFAULT_DB_WINDOW: Tuple[float, float] = (-25.0, 0.0)
DEFAULT_DB_EPS: float = 1e-10


class CalibratedScene(NamedTuple):
    """Calibrated sigma0 with georeferencing needed for masking and inference."""
    sigma0: np.ndarray
    transform: Affine
    crs: CRS
    polarisation: str = "VV"
    vh_available: bool = False


class PreprocessedSceneResult(BaseModel):
    """Provenance and metadata record for VARUNA QUICKLOOK SAR ANALYSIS."""
    model_config = ConfigDict(frozen=True)

    pipeline_label: str = "VARUNA QUICKLOOK SAR ANALYSIS"
    case_id: str
    observation_id: str
    source_input_path: str
    input_sha256: str
    raster_dimensions: Tuple[int, int]
    crs: str
    vv_processed: bool
    vh_available: bool
    processed_db_geotiff_path: str
    output_sha256: str
    started_at: str
    completed_at: str
    status: str
    error_message: Optional[str] = None


def lee_filter(image: np.ndarray, size: int = 7) -> np.ndarray:
    r"""Apply the classic Lee (1980) adaptive speckle filter.

    Models SAR speckle as multiplicative noise and derives the minimum-mean-square-error
    estimate of true reflectivity within a local moving window:
        x_hat = y_mean + W * (y - y_mean)
        W = Var_signal / Var_y
        Var_signal = (Var_y - y_mean^2 * Cu^2) / (1 + Cu^2)
    where Cu = std / mean. Mean-preserving on homogeneous regions while suppressing variance.
    """
    if image.ndim != 2:
        raise ValueError(f"lee_filter expects a 2-D array, got shape {image.shape}")
    if size < 1:
        raise ValueError(f"window size must be >= 1, got {size}")

    img = np.asarray(image, dtype=np.float64)

    local_mean = uniform_filter(img, size=size)
    local_sqr_mean = uniform_filter(img**2, size=size)
    local_var = local_sqr_mean - local_mean**2
    local_var = np.maximum(local_var, 0.0)

    global_mean = float(img.mean())
    global_var = float(img.var())
    cu2 = global_var / (global_mean**2) if global_mean != 0.0 else 0.0

    signal_var = (local_var - (local_mean**2) * cu2) / (1.0 + cu2)
    signal_var = np.maximum(signal_var, 0.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        weight = np.where(local_var > 0.0, signal_var / local_var, 0.0)
    weight = np.clip(weight, 0.0, 1.0)
    weight = np.where(np.isfinite(weight), weight, 0.0)

    return local_mean + weight * (img - local_mean)


def to_db(sigma0: np.ndarray, eps: float = DEFAULT_DB_EPS) -> np.ndarray:
    """Convert linear-power sigma0 to decibels: 10 * log10(max(sigma0, eps))."""
    if eps <= 0.0:
        raise ValueError(f"eps must be positive, got {eps}")
    arr = np.asarray(sigma0, dtype=np.float64)
    return 10.0 * np.log10(np.maximum(arr, eps))


def normalize_for_model(
    db: np.ndarray,
    *,
    in_min: float = DEFAULT_DB_WINDOW[0],
    in_max: float = DEFAULT_DB_WINDOW[1],
) -> np.ndarray:
    """Map SAR dB into model expected 3-channel [0, 1] input range.

    Replicates single SAR channel across 3 channels to match 8-bit RGB training distributions.
    """
    if not in_min < in_max:
        raise ValueError(f"require in_min < in_max, got in_min={in_min}, in_max={in_max}")
    arr = np.asarray(db, dtype=np.float64)
    scaled = (arr - in_min) / (in_max - in_min)
    scaled = np.clip(scaled, 0.0, 1.0).astype(np.float32)
    return np.repeat(scaled[..., np.newaxis], 3, axis=-1)


def model_ready_chw(
    db: np.ndarray,
    *,
    in_min: float = DEFAULT_DB_WINDOW[0],
    in_max: float = DEFAULT_DB_WINDOW[1],
    mean: Tuple[float, float, float] = IMAGENET_MEAN,
    std: Tuple[float, float, float] = IMAGENET_STD,
) -> np.ndarray:
    """Produce model-ready CHW tensor: dB -> [0, 1] -> ImageNet-normalised."""
    hwc = normalize_for_model(db, in_min=in_min, in_max=in_max)
    mean_arr = np.asarray(mean, dtype=np.float32)
    std_arr = np.asarray(std, dtype=np.float32)
    normed = (hwc - mean_arr) / std_arr
    return np.transpose(normed, (2, 0, 1)).astype(np.float32)


def read_sar_raster(
    raster_path: Union[str, Path],
    polarisation: str = "VV",
    *,
    bbox: Optional[Tuple[float, float, float, float]] = None,
) -> CalibratedScene:
    """Read a SAR raster file (GeoTIFF, COG, or SAFE directory) as intensity.

    Supports single-file GeoTIFF / COG and full Sentinel-1 SAFE directory measurements.
    """
    path = Path(raster_path)
    pol = polarisation.lower()

    if path.is_dir() and path.suffix == ".SAFE":
        return read_grd_measurement(path, polarisation=polarisation, bbox=bbox)

    # Check for direct GeoTIFF / COG
    if not path.is_file():
        # Check if measurement directory exists under path
        meas_dir = path / "measurement"
        if meas_dir.is_dir():
            return read_grd_measurement(path, polarisation=polarisation, bbox=bbox)
        raise FileNotFoundError(f"SAR raster not found at: {path}")

    with rasterio.open(path) as ds:
        # Check for GCPs or standard affine
        if ds.gcps[0]:
            from rasterio.transform import from_gcps
            transform = from_gcps(ds.gcps[0])
            crs = ds.gcps[1] or CRS.from_epsg(4326)
        else:
            transform = ds.transform
            crs = ds.crs or CRS.from_epsg(4326)

        data = ds.read(1).astype(np.float64)
        # Intensity = DN^2 if raw amplitude, or direct linear power
        intensity = np.where(data > 0, data**2 if np.max(data) > 100.0 else data, 0.0)

    # Check if VH partner file is present
    vh_available = False
    parent = path.parent
    vh_files = list(parent.glob(f"*{path.stem}*vh*")) + list(parent.glob("*vh*.tif*"))
    if vh_files:
        vh_available = True

    return CalibratedScene(
        sigma0=intensity,
        transform=transform,
        crs=crs,
        polarisation=polarisation.upper(),
        vh_available=vh_available,
    )


def read_grd_measurement(
    safe_path: Union[Path, str],
    polarisation: str = "vv",
    *,
    bbox: Optional[Tuple[float, float, float, float]] = None,
) -> CalibratedScene:
    """Read a GRD measurement GeoTIFF from a SAFE directory with GCP georeferencing."""
    from affine import Affine
    from rasterio.transform import from_gcps
    from rasterio.windows import Window

    safe = Path(safe_path)
    pol = polarisation.lower()
    tifs = sorted(safe.glob(f"measurement/*-{pol}-*.tiff"))
    if not tifs:
        tifs = sorted(safe.glob(f"measurement/*-{pol}-*.tif"))
    if not tifs:
        # Fallback to any measurement tiff
        tifs = sorted(safe.glob("measurement/*.tiff")) or sorted(safe.glob("measurement/*.tif"))
    if not tifs:
        raise FileNotFoundError(f"No {pol} measurement GeoTIFF under {safe}")

    meas_file = tifs[0]
    vh_tifs = sorted(safe.glob("measurement/*-vh-*.tiff")) + sorted(safe.glob("measurement/*-vh-*.tif"))
    vh_available = len(vh_tifs) > 0

    with rasterio.open(meas_file) as ds:
        gcps, gcp_crs = ds.gcps
        if gcps:
            full_transform = from_gcps(gcps)
            crs = gcp_crs or CRS.from_epsg(4326)
        else:
            full_transform = ds.transform
            crs = ds.crs or CRS.from_epsg(4326)

        if bbox is not None:
            min_lon, min_lat, max_lon, max_lat = bbox
            inv = ~full_transform
            corners = [
                (min_lon, min_lat),
                (min_lon, max_lat),
                (max_lon, min_lat),
                (max_lon, max_lat),
            ]
            pixel_coords = [inv * (lon, lat) for lon, lat in corners]
            cols = [c for c, _ in pixel_coords]
            rows = [r for _, r in pixel_coords]
            col_off = max(0, int(np.floor(min(cols))))
            row_off = max(0, int(np.floor(min(rows))))
            col_end = min(ds.width, int(np.ceil(max(cols))))
            row_end = min(ds.height, int(np.ceil(max(rows))))
            if col_end <= col_off or row_end <= row_off:
                raise ValueError("Requested bbox does not overlap the scene footprint")
            window = Window(col_off, row_off, col_end - col_off, row_end - row_off)
            dn = ds.read(1, window=window).astype(np.float64)
            transform = full_transform * Affine.translation(col_off, row_off)
        else:
            dn = ds.read(1).astype(np.float64)
            transform = full_transform

    intensity = dn * dn
    return CalibratedScene(
        sigma0=intensity,
        transform=transform,
        crs=crs,
        polarisation=polarisation.upper(),
        vh_available=vh_available,
    )


def calibrate_safe(
    safe_path: Union[str, Path],
    *,
    polarisation: str = "vv",
) -> CalibratedScene:
    """Attempt radiometric calibration via xarray-sentinel; fallback to read_grd_measurement."""
    safe = Path(safe_path)
    if not safe.exists():
        raise FileNotFoundError(f"SAFE product not found: {safe}")

    try:
        import xarray_sentinel as xs
        pol = polarisation.upper()
        mode = "IW"
        for token in safe.name.split("_"):
            if token in ("IW", "EW", "WV"):
                mode = token
                break

        group = f"{mode}/{pol}"
        measurement = xs.open_sentinel1_dataset(str(safe), group=group)
        calibration = xs.open_sentinel1_dataset(str(safe), group=f"{group}/calibration")
        dn = measurement["measurement"]
        sigma0_da = xs.calibrate_intensity(dn, calibration["sigmaNought"])
        import rioxarray
        transform = sigma0_da.rio.transform(recalc=True)
        crs = sigma0_da.rio.crs or CRS.from_epsg(4326)
        sigma0 = np.asarray(sigma0_da.values, dtype=np.float64)
        return CalibratedScene(
            sigma0=sigma0,
            transform=transform,
            crs=crs,
            polarisation=polarisation.upper(),
            vh_available=True,
        )
    except Exception as exc:
        logger.debug(f"xarray-sentinel calibration unavailable ({exc}); using GCP measurement fallback.")
        return read_grd_measurement(safe_path, polarisation=polarisation)


def land_mask_from_coastlines(
    shape: Tuple[int, int],
    transform: Affine,
    crs: CRS,
    coastlines_path: Union[str, Path],
) -> np.ndarray:
    """Rasterise land polygons onto scene grid to suppress over-land false positives."""
    import geopandas as gpd
    from rasterio.features import rasterize
    from shapely.geometry import mapping

    path = Path(coastlines_path)
    if not path.exists():
        logger.warning(f"Coastlines path does not exist: {path}. Skipping land mask.")
        return np.zeros(shape, dtype=bool)

    target_crs = crs if isinstance(crs, CRS) else CRS.from_user_input(crs)
    gdf = gpd.read_file(path)
    if gdf.crs is not None:
        gdf = gdf.to_crs(target_crs.to_wkt())

    geometries = [mapping(geom) for geom in gdf.geometry if geom is not None and not geom.is_empty]
    if not geometries:
        return np.zeros(shape, dtype=bool)

    burned = rasterize(
        ((g, 1) for g in geometries),
        out_shape=shape,
        transform=transform,
        fill=0,
        dtype="uint8",
        all_touched=True,
    )
    return np.asarray(burned, dtype=bool)


def execute_quicklook_preprocessing(
    case_id: str,
    observation_id: str,
    source_input_path: Union[str, Path],
    *,
    output_base_dir: Union[str, Path] = "data/cases",
    polarisation: str = "VV",
    filter_size: int = 7,
    db_window: Tuple[float, float] = DEFAULT_DB_WINDOW,
    coastlines_path: Optional[Union[str, Path]] = None,
) -> Tuple[PreprocessedSceneResult, CalibratedScene, np.ndarray, np.ndarray]:
    """Execute complete VARUNA QUICKLOOK SAR preprocessing pipeline:

    RAW SCENE -> CALIBRATE / READ -> LEE FILTER -> DECIBEL (dB) -> MODEL TENSOR & EXPORT GEOTIFF
    Target directory: data/cases/<case_id>/observations/<observation_id>/processed/
    """
    started_at = datetime.now(timezone.utc).isoformat()
    p_in = Path(source_input_path)
    input_sha256 = ""
    if p_in.is_file():
        h = hashlib.sha256()
        with p_in.open("rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        input_sha256 = h.hexdigest()

    proc_dir = Path(output_base_dir) / case_id / "observations" / observation_id / "processed"
    proc_dir.mkdir(parents=True, exist_ok=True)

    try:
        # 1. Calibrate / read intensity
        scene = read_sar_raster(source_input_path, polarisation=polarisation)
        h_dim, w_dim = scene.sigma0.shape

        # 2. Apply Lee filter
        filtered_sigma0 = lee_filter(scene.sigma0, size=filter_size)

        # 3. Convert to dB
        sigma0_db = to_db(filtered_sigma0)

        # 4. Land mask if provided
        land_mask = None
        if coastlines_path:
            land_mask = land_mask_from_coastlines(
                (h_dim, w_dim), scene.transform, scene.crs, coastlines_path
            )
            # Mask out land in dB
            sigma0_db = np.where(land_mask, db_window[0], sigma0_db)

        # 5. Export preprocessed dB GeoTIFF
        out_tif = proc_dir / f"{observation_id}_sigma0_db.tif"
        with rasterio.open(
            out_tif,
            "w",
            driver="GTiff",
            height=h_dim,
            width=w_dim,
            count=1,
            dtype=rasterio.float32,
            crs=scene.crs,
            transform=scene.transform,
            compress="deflate",
        ) as dst:
            dst.write(sigma0_db.astype(np.float32), 1)
            dst.update_tags(
                PIPELINE="VARUNA QUICKLOOK SAR ANALYSIS",
                POLARISATION=scene.polarisation,
                FILTER="LEE_SPECKLE_MMSE",
                FILTER_SIZE=str(filter_size),
                DB_WINDOW=f"{db_window[0]},{db_window[1]}",
            )

        # Compute output hash
        h_out = hashlib.sha256()
        with out_tif.open("rb") as f:
            while chunk := f.read(65536):
                h_out.update(chunk)
        out_sha256 = h_out.hexdigest()

        completed_at = datetime.now(timezone.utc).isoformat()
        result = PreprocessedSceneResult(
            case_id=case_id,
            observation_id=observation_id,
            source_input_path=str(source_input_path),
            input_sha256=input_sha256,
            raster_dimensions=(h_dim, w_dim),
            crs=str(scene.crs),
            vv_processed=True,
            vh_available=scene.vh_available,
            processed_db_geotiff_path=str(out_tif),
            output_sha256=out_sha256,
            started_at=started_at,
            completed_at=completed_at,
            status="SUCCESS",
        )
        return result, scene, filtered_sigma0, sigma0_db

    except Exception as exc:
        completed_at = datetime.now(timezone.utc).isoformat()
        logger.error(f"Quicklook preprocessing failed: {exc}", exc_info=True)
        result = PreprocessedSceneResult(
            case_id=case_id,
            observation_id=observation_id,
            source_input_path=str(source_input_path),
            input_sha256=input_sha256,
            raster_dimensions=(0, 0),
            crs="",
            vv_processed=False,
            vh_available=False,
            processed_db_geotiff_path="",
            output_sha256="",
            started_at=started_at,
            completed_at=completed_at,
            status="FAILED",
            error_message=str(exc),
        )
        raise exc
