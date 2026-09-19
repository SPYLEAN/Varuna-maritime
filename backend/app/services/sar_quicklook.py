"""
VARUNA — SAR Quicklook Preprocessing & Calibration Service
Adapted from: m7mdehab/oil-spill-detection (src/oilspill/pipeline/preprocess.py)
License: MIT (Copyright (c) 2024-2026 Mohammed Ehab)
Source Commit SHA: 6c18c292153b3c617dd1e015dbe00f86272f9437

PIPELINE DESIGNATION:
VARUNA QUICKLOOK SAR ANALYSIS
(Radiometric calibration, Lee speckle filtering, decibel scaling, and land suppression).
Terrain correction is NOT applied in this quicklook pipeline.
"""

from __future__ import annotations

import hashlib
import logging
import time
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

# Valid radiometric calibration modes
RADIOMETRIC_MODE_SIGMA0_LUT = "SIGMA0_LUT_CALIBRATED"
RADIOMETRIC_MODE_MEASUREMENT_INTENSITY_FALLBACK = "MEASUREMENT_INTENSITY_FALLBACK"
RADIOMETRIC_MODE_PROVIDER_PRECALIBRATED = "PROVIDER_PRECALIBRATED"
RADIOMETRIC_MODE_COG_PRECALIBRATED = RADIOMETRIC_MODE_PROVIDER_PRECALIBRATED  # backward compatibility alias
RADIOMETRIC_MODE_UNKNOWN = "UNKNOWN"


class GeoreferenceUnavailableError(Exception):
    """Raised when spatial georeferencing (CRS or affine transform) cannot be truthfully recovered."""
    pass


class CalibratedScene(NamedTuple):
    """Calibrated sigma0 with georeferencing needed for masking and inference."""
    sigma0: np.ndarray
    transform: Affine
    crs: CRS
    polarisation: str = "VV"
    vh_available: bool = False
    radiometric_mode: str = RADIOMETRIC_MODE_UNKNOWN


class SourceProvenance(BaseModel):
    """Explicit source provenance metadata carried from acquisition through preprocessing."""
    model_config = ConfigDict(frozen=True)

    source_stac_item_id: Optional[str] = None
    source_product_id: Optional[str] = None
    source_archive_sha256: Optional[str] = None
    source_archive_path: Optional[str] = None


class PreprocessedSceneResult(BaseModel):
    """Provenance and metadata record for VARUNA QUICKLOOK SAR ANALYSIS."""
    model_config = ConfigDict(frozen=True)

    pipeline_label: str = "VARUNA QUICKLOOK SAR ANALYSIS"
    case_id: str
    observation_id: str
    source_input_path: str
    input_sha256: str
    product_id: Optional[str] = None
    source_stac_item_id: Optional[str] = None
    source_product_id: Optional[str] = None
    source_archive_sha256: Optional[str] = None
    source_archive_path: Optional[str] = None
    raster_dimensions: Tuple[int, int]
    crs: str
    polarization: str = "VV"
    radiometric_mode: str = RADIOMETRIC_MODE_UNKNOWN
    filter_size: int = 7
    vv_processed: bool = True
    vh_available: bool = False
    vh_processed: bool = False
    processed_db_geotiff_path: str = ""
    vh_processed_db_geotiff_path: Optional[str] = None
    output_sha256: str = ""
    vh_output_sha256: Optional[str] = None
    dualpol_aligned: bool = False
    processing_duration_seconds: float = 0.0
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


def _acquisition_mode(safe: Path, xs: Any) -> str:
    """Determine the S1 acquisition mode group (e.g. IW, EW)."""
    for token in safe.name.split("_"):
        if token in ("IW", "EW", "WV"):
            return token
    try:
        root = xs.open_sentinel1_dataset(str(safe))
        subgroups = str(root.attrs.get("subgroups", "")).replace("[", " ").replace("]", " ")
        for candidate in ("IW", "EW", "WV"):
            if candidate in subgroups:
                return candidate
    except Exception:
        pass
    return "IW"


