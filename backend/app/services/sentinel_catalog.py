"""
Copernicus Sentinel-1 Catalogue Service for VARUNA.

Integrates with the Copernicus Data Space Ecosystem (CDSE) STAC API to search
and normalize genuine Sentinel-1 GRD acquisitions intersecting a case AOI and
time window.

Catalogue coverage approximation is calculated via Shapely polygon intersection.
This is a footprint intersection metric for catalogue discovery and ranking,
not a physical curved-Earth geodetic area measurement.
"""

from __future__ import annotations

import datetime
import logging
import os
import uuid
from typing import Any, Dict, List, Optional, Tuple

from shapely.geometry import shape
from shapely.validation import make_valid
import pystac
from pystac_client import Client
from pystac_client.exceptions import APIError

logger = logging.getLogger(__name__)

DEFAULT_CDSE_STAC_URL = "https://stac.dataspace.copernicus.eu/v1/"
COLLECTION_SENTINEL1_GRD = "sentinel-1-grd"


class SentinelCatalogError(Exception):
    """Base exception for satellite catalogue operations."""
    pass


class InvalidAoiError(SentinelCatalogError):
    """Raised when the provided AOI GeoJSON is malformed or invalid."""
    pass


class InvalidTimeRangeError(SentinelCatalogError):
    """Raised when the time query window is invalid."""
    pass


class CopernicusUnavailableError(SentinelCatalogError):
    """Raised when Copernicus CDSE STAC endpoint is unreachable or errors."""
    pass


class CopernicusTimeoutError(CopernicusUnavailableError):
    """Raised when Copernicus CDSE request times out."""
    pass


class CopernicusRateLimitError(CopernicusUnavailableError):
    """Raised when Copernicus CDSE returns 429 rate limit."""
    pass


class ItemNotFoundError(SentinelCatalogError):
    """Raised when a specific STAC item ID cannot be found."""
    pass


def get_cdse_stac_url() -> str:
    """Return the configured Copernicus STAC URL."""
    return os.environ.get("VARUNA_CDSE_STAC_URL", DEFAULT_CDSE_STAC_URL).strip()


def validate_aoi_geojson(aoi_geojson: Any) -> Dict[str, Any]:
    """
    Validate that aoi_geojson is a valid GeoJSON geometry (Polygon or MultiPolygon).
    Returns normalized GeoJSON geometry dict.
    """
    if not aoi_geojson:
        raise InvalidAoiError("AOI GeoJSON is required.")

    if not isinstance(aoi_geojson, dict):
        raise InvalidAoiError("AOI GeoJSON must be a dictionary.")

    # Support Feature or raw Geometry
    geom_dict = aoi_geojson
    if aoi_geojson.get("type") == "Feature":
        geom_dict = aoi_geojson.get("geometry")
        if not geom_dict:
            raise InvalidAoiError("Feature missing 'geometry' property.")

    geom_type = geom_dict.get("type")
    if geom_type not in ("Polygon", "MultiPolygon"):
        raise InvalidAoiError(
            f"AOI geometry must be 'Polygon' or 'MultiPolygon', got '{geom_type}'."
        )

    coords = geom_dict.get("coordinates")
    if not coords or not isinstance(coords, list):
        raise InvalidAoiError("AOI geometry missing coordinates.")

    try:
        geom_shape = shape(geom_dict)
        if geom_shape.is_empty:
            raise InvalidAoiError("AOI geometry is empty.")
        if not geom_shape.is_valid:
            geom_shape = make_valid(geom_shape)
            if geom_shape.is_empty:
                raise InvalidAoiError("AOI geometry could not be repaired into valid polygon.")
    except Exception as e:
        raise InvalidAoiError(f"Failed to parse AOI geometry: {str(e)}") from e

    # Bounds sanity check (WGS84)
    minx, miny, maxx, maxy = geom_shape.bounds
    if not (-180.0 <= minx <= 180.0 and -180.0 <= maxx <= 180.0 and
            -90.0 <= miny <= 90.0 and -90.0 <= maxy <= 90.0):
        raise InvalidAoiError("AOI coordinates outside valid WGS84 range [-180..180, -90..90].")

    return geom_dict


