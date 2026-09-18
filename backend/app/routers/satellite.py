from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import List

from fastapi import APIRouter, HTTPException, status

from ..schemas import (
    SatelliteAttachRequest,
    SatelliteObservation,
    SatelliteSearchRequest,
    SatelliteSearchResponse,
)
from ..services.sentinel_catalog import (
    CopernicusRateLimitError,
    CopernicusTimeoutError,
    CopernicusUnavailableError,
    InvalidAoiError,
    InvalidTimeRangeError,
    ItemNotFoundError,
    get_sentinel1_item_by_id,
    search_sentinel1_grd,
)
from ..storage import storage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cases/{case_id}/satellite", tags=["Satellite"])


@router.post("/search", response_model=SatelliteSearchResponse)
def search_satellite_observations(
    case_id: str,
    payload: SatelliteSearchRequest,
) -> SatelliteSearchResponse:
    """
    Search Sentinel-1 GRD catalogue items intersecting the case's persisted AOI and time window.
    """
    raw_case = storage.get_case(case_id)
    if not raw_case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"CASE_NOT_FOUND: Case '{case_id}' does not exist.",
        )

    aoi_geojson = raw_case.get("aoi_geojson")
    if not aoi_geojson:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"CASE_HAS_NO_AOI: Case '{case_id}' has no persisted AOI geometry.",
        )

    try:
        results = search_sentinel1_grd(
            aoi_geojson=aoi_geojson,
            start_datetime=payload.start_datetime,
            end_datetime=payload.end_datetime,
            limit=payload.limit,
            instrument_mode=payload.instrument_mode,
        )
    except InvalidAoiError as iae:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"INVALID_AOI: {str(iae)}",
        ) from iae
    except InvalidTimeRangeError as ite:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"INVALID_TIME_RANGE: {str(ite)}",
        ) from ite
    except CopernicusRateLimitError as rle:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"RATE_LIMITED: {str(rle)}",
        ) from rle
    except CopernicusTimeoutError as cte:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"TIMEOUT: {str(cte)}",
        ) from cte
    except CopernicusUnavailableError as cue:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"COPERNICUS CATALOGUE TEMPORARILY UNAVAILABLE: {str(cue)}",
        ) from cue
    except Exception as exc:
        logger.error(f"Unexpected satellite search error: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"MALFORMED_PROVIDER_RESPONSE: {str(exc)}",
        ) from exc

    obs_models = [SatelliteObservation(**item) for item in results]

    return SatelliteSearchResponse(
        case_id=case_id,
        provider="Copernicus Data Space Ecosystem",
        collection="sentinel-1-grd",
        query={
            "start_datetime": payload.start_datetime,
            "end_datetime": payload.end_datetime,
            "limit": payload.limit,
            "instrument_mode": payload.instrument_mode,
            "intersects": aoi_geojson,
        },
        count=len(obs_models),
        results=obs_models,
    )


@router.post("/attach", response_model=SatelliteObservation, status_code=status.HTTP_201_CREATED)
def attach_satellite_observation(
    case_id: str,
    payload: SatelliteAttachRequest,
) -> SatelliteObservation:
    """
    Verify and attach a genuine Sentinel-1 STAC item to the case's data manifest.
    Stores cryptographic and provider provenance.
    """
    raw_case = storage.get_case(case_id)
    if not raw_case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"CASE_NOT_FOUND: Case '{case_id}' does not exist.",
        )

    aoi_geojson = raw_case.get("aoi_geojson")

    try:
        norm_item = get_sentinel1_item_by_id(
            stac_item_id=payload.stac_item_id,
            aoi_geojson=aoi_geojson,
        )
    except ItemNotFoundError as ine:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ITEM_NOT_FOUND: {str(ine)}",
        ) from ine
    except CopernicusRateLimitError as rle:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"RATE_LIMITED: {str(rle)}",
        ) from rle
    except CopernicusTimeoutError as cte:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"TIMEOUT: {str(cte)}",
        ) from cte
    except CopernicusUnavailableError as cue:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"COPERNICUS CATALOGUE TEMPORARILY UNAVAILABLE: {str(cue)}",
        ) from cue
    except Exception as exc:
        logger.error(f"Unexpected satellite attach error: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"MALFORMED_PROVIDER_RESPONSE: {str(exc)}",
        ) from exc

    now_iso = datetime.now(timezone.utc).isoformat()
    norm_item["attached_at"] = now_iso
    norm_item["provenance"] = {
        "provider": "Copernicus Data Space Ecosystem",
        "catalogue": "CDSE STAC",
        "collection": "sentinel-1-grd",
        "retrieved_at": now_iso,
        "query_aoi": aoi_geojson,
        "stac_item_id": norm_item["stac_item_id"],
        "source_url": f"https://stac.dataspace.copernicus.eu/v1/collections/sentinel-1-grd/items/{norm_item['stac_item_id']}",
        "raw_properties": norm_item.get("raw_properties", {}),
    }

    obs_model = SatelliteObservation(**norm_item)
    obs_dict = obs_model.model_dump()

    # Update manifest in raw_case
    manifest = raw_case.setdefault("data_manifest", {})
    sat_obs_list = manifest.setdefault("satellite_observations", [])

    # Replace if same STAC item ID already attached, else append
    existing_idx = next(
        (i for i, o in enumerate(sat_obs_list) if o.get("stac_item_id") == obs_model.stac_item_id),
        None,
    )
    if existing_idx is not None:
        sat_obs_list[existing_idx] = obs_dict
    else:
        sat_obs_list.append(obs_dict)

    # Also keep satellite_imagery list in sync
    sat_img_list = manifest.setdefault("satellite_imagery", [])
    img_idx = next(
        (i for i, o in enumerate(sat_img_list) if isinstance(o, dict) and o.get("stac_item_id") == obs_model.stac_item_id),
        None,
    )
    if img_idx is not None:
        sat_img_list[img_idx] = obs_dict
    else:
        sat_img_list.append(obs_dict)

    # If observation_timestamp was missing on case, populate with satellite datetime
    if not raw_case.get("observation_timestamp") and obs_model.datetime:
        raw_case["observation_timestamp"] = obs_model.datetime

    storage.save_case(raw_case)

    return obs_model


@router.get("", response_model=List[SatelliteObservation])
def get_case_satellite_observations(case_id: str) -> List[SatelliteObservation]:
    """
    Get all attached satellite observations for a case.
    """
    raw_case = storage.get_case(case_id)
    if not raw_case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"CASE_NOT_FOUND: Case '{case_id}' does not exist.",
        )

    observations = (
        raw_case.get("data_manifest", {})
        .get("satellite_observations", [])
    )
    return [SatelliteObservation(**o) for o in observations]
