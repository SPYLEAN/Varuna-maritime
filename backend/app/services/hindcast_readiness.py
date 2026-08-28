from __future__ import annotations
import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from backend.app.schemas import Case, EvidenceType, StatusEnum
from backend.app.services.metocean_inspector import inspect_metocean_file, normalize_longitude, to_utc_iso


def evaluate_hindcast_readiness(
    case_manifest: Dict[str, Any],
    hindcast_hours: float = 12.0,
    require_waves: bool = False,
    spill_geometry_analysis_id: Optional[str] = None,
) -> Tuple[Dict[str, Any], StatusEnum, List[str]]:
    """
    Evaluates whether a case contains sufficient georeferenced spill geometry and
    met-ocean observations covering the spill location and time window [T_obs - H, T_obs].

    Returns:
        (results_summary_dict, status_enum, warnings_list)
    """
    reasons: List[str] = []
    warnings: List[str] = []

    gen_results = case_manifest.get("data_manifest", {}).get("generated_analysis_results", [])
    evidence_items = case_manifest.get("data_manifest", {}).get("evidence", [])

    # 1. Check A: Spill Geometry Prerequisite
    completed_geom_ans = [
        r for r in gen_results
        if r.get("module") == "spill_geometry" and r.get("status") == "completed"
    ]

    if spill_geometry_analysis_id:
        matching_geom = [r for r in completed_geom_ans if r.get("analysis_id") == spill_geometry_analysis_id]
        target_geom_an = matching_geom[0] if matching_geom else None
    else:
        target_geom_an = completed_geom_ans[-1] if completed_geom_ans else None

    if not target_geom_an:
        reasons.append("missing_spill_geometry")
        warnings.append("No completed spill geometry analysis found for this case.")
        return _build_insufficient_result(hindcast_hours, require_waves, reasons, warnings)

    geom_res = target_geom_an.get("result") or {}

    # 2. Check B: Georeferencing Prerequisite
    georeferenced = geom_res.get("georeferenced", False)
    geo_centroid = geom_res.get("geographic_centroid")  # [lat, lon]

    if not georeferenced or not geo_centroid:
        reasons.append("missing_georeferencing")
        warnings.append("Hindcasting requires georeferenced spill geometry.")
        return _build_insufficient_result(hindcast_hours, require_waves, reasons, warnings, georeferenced=False)

    spill_lat, spill_lon = float(geo_centroid[0]), float(geo_centroid[1])

    # 3. Check C: Incident Observation Timestamp Prerequisite
    obs_time_str = case_manifest.get("observation_timestamp")
    if not obs_time_str:
        # Check SAR evidence acquisition timestamp
        sar_evs = [ev for ev in evidence_items if ev.get("evidence_type") == "sar_image"]
        if sar_evs and sar_evs[-1].get("acquisition_timestamp"):
            obs_time_str = sar_evs[-1].get("acquisition_timestamp")

    if not obs_time_str:
        reasons.append("missing_observation_time")
        warnings.append("Incident observation / acquisition timestamp is missing.")
        return _build_insufficient_result(hindcast_hours, require_waves, reasons, warnings, georeferenced=True, geo_centroid=geo_centroid)

    req_end_iso = to_utc_iso(obs_time_str)
    if not req_end_iso:
        reasons.append("invalid_observation_time")
        warnings.append(f"Unable to parse observation timestamp: '{obs_time_str}'")
        return _build_insufficient_result(hindcast_hours, require_waves, reasons, warnings, georeferenced=True, geo_centroid=geo_centroid)

    dt_end = datetime.datetime.fromisoformat(req_end_iso.replace("Z", "+00:00"))
    dt_start = dt_end - datetime.timedelta(hours=hindcast_hours)
    req_start_iso = dt_start.strftime("%Y-%m-%dT%H:%M:%SZ")

    # 4. Check Environmental Evidence Items
    current_evs = [ev for ev in evidence_items if ev.get("evidence_type") in ["ocean_current", "met_ocean"]]
    wind_evs = [ev for ev in evidence_items if ev.get("evidence_type") in ["wind", "met_ocean"]]
    wave_evs = [ev for ev in evidence_items if ev.get("evidence_type") in ["wave", "met_ocean"]]

    # Validate Ocean Current Data
    current_cov = _validate_field_coverage(
        evidence_list=current_evs,
        required_var_keys=["u_current", "v_current"],
        spill_lat=spill_lat,
        spill_lon=spill_lon,
        req_start_dt=dt_start,
        req_end_dt=dt_end,
        missing_reason="missing_current_data",
        spatial_gap_reason="current_spatial_gap",
        temporal_gap_reason="current_temporal_gap",
        field_name="Ocean current",
    )
    if current_cov["reasons"]:
        reasons.extend(current_cov["reasons"])
        warnings.extend(current_cov["warnings"])

    # Validate Wind Data
    wind_cov = _validate_field_coverage(
        evidence_list=wind_evs,
        required_var_keys=["u_wind", "v_wind"],
        spill_lat=spill_lat,
        spill_lon=spill_lon,
        req_start_dt=dt_start,
        req_end_dt=dt_end,
        missing_reason="missing_wind_data",
        spatial_gap_reason="wind_spatial_gap",
        temporal_gap_reason="wind_temporal_gap",
        field_name="Wind",
    )
    if wind_cov["reasons"]:
        reasons.extend(wind_cov["reasons"])
        warnings.extend(wind_cov["warnings"])

    # Validate Wave Data
    wave_cov = _validate_field_coverage(
        evidence_list=wave_evs,
        required_var_keys=["swh"],
        spill_lat=spill_lat,
        spill_lon=spill_lon,
        req_start_dt=dt_start,
        req_end_dt=dt_end,
        missing_reason="missing_wave_data" if require_waves else None,
        spatial_gap_reason="wave_spatial_gap" if require_waves else None,
        temporal_gap_reason="wave_temporal_gap" if require_waves else None,
        field_name="Wave",
    )
    if require_waves and wave_cov["reasons"]:
        reasons.extend(wave_cov["reasons"])
        warnings.extend(wave_cov["warnings"])

    # Final Readiness Determination
    ready = len(reasons) == 0
    status = StatusEnum.COMPLETED if ready else StatusEnum.INSUFFICIENT_DATA

    results_summary = {
        "ready_for_hindcast": ready,
        "reasons": reasons,
        "spill_georeferenced": True,
        "geographic_centroid": [spill_lat, spill_lon],
        "observation_time_utc": req_end_iso,
        "requested_hindcast_hours": hindcast_hours,
        "required_forcing_window": {
            "start_utc": req_start_iso,
            "end_utc": req_end_iso,
        },
        "environmental_coverage": {
            "ocean_current": current_cov["summary"],
            "wind": wind_cov["summary"],
            "wave": wave_cov["summary"],
        },
    }

    return results_summary, status, warnings