def validate_time_range(start_datetime: str, end_datetime: str) -> Tuple[str, str]:
    """
    Validate and normalize ISO-8601 UTC date strings.
    Returns (start_iso_utc, end_iso_utc).
    """
    if not start_datetime or not end_datetime:
        raise InvalidTimeRangeError("Both start_datetime and end_datetime are required.")

    def _parse_iso(val: str, label: str) -> datetime.datetime:
        cleaned = val.strip().replace(" ", "T")
        try:
            dt = datetime.datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.timezone.utc)
            else:
                dt = dt.astimezone(datetime.timezone.utc)
            return dt
        except Exception as e:
            raise InvalidTimeRangeError(
                f"Invalid ISO-8601 date string for {label}: '{val}' ({str(e)})"
            ) from e

    dt_start = _parse_iso(start_datetime, "start_datetime")
    dt_end = _parse_iso(end_datetime, "end_datetime")

    if dt_start > dt_end:
        raise InvalidTimeRangeError(
            f"start_datetime ({start_datetime}) must be earlier than or equal to end_datetime ({end_datetime})."
        )

    # Format standard ISO-8601 UTC string ending in 'Z'
    s_iso = dt_start.strftime("%Y-%m-%dT%H:%M:%SZ")
    e_iso = dt_end.strftime("%Y-%m-%dT%H:%M:%SZ")
    return s_iso, e_iso


def calculate_aoi_coverage(
    aoi_geojson: Dict[str, Any],
    footprint_geojson: Dict[str, Any]
) -> Tuple[float, float]:
    """
    Calculate catalogue footprint intersection coverage between Case AOI and STAC item.

    Note: This computes planar 2D polygon intersection area ratio in WGS84 coordinates.
    It serves as a catalogue-ranking and discovery metric, not a physical curved-Earth
    geodetic area measurement.

    Returns:
        (coverage_fraction, coverage_percent)
        e.g. (0.8523, 85.2)
    """
    if not aoi_geojson or not footprint_geojson:
        return 0.0, 0.0

    try:
        s_aoi = shape(aoi_geojson)
        if not s_aoi.is_valid:
            s_aoi = make_valid(s_aoi)

        s_fp = shape(footprint_geojson)
        if not s_fp.is_valid:
            s_fp = make_valid(s_fp)

        if s_aoi.is_empty or s_fp.is_empty or s_aoi.area <= 0:
            return 0.0, 0.0

        intersection = s_aoi.intersection(s_fp)
        if intersection.is_empty:
            return 0.0, 0.0

        fraction = float(intersection.area / s_aoi.area)
        fraction = max(0.0, min(1.0, fraction))
        percent = round(fraction * 100.0, 1)
        fraction = round(fraction, 4)
        return fraction, percent
    except Exception as e:
        logger.warning(f"Error calculating AOI coverage: {e}")
        return 0.0, 0.0