def _georef_from_dataarray(da: Any) -> Tuple[Affine, CRS]:
    """Recover affine transform and CRS from an xarray DataArray.

    Fails explicitly with GeoreferenceUnavailableError if truthful CRS or transform
    cannot be recovered. Never fabricates Affine.identity() or EPSG:4326.
    """
    try:
        import rioxarray  # noqa: F401
        if not hasattr(da, "rio"):
            raise GeoreferenceUnavailableError("DataArray lacks rio accessor for spatial georeferencing")

        crs = da.rio.crs
        if crs is None:
            raise GeoreferenceUnavailableError("DataArray rio.crs is None; truthful CRS unavailable")

        transform = da.rio.transform(recalc=True)
        if transform is None:
            raise GeoreferenceUnavailableError("DataArray rio.transform is None; truthful transform unavailable")

        # Refuse to accept default identity transform with EPSG:4326 when no spatial coordinates exist
        if transform == Affine.identity() and crs.to_epsg() == 4326 and "x" not in getattr(da, "coords", {}) and "longitude" not in getattr(da, "coords", {}):
            raise GeoreferenceUnavailableError("DataArray contains unreferenced default identity transform")

        return transform, crs
    except GeoreferenceUnavailableError:
        raise
    except Exception as exc:
        raise GeoreferenceUnavailableError(
            f"Failed to recover spatial georeferencing from DataArray: {exc}"
        ) from exc


def read_grd_measurement(
    safe_path: Union[Path, str],
    polarisation: str = "vv",
    *,
    bbox: Optional[Tuple[float, float, float, float]] = None,
) -> CalibratedScene:
    """Read a GRD measurement GeoTIFF from a SAFE directory with GCP georeferencing.

    Returns an uncalibrated relative intensity array with explicit
    radiometric_mode='MEASUREMENT_INTENSITY_FALLBACK'.
    """
    from affine import Affine
    from rasterio.transform import from_gcps
    from rasterio.windows import Window

    safe = Path(safe_path)
    pol = polarisation.lower()
    tifs = sorted(safe.glob(f"measurement/*-{pol}-*.tiff"))
    if not tifs:
        tifs = sorted(safe.glob(f"measurement/*-{pol}-*.tif"))
    if not tifs:
        tifs = sorted(safe.glob(f"*-{pol}-*.tiff")) or sorted(safe.glob(f"*-{pol}-*.tif"))
    if not tifs:
        tifs = sorted(safe.glob("measurement/*.tiff")) or sorted(safe.glob("measurement/*.tif"))
    if not tifs:
        raise FileNotFoundError(f"No {pol} measurement GeoTIFF under {safe}")

    meas_file = tifs[0]
    vh_tifs = sorted(safe.glob("measurement/*-vh-*.tiff")) + sorted(safe.glob("measurement/*-vh-*.tif"))
    vh_available = len(vh_tifs) > 0

    with rasterio.open(meas_file) as ds:
        gcps, gcp_crs = ds.gcps
        if gcps:
            if not gcp_crs:
                raise GeoreferenceUnavailableError(f"Measurement GeoTIFF {meas_file} contains GCPs but no GCP CRS")
            full_transform = from_gcps(gcps)
            crs = gcp_crs
        else:
            full_transform = ds.transform
            crs = ds.crs
            if crs is None:
                raise GeoreferenceUnavailableError(f"Measurement GeoTIFF {meas_file} contains no valid CRS")

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
        radiometric_mode=RADIOMETRIC_MODE_MEASUREMENT_INTENSITY_FALLBACK,
    )