def _validate_field_coverage(
    evidence_list: List[Dict[str, Any]],
    required_var_keys: List[str],
    spill_lat: float,
    spill_lon: float,
    req_start_dt: datetime.datetime,
    req_end_dt: datetime.datetime,
    missing_reason: Optional[str],
    spatial_gap_reason: Optional[str],
    temporal_gap_reason: Optional[str],
    field_name: str,
) -> Dict[str, Any]:
    cov_reasons: List[str] = []
    cov_warnings: List[str] = []

    if not evidence_list:
        if missing_reason:
            cov_reasons.append(missing_reason)
            cov_warnings.append(f"{field_name} evidence dataset is missing.")
        return {
            "summary": {
                "present": False,
                "spatial_coverage": False,
                "temporal_coverage": False,
                "available_start_utc": None,
                "available_end_utc": None,
                "required_start_utc": req_start_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "required_end_utc": req_end_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
            "reasons": cov_reasons,
            "warnings": cov_warnings,
        }

    # Inspect evidence files
    spatial_pass = False
    temporal_pass = False
    best_start = None
    best_end = None

    for ev in evidence_list:
        stored_path = ev.get("stored_path")
        if not stored_path or not Path(stored_path).exists():
            continue

        meta = inspect_metocean_file(stored_path, declared_provider=ev.get("source"))

        # Check if contains required variable components
        has_vars = True
        for vk in required_var_keys:
            if vk not in meta.detected_components and vk not in meta.detected_variables:
                # Check for generic component matching
                if not any(vk in var.lower() for var in meta.detected_variables):
                    has_vars = False
                    break

        if not has_vars and field_name != "Wave":
            continue

        # Spatial Coverage Check (with 0.05 deg margin)
        if meta.lat_min is not None and meta.lat_max is not None and meta.lon_min is not None and meta.lon_max is not None:
            if (meta.lat_min - 0.05 <= spill_lat <= meta.lat_max + 0.05) and (meta.lon_min - 0.05 <= spill_lon <= meta.lon_max + 0.05):
                spatial_pass = True

        # Temporal Coverage Check
        if meta.time_start_utc and meta.time_end_utc:
            t_start = datetime.datetime.fromisoformat(meta.time_start_utc.replace("Z", "+00:00"))
            t_end = datetime.datetime.fromisoformat(meta.time_end_utc.replace("Z", "+00:00"))

            if not best_start or t_start < best_start:
                best_start = t_start
            if not best_end or t_end > best_end:
                best_end = t_end

            if (t_start <= req_start_dt + datetime.timedelta(minutes=5)) and (t_end >= req_end_dt - datetime.timedelta(minutes=5)):
                temporal_pass = True

    if evidence_list and not spatial_pass and spatial_gap_reason:
        cov_reasons.append(spatial_gap_reason)
        cov_warnings.append(f"{field_name} data does not spatially cover the spill location ({spill_lat:.4f}, {spill_lon:.4f}).")

    if evidence_list and not temporal_pass and temporal_gap_reason:
        cov_reasons.append(temporal_gap_reason)
        av_start_str = best_start.strftime("%Y-%m-%dT%H:%M:%SZ") if best_start else "N/A"
        av_end_str = best_end.strftime("%Y-%m-%dT%H:%M:%SZ") if best_end else "N/A"
        req_start_str = req_start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        req_end_str = req_end_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        cov_warnings.append(f"{field_name} data temporal gap: dataset [{av_start_str} .. {av_end_str}] does not cover required window [{req_start_str} .. {req_end_str}].")

    return {
        "summary": {
            "present": True,
            "spatial_coverage": spatial_pass,
            "temporal_coverage": temporal_pass,
            "available_start_utc": best_start.strftime("%Y-%m-%dT%H:%M:%SZ") if best_start else None,
            "available_end_utc": best_end.strftime("%Y-%m-%dT%H:%M:%SZ") if best_end else None,
            "required_start_utc": req_start_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "required_end_utc": req_end_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        "reasons": cov_reasons,
        "warnings": cov_warnings,
    }


def _build_insufficient_result(
    hindcast_hours: float,
    require_waves: bool,
    reasons: List[str],
    warnings: List[str],
    georeferenced: bool = False,
    geo_centroid: Optional[List[float]] = None,
) -> Tuple[Dict[str, Any], StatusEnum, List[str]]:
    summary = {
        "ready_for_hindcast": False,
        "reasons": reasons,
        "spill_georeferenced": georeferenced,
        "geographic_centroid": geo_centroid,
        "requested_hindcast_hours": hindcast_hours,
        "required_forcing_window": None,
        "environmental_coverage": {
            "ocean_current": {"present": False, "spatial_coverage": False, "temporal_coverage": False},
            "wind": {"present": False, "spatial_coverage": False, "temporal_coverage": False},
            "wave": {"present": False, "spatial_coverage": False, "temporal_coverage": False},
        },
    }
    return summary, StatusEnum.INSUFFICIENT_DATA, warnings