def normalize_stac_item(
    item: Any,
    aoi_geojson: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Normalize a PySTAC Item or dict-like STAC record into the VARUNA SatelliteObservation schema.
    Strictly avoids inventing fake values: missing properties remain null.
    """
    if isinstance(item, pystac.Item):
        item_id = item.id
        geometry = item.geometry
        bbox = item.bbox
        properties = dict(item.properties)
        item_datetime = item.datetime.isoformat() if item.datetime else properties.get("datetime")
        assets_dict = {}
        for k, v in item.assets.items():
            assets_dict[k] = {
                "href": v.href,
                "title": v.title,
                "type": v.media_type,
                "roles": v.roles,
            }
    elif isinstance(item, dict):
        item_id = item.get("id")
        geometry = item.get("geometry")
        bbox = item.get("bbox")
        properties = dict(item.get("properties") or {})
        item_datetime = properties.get("datetime")
        raw_assets = item.get("assets") or {}
        assets_dict = {}
        for k, v in raw_assets.items():
            if isinstance(v, dict):
                assets_dict[k] = {
                    "href": v.get("href"),
                    "title": v.get("title"),
                    "type": v.get("type"),
                    "roles": v.get("roles"),
                }
            else:
                assets_dict[k] = {"href": str(v)}
    else:
        raise ValueError(f"Unsupported item type for normalization: {type(item)}")

    # Extract platform
    platform = properties.get("platform")
    if platform and isinstance(platform, str):
        # Format cleanly if sentinel-1a -> Sentinel-1A
        if platform.lower() == "sentinel-1a":
            platform = "Sentinel-1A"
        elif platform.lower() == "sentinel-1b":
            platform = "Sentinel-1B"
        elif platform.lower() == "sentinel-1c":
            platform = "Sentinel-1C"

    # Constellation
    constellation = properties.get("constellation")

    # Timestamps
    start_dt = properties.get("start_datetime") or item_datetime
    end_dt = properties.get("end_datetime") or item_datetime

    # Instrument mode
    instrument_mode = properties.get("sar:instrument_mode") or properties.get("instrumentMode")

    # Polarizations
    polarizations = properties.get("sar:polarizations")
    if polarizations is None:
        polarizations = properties.get("polarization")
    if isinstance(polarizations, str):
        polarizations = [polarizations]
    elif not isinstance(polarizations, list):
        polarizations = []

    # Orbit
    orbit_state = properties.get("sat:orbit_state") or properties.get("orbitDirection")
    if orbit_state and isinstance(orbit_state, str):
        orbit_state = orbit_state.lower()

    relative_orbit = properties.get("sat:relative_orbit") or properties.get("relativeOrbitNumber")
    if relative_orbit is not None:
        try:
            relative_orbit = int(relative_orbit)
        except (ValueError, TypeError):
            relative_orbit = None

    absolute_orbit = properties.get("sat:absolute_orbit") or properties.get("orbitNumber")
    if absolute_orbit is not None:
        try:
            absolute_orbit = int(absolute_orbit)
        except (ValueError, TypeError):
            absolute_orbit = None

    # Product type
    product_type = properties.get("product:type") or properties.get("productType")

    # Thumbnail and metadata URLs from genuine assets
    thumbnail_url = None
    if "thumbnail" in assets_dict:
        thumbnail_url = assets_dict["thumbnail"].get("href")
    elif "quicklook" in assets_dict:
        thumbnail_url = assets_dict["quicklook"].get("href")

    metadata_url = None
    if "safe_manifest" in assets_dict:
        metadata_url = assets_dict["safe_manifest"].get("href")
    elif "Product" in assets_dict:
        metadata_url = assets_dict["Product"].get("href")

    # Calculate coverage if AOI is provided
    cov_fraction, cov_percent = 0.0, 0.0
    if aoi_geojson and geometry:
        cov_fraction, cov_percent = calculate_aoi_coverage(aoi_geojson, geometry)

    return {
        "observation_id": f"obs-{uuid.uuid4().hex[:12]}",
        "provider": "Copernicus Data Space Ecosystem",
        "collection": COLLECTION_SENTINEL1_GRD,
        "stac_item_id": item_id,
        "platform": platform,
        "constellation": constellation,
        "datetime": item_datetime,
        "start_datetime": start_dt,
        "end_datetime": end_dt,
        "instrument_mode": instrument_mode,
        "polarizations": polarizations,
        "orbit_state": orbit_state,
        "relative_orbit": relative_orbit,
        "absolute_orbit": absolute_orbit,
        "product_type": product_type,
        "geometry": geometry,
        "bbox": bbox,
        "assets": assets_dict,
        "thumbnail_url": thumbnail_url,
        "metadata_url": metadata_url,
        "coverage_fraction": cov_fraction,
        "coverage_percent": cov_percent,
        "attached_at": None,
        "raw_properties": properties,
    }


def search_sentinel1_grd(
    aoi_geojson: Dict[str, Any],
    start_datetime: str,
    end_datetime: str,
    limit: int = 20,
    instrument_mode: Optional[str] = "IW",
    stac_url: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Search genuine Sentinel-1 GRD acquisitions from Copernicus Data Space Ecosystem STAC.

    Args:
        aoi_geojson: GeoJSON geometry (Polygon or MultiPolygon) defining the Case AOI.
        start_datetime: Start of observation time window (ISO-8601 UTC).
        end_datetime: End of observation time window (ISO-8601 UTC).
        limit: Maximum number of acquisitions to return (1..100).
        instrument_mode: Filter by instrument mode, default 'IW'.
        stac_url: Optional override for CDSE STAC URL.

    Returns:
        List of normalized SatelliteObservation dicts sorted by coverage_percent desc, datetime desc.
    """
    valid_aoi = validate_aoi_geojson(aoi_geojson)
    s_iso, e_iso = validate_time_range(start_datetime, end_datetime)
    time_window = f"{s_iso}/{e_iso}"
    endpoint = (stac_url or get_cdse_stac_url()).rstrip("/") + "/"

    limit = max(1, min(100, int(limit)))

    logger.info(
        f"Searching CDSE STAC [{endpoint}], collection={COLLECTION_SENTINEL1_GRD}, "
        f"time={time_window}, mode={instrument_mode}, limit={limit}"
    )

    try:
        client = Client.open(endpoint)
        query_filter: Dict[str, Any] = {}
        if instrument_mode:
            query_filter["sar:instrument_mode"] = {"eq": instrument_mode}

        search_params: Dict[str, Any] = {
            "collections": [COLLECTION_SENTINEL1_GRD],
            "intersects": valid_aoi,
            "datetime": time_window,
            "limit": limit,
        }
        if query_filter:
            search_params["query"] = query_filter

        item_search = client.search(**search_params)
        raw_items = list(item_search.items())
    except APIError as ae:
        status_code = getattr(ae, "status_code", None)
        msg = str(ae)
        logger.error(f"CDSE STAC API Error (status {status_code}): {msg}")
        if status_code == 429 or "rate limit" in msg.lower():
            raise CopernicusRateLimitError(f"CDSE rate limited: {msg}") from ae
        raise CopernicusUnavailableError(f"COPERNICUS CATALOGUE TEMPORARILY UNAVAILABLE: {msg}") from ae
    except TimeoutError as te:
        logger.error(f"CDSE STAC request timed out: {te}")
        raise CopernicusTimeoutError(f"CDSE STAC request timed out: {te}") from te
    except Exception as e:
        err_msg = str(e)
        logger.error(f"Failed to query Copernicus STAC endpoint: {err_msg}")
        if "timeout" in err_msg.lower():
            raise CopernicusTimeoutError(f"CDSE STAC request timed out: {err_msg}") from e
        if "429" in err_msg or "rate limit" in err_msg.lower():
            raise CopernicusRateLimitError(f"CDSE rate limited: {err_msg}") from e
        raise CopernicusUnavailableError(
            f"COPERNICUS CATALOGUE TEMPORARILY UNAVAILABLE: {err_msg}"
        ) from e

    results: List[Dict[str, Any]] = []
    for item in raw_items:
        # Client-side instrument mode filter safeguard
        if instrument_mode:
            item_mode = (
                item.properties.get("sar:instrument_mode")
                or item.properties.get("instrumentMode")
            )
            if item_mode and item_mode.upper() != instrument_mode.upper():
                continue

        normalized = normalize_stac_item(item, aoi_geojson=valid_aoi)
        results.append(normalized)

    # Sort deterministically: highest AOI coverage first, then newest datetime
    results.sort(
        key=lambda x: (
            x.get("coverage_percent") or 0.0,
            x.get("datetime") or ""
        ),
        reverse=True
    )

    return results


def get_sentinel1_item_by_id(
    stac_item_id: str,
    aoi_geojson: Optional[Dict[str, Any]] = None,
    stac_url: Optional[str] = None
) -> Dict[str, Any]:
    """
    Retrieve and verify a specific Sentinel-1 GRD STAC item from CDSE.
    Ensures backend does not trust arbitrary untrusted metadata.
    """
    if not stac_item_id or not isinstance(stac_item_id, str):
        raise ItemNotFoundError("A valid stac_item_id string is required.")

    clean_id = stac_item_id.strip()
    endpoint = (stac_url or get_cdse_stac_url()).rstrip("/") + "/"

    # CDSE sentinel-1-grd items end with _COG
    candidate_ids = [clean_id]
    if not clean_id.endswith("_COG"):
        candidate_ids.append(f"{clean_id}_COG")

    try:
        client = Client.open(endpoint)
        item = None
        for cid in candidate_ids:
            try:
                search = client.search(collections=[COLLECTION_SENTINEL1_GRD], ids=[cid])
                items = list(search.items())
                if items:
                    item = items[0]
                    break
            except Exception as e:
                logger.debug(f"Search for id {cid} error: {e}")
                continue

        if not item:
            raise ItemNotFoundError(
                f"STAC item '{clean_id}' was not found in CDSE collection '{COLLECTION_SENTINEL1_GRD}'."
            )

        valid_aoi = None
        if aoi_geojson:
            try:
                valid_aoi = validate_aoi_geojson(aoi_geojson)
            except Exception:
                valid_aoi = None

        return normalize_stac_item(item, aoi_geojson=valid_aoi)

    except ItemNotFoundError:
        raise
    except APIError as ae:
        status_code = getattr(ae, "status_code", None)
        msg = str(ae)
        if status_code == 429 or "rate limit" in msg.lower():
            raise CopernicusRateLimitError(f"CDSE rate limited: {msg}") from ae
        raise CopernicusUnavailableError(f"COPERNICUS CATALOGUE TEMPORARILY UNAVAILABLE: {msg}") from ae
    except Exception as e:
        err_msg = str(e)
        if "timeout" in err_msg.lower():
            raise CopernicusTimeoutError(f"CDSE STAC request timed out: {err_msg}") from e
        raise CopernicusUnavailableError(
            f"COPERNICUS CATALOGUE TEMPORARILY UNAVAILABLE: {err_msg}"
        ) from e