def calibrate_safe(
    safe_path: Union[str, Path],
    *,
    polarisation: str = "vv",
) -> CalibratedScene:
    """Read a Sentinel-1 GRD SAFE and calibrate to Sigma0 using product calibration LUT.

    Attempts true radiometric calibration using xarray-sentinel and the sigmaNought LUT.
    Only if xarray-sentinel or the XML calibration LUT is unavailable does it fall back to
    read_grd_measurement, explicitly returning MEASUREMENT_INTENSITY_FALLBACK.
    """
    safe = Path(safe_path)
    if not safe.exists():
        raise FileNotFoundError(f"SAFE product not found: {safe}")

    pol = polarisation.upper()

    try:
        import xarray_sentinel as xs
        import rioxarray  # noqa: F401

        mode = _acquisition_mode(safe, xs)
        group = f"{mode}/{pol}"

        measurement = xs.open_sentinel1_dataset(str(safe), group=group)
        calibration = xs.open_sentinel1_dataset(str(safe), group=f"{group}/calibration")

        dn = measurement["measurement"]
        sigma0_da = xs.calibrate_intensity(dn, calibration["sigmaNought"])

        transform, crs = _georef_from_dataarray(sigma0_da)
        sigma0 = np.asarray(sigma0_da.values, dtype=np.float64)

        # Check VH availability
        vh_available = False
        try:
            xs.open_sentinel1_dataset(str(safe), group=f"{mode}/VH")
            vh_available = True
        except Exception:
            meas_dir = safe / "measurement"
            if meas_dir.exists():
                vh_tifs = list(meas_dir.glob("*-vh-*"))
                vh_available = len(vh_tifs) > 0

        return CalibratedScene(
            sigma0=sigma0,
            transform=transform,
            crs=crs,
            polarisation=pol,
            vh_available=vh_available,
            radiometric_mode=RADIOMETRIC_MODE_SIGMA0_LUT,
        )
    except Exception as exc:
        logger.warning(
            f"Full sigma0 calibration with xarray-sentinel unavailable ({exc}); "
            f"using fallback measurement intensity."
        )
        return read_grd_measurement(safe_path, polarisation=polarisation)


def read_sar_raster(
    raster_path: Union[str, Path],
    polarisation: str = "VV",
    *,
    bbox: Optional[Tuple[float, float, float, float]] = None,
    radiometric_mode: Optional[str] = None,
) -> CalibratedScene:
    """Read a SAR raster file (GeoTIFF, COG, or SAFE directory) as intensity.

    Generic rasters default to radiometric_mode='UNKNOWN' unless the caller or
    GeoTIFF metadata explicitly declares 'PROVIDER_PRECALIBRATED'.
    Does not determine physical semantics from pixel magnitude.
    """
    path = Path(raster_path)
    pol = polarisation.lower()

    if (path.is_dir() and path.suffix == ".SAFE") or (path.is_dir() and (path / "measurement").is_dir()):
        return calibrate_safe(path, polarisation=polarisation)

    if not path.is_file():
        meas_dir = path / "measurement"
        if meas_dir.is_dir():
            return calibrate_safe(path, polarisation=polarisation)
        raise FileNotFoundError(f"SAR raster not found at: {path}")

    with rasterio.open(path) as ds:
        if ds.gcps[0]:
            from rasterio.transform import from_gcps
            transform = from_gcps(ds.gcps[0])
            crs = ds.gcps[1]
            if crs is None:
                raise GeoreferenceUnavailableError(f"Raster {path} contains GCPs but no valid GCP CRS")
        else:
            transform = ds.transform
            crs = ds.crs
            if crs is None:
                raise GeoreferenceUnavailableError(f"Raster {path} contains no valid CRS")

        data = ds.read(1).astype(np.float64)
        intensity = np.maximum(data, 0.0)

        tags = ds.tags()
        tag_mode = tags.get("RADIOMETRIC_MODE", "")
        if radiometric_mode is not None:
            final_mode = radiometric_mode
        elif tag_mode in (
            RADIOMETRIC_MODE_PROVIDER_PRECALIBRATED,
            RADIOMETRIC_MODE_SIGMA0_LUT,
            RADIOMETRIC_MODE_MEASUREMENT_INTENSITY_FALLBACK,
        ):
            final_mode = tag_mode
        elif tags.get("PRECALIBRATED", "").lower() in ("true", "1", "yes"):
            final_mode = RADIOMETRIC_MODE_PROVIDER_PRECALIBRATED
        else:
            final_mode = RADIOMETRIC_MODE_UNKNOWN

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
        radiometric_mode=final_mode,
    )


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


def verify_dualpol_alignment(vv_scene: CalibratedScene, vh_scene: CalibratedScene) -> bool:
    """Verify VV and VH raster spatial alignment (dimensions, CRS, transform) before dual-pol ML use."""
    if vv_scene.sigma0.shape != vh_scene.sigma0.shape:
        raise ValueError(
            f"Dual-pol alignment failure: VV dimensions {vv_scene.sigma0.shape} != VH dimensions {vh_scene.sigma0.shape}"
        )
    if str(vv_scene.crs) != str(vh_scene.crs):
        raise ValueError(
            f"Dual-pol alignment failure: VV CRS {vv_scene.crs} != VH CRS {vh_scene.crs}"
        )
    if vv_scene.transform != vh_scene.transform:
        for a, b in zip(vv_scene.transform, vh_scene.transform):
            if abs(a - b) > 1e-5:
                raise ValueError(
                    f"Dual-pol alignment failure: VV transform {vv_scene.transform} != VH transform {vh_scene.transform}"
                )
    return True


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
    process_vh: bool = True,
    provenance: Optional[Union[SourceProvenance, Any]] = None,
    source_stac_item_id: Optional[str] = None,
    source_product_id: Optional[str] = None,
    source_archive_sha256: Optional[str] = None,
    source_archive_path: Optional[str] = None,
) -> Tuple[PreprocessedSceneResult, CalibratedScene, np.ndarray, np.ndarray]:
    """Execute complete VARUNA QUICKLOOK SAR preprocessing pipeline:

    RAW SCENE -> CALIBRATE_SAFE (for SAFE products) / READ -> LEE FILTER -> DECIBEL (dB) -> GEOTIFF EXPORT
    Target directory: data/cases/<case_id>/observations/<observation_id>/processed/
    """
    start_clock = time.time()
    started_at = datetime.now(timezone.utc).isoformat()
    p_in = Path(source_input_path)

    # Resolve explicit source provenance
    final_stac_item_id = source_stac_item_id
    final_product_id = source_product_id
    final_archive_sha256 = source_archive_sha256
    final_archive_path = source_archive_path

    if provenance is not None:
        if hasattr(provenance, "source_stac_item_id") and getattr(provenance, "source_stac_item_id"):
            final_stac_item_id = final_stac_item_id or getattr(provenance, "source_stac_item_id")
        elif hasattr(provenance, "stac_item_id") and getattr(provenance, "stac_item_id"):
            final_stac_item_id = final_stac_item_id or getattr(provenance, "stac_item_id")

        if hasattr(provenance, "source_product_id") and getattr(provenance, "source_product_id"):
            final_product_id = final_product_id or getattr(provenance, "source_product_id")
        elif hasattr(provenance, "product_id") and getattr(provenance, "product_id"):
            final_product_id = final_product_id or getattr(provenance, "product_id")

        if hasattr(provenance, "source_archive_sha256") and getattr(provenance, "source_archive_sha256"):
            final_archive_sha256 = final_archive_sha256 or getattr(provenance, "source_archive_sha256")
        elif hasattr(provenance, "sha256") and getattr(provenance, "sha256"):
            final_archive_sha256 = final_archive_sha256 or getattr(provenance, "sha256")

        if hasattr(provenance, "source_archive_path") and getattr(provenance, "source_archive_path"):
            final_archive_path = final_archive_path or getattr(provenance, "source_archive_path")
        elif hasattr(provenance, "archive_path") and getattr(provenance, "archive_path"):
            final_archive_path = final_archive_path or getattr(provenance, "archive_path")

        if isinstance(provenance, dict):
            final_stac_item_id = final_stac_item_id or provenance.get("source_stac_item_id") or provenance.get("stac_item_id")
            final_product_id = final_product_id or provenance.get("source_product_id") or provenance.get("product_id")
            final_archive_sha256 = final_archive_sha256 or provenance.get("source_archive_sha256") or provenance.get("sha256")
            final_archive_path = final_archive_path or provenance.get("source_archive_path") or provenance.get("archive_path")

    if not final_product_id:
        final_product_id = p_in.stem

    # Input hash:
    # Preprocessing cannot recover original archive SHA256 by hashing source_input_path
    # when receiving an extracted SAFE directory. Do not hash extracted directory.
    input_sha256 = ""
    if final_archive_sha256:
        input_sha256 = final_archive_sha256
    elif p_in.is_file():
        h = hashlib.sha256()
        with p_in.open("rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        input_sha256 = h.hexdigest()
        final_archive_sha256 = input_sha256
        if not final_archive_path:
            final_archive_path = str(p_in)

    proc_dir = Path(output_base_dir) / case_id / "observations" / observation_id / "processed"
    proc_dir.mkdir(parents=True, exist_ok=True)

    try:
        # 1. Calibration: for SAFE products, explicitly route to calibrate_safe()
        is_safe_product = (
            (p_in.is_dir() and p_in.suffix == ".SAFE")
            or (p_in.is_dir() and (p_in / "measurement").is_dir())
            or (p_in.is_file() and p_in.name.endswith(".SAFE.zip"))
        )

        if is_safe_product:
            scene = calibrate_safe(source_input_path, polarisation=polarisation)
        else:
            scene = read_sar_raster(source_input_path, polarisation=polarisation)

        print(f"[SAR] processing {scene.polarisation}", flush=True)
        logger.info(f"[SAR] processing {scene.polarisation}")

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
            sigma0_db = np.where(land_mask, db_window[0], sigma0_db)

        # 5. Export preprocessed VV dB GeoTIFF
        out_tif = proc_dir / f"{observation_id}_{scene.polarisation.lower()}_sigma0_db.tif"
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
                TERRAIN_CORRECTION="NONE",
                POLARISATION=scene.polarisation,
                RADIOMETRIC_MODE=scene.radiometric_mode,
                CRS=str(scene.crs),
                TRANSFORM=str(list(scene.transform)[:6]),
                DIMENSIONS=f"{h_dim}x{w_dim}",
                SOURCE_STAC_ITEM_ID=str(final_stac_item_id or ""),
                SOURCE_PRODUCT_ID=str(final_product_id or ""),
                SOURCE_ARCHIVE_SHA256=str(final_archive_sha256 or ""),
                PROCESSING_TIMESTAMP=started_at,
                FILTER_METHOD="LEE_SPECKLE_MMSE",
                FILTER_SIZE=str(filter_size),
                DB_WINDOW=f"{db_window[0]},{db_window[1]}",
            )

        # Output hash
        h_out = hashlib.sha256()
        with out_tif.open("rb") as f:
            while chunk := f.read(65536):
                h_out.update(chunk)
        out_sha256 = h_out.hexdigest()

        # 6. Optional VH processing if requested and available
        vh_tif_path = None
        vh_sha256 = None
        vh_processed = False
        dualpol_aligned = False

        if process_vh and scene.vh_available and is_safe_product:
            try:
                print("[SAR] processing VH", flush=True)
                logger.info("[SAR] processing VH")
                vh_scene = calibrate_safe(source_input_path, polarisation="VH")
                verify_dualpol_alignment(scene, vh_scene)
                dualpol_aligned = True

                vh_filtered = lee_filter(vh_scene.sigma0, size=filter_size)
                vh_db = to_db(vh_filtered)
                if coastlines_path and land_mask is not None:
                    vh_db = np.where(land_mask, db_window[0], vh_db)

                vh_out_tif = proc_dir / f"{observation_id}_vh_sigma0_db.tif"
                with rasterio.open(
                    vh_out_tif,
                    "w",
                    driver="GTiff",
                    height=h_dim,
                    width=w_dim,
                    count=1,
                    dtype=rasterio.float32,
                    crs=vh_scene.crs,
                    transform=vh_scene.transform,
                    compress="deflate",
                ) as vh_dst:
                    vh_dst.write(vh_db.astype(np.float32), 1)
                    vh_dst.update_tags(
                        PIPELINE="VARUNA QUICKLOOK SAR ANALYSIS",
                        TERRAIN_CORRECTION="NONE",
                        POLARISATION="VH",
                        RADIOMETRIC_MODE=vh_scene.radiometric_mode,
                        CRS=str(vh_scene.crs),
                        TRANSFORM=str(list(vh_scene.transform)[:6]),
                        DIMENSIONS=f"{h_dim}x{w_dim}",
                        SOURCE_STAC_ITEM_ID=str(final_stac_item_id or ""),
                        SOURCE_PRODUCT_ID=str(final_product_id or ""),
                        SOURCE_ARCHIVE_SHA256=str(final_archive_sha256 or ""),
                        PROCESSING_TIMESTAMP=started_at,
                        FILTER_METHOD="LEE_SPECKLE_MMSE",
                        FILTER_SIZE=str(filter_size),
                        DB_WINDOW=f"{db_window[0]},{db_window[1]}",
                    )
                h_vh = hashlib.sha256()
                with vh_out_tif.open("rb") as f:
                    while chunk := f.read(65536):
                        h_vh.update(chunk)
                vh_sha256 = h_vh.hexdigest()
                vh_tif_path = str(vh_out_tif)
                vh_processed = True
            except Exception as vh_exc:
                logger.warning(f"VH channel processing skipped due to error: {vh_exc}")

        print("[SAR] preprocessing complete", flush=True)
        logger.info("[SAR] preprocessing complete")

        duration = round(time.time() - start_clock, 2)
        completed_at = datetime.now(timezone.utc).isoformat()

        result = PreprocessedSceneResult(
            case_id=case_id,
            observation_id=observation_id,
            source_input_path=str(source_input_path),
            input_sha256=input_sha256,
            product_id=final_product_id,
            source_stac_item_id=final_stac_item_id,
            source_product_id=final_product_id,
            source_archive_sha256=final_archive_sha256,
            source_archive_path=final_archive_path,
            raster_dimensions=(h_dim, w_dim),
            crs=str(scene.crs),
            polarization=scene.polarisation,
            radiometric_mode=scene.radiometric_mode,
            filter_size=filter_size,
            vv_processed=True,
            vh_available=scene.vh_available,
            vh_processed=vh_processed,
            processed_db_geotiff_path=str(out_tif),
            vh_processed_db_geotiff_path=vh_tif_path,
            output_sha256=out_sha256,
            vh_output_sha256=vh_sha256,
            dualpol_aligned=dualpol_aligned,
            processing_duration_seconds=duration,
            started_at=started_at,
            completed_at=completed_at,
            status="SUCCESS",
        )
        return result, scene, filtered_sigma0, sigma0_db

    except Exception as exc:
        duration = round(time.time() - start_clock, 2)
        completed_at = datetime.now(timezone.utc).isoformat()
        logger.error(f"Quicklook preprocessing failed: {exc}", exc_info=True)
        result = PreprocessedSceneResult(
            case_id=case_id,
            observation_id=observation_id,
            source_input_path=str(source_input_path),
            input_sha256=input_sha256,
            product_id=final_product_id,
            source_stac_item_id=final_stac_item_id,
            source_product_id=final_product_id,
            source_archive_sha256=final_archive_sha256,
            source_archive_path=final_archive_path,
            raster_dimensions=(0, 0),
            crs="",
            polarization=polarisation.upper(),
            radiometric_mode=RADIOMETRIC_MODE_UNKNOWN,
            filter_size=filter_size,
            vv_processed=False,
            vh_available=False,
            vh_processed=False,
            processed_db_geotiff_path="",
            output_sha256="",
            processing_duration_seconds=duration,
            started_at=started_at,
            completed_at=completed_at,
            status="FAILED",
            error_message=str(exc),
        )
        raise exc

