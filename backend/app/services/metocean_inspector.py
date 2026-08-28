from __future__ import annotations
import csv
import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import netCDF4 as nc
import numpy as np
import pyproj
import rasterio
from backend.app.schemas import MetOceanMetadata


def normalize_longitude(lon: float) -> float:
    """Normalizes longitude from 0..360 convention to -180..180 convention."""
    norm = ((lon + 180.0) % 360.0) - 180.0
    # Handle exact 180.0 edge case
    if norm == -180.0 and lon > 0:
        return 180.0
    return round(float(norm), 6)


def normalize_longitude_range(lons: np.ndarray | List[float]) -> Tuple[float, float]:
    """Computes normalized [lon_min, lon_max] in -180..180 space."""
    norm_lons = [normalize_longitude(float(x)) for x in lons]
    return float(min(norm_lons)), float(max(norm_lons))


def to_utc_iso(dt_obj: Any) -> Optional[str]:
    """Converts various date/time formats into UTC ISO-8601 string ending in Z."""
    if dt_obj is None:
        return None
    try:
        if isinstance(dt_obj, str):
            dt_str = dt_obj.strip()
            if dt_str.endswith("Z"):
                dt_str = dt_str[:-1] + "+00:00"
            dt = datetime.datetime.fromisoformat(dt_str)
        elif hasattr(dt_obj, "strftime"): # cftime or datetime object
            dt = datetime.datetime(
                dt_obj.year, dt_obj.month, dt_obj.day,
                getattr(dt_obj, "hour", 0), getattr(dt_obj, "minute", 0), getattr(dt_obj, "second", 0)
            )
        elif isinstance(dt_obj, (np.datetime64, int, float)):
            dt = datetime.datetime.fromtimestamp(dt_obj, tz=datetime.timezone.utc)
        else:
            return None

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        else:
            dt = dt.astimezone(datetime.timezone.utc)

        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return None


def inspect_metocean_file(
    file_path: str | Path,
    declared_provider: Optional[str] = None,
    declared_dataset_name: Optional[str] = None,
    declared_start_time: Optional[str] = None,
    declared_end_time: Optional[str] = None,
) -> MetOceanMetadata:
    """
    Reads environmental files (.nc, .tif, .csv) and extracts authoritative metadata.
    """
    fpath = Path(file_path)
    if not fpath.exists():
        raise FileNotFoundError(f"Met-ocean file not found: {fpath}")

    ext = fpath.suffix.lower()

    if ext in [".nc", ".nc4"]:
        return _inspect_netcdf(fpath, declared_provider, declared_dataset_name, declared_start_time, declared_end_time)
    elif ext in [".tif", ".tiff"]:
        return _inspect_geotiff(fpath, declared_provider, declared_dataset_name)
    elif ext == ".csv":
        return _inspect_csv(fpath, declared_provider, declared_dataset_name, declared_start_time, declared_end_time)
    else:
        # Generic fallback for unknown format
        return MetOceanMetadata(
            provider=declared_provider,
            dataset_name=declared_dataset_name or fpath.name,
            warnings=[f"Unsupported file format '{ext}' for automatic metadata extraction."],
        )


def _inspect_netcdf(
    fpath: Path,
    provider: Optional[str],
    dataset_name: Optional[str],
    declared_start: Optional[str],
    declared_end: Optional[str],
) -> MetOceanMetadata:
    detected_vars: List[str] = []
    detected_comps: Dict[str, str] = {}
    units: Dict[str, str] = {}
    warnings: List[str] = []

    lat_min, lat_max = None, None
    lon_min, lon_max = None, None
    time_start, time_end = None, None
    time_res_hours = None
    spatial_res_deg = None
    depth_m = None
    crs_str = "EPSG:4326"

    with nc.Dataset(str(fpath), "r") as ds:
        detected_vars = list(ds.variables.keys())

        # Inspect units & components
        for var_name, var_obj in ds.variables.items():
            u = getattr(var_obj, "units", None)
            if u:
                units[var_name] = str(u)

            lname = var_name.lower()
            std_name = str(getattr(var_obj, "standard_name", "")).lower()

            if lname in ["u_current", "uo", "ucurrent", "u_curr"] or "sea_water_x_velocity" in std_name:
                detected_comps["u_current"] = var_name
            elif lname in ["v_current", "vo", "vcurrent", "v_curr"] or "sea_water_y_velocity" in std_name:
                detected_comps["v_current"] = var_name
            elif lname in ["u_wind", "u10", "u10m", "wind_u"] or "eastward_wind" in std_name:
                detected_comps["u_wind"] = var_name
            elif lname in ["v_wind", "v10", "v10m", "wind_v"] or "northward_wind" in std_name:
                detected_comps["v_wind"] = var_name
            elif lname in ["swh", "hs", "significant_wave_height"] or "significant_height_of_wind_and_swell_waves" in std_name:
                detected_comps["swh"] = var_name
            elif lname in ["mwd", "dir", "mean_wave_direction"] or "mean_wave_direction" in std_name:
                detected_comps["mwd"] = var_name

        # Coordinates extraction
        lat_var = None
        for name in ["latitude", "lat", "y"]:
            if name in ds.variables:
                lat_var = ds.variables[name]
                break

        if lat_var is not None:
            lats = np.array(lat_var[:]).flatten()
            lat_min, lat_max = float(lats.min()), float(lats.max())
            if len(lats) > 1:
                spatial_res_deg = round(float(abs(lats[1] - lats[0])), 4)

        lon_var = None
        for name in ["longitude", "lon", "x"]:
            if name in ds.variables:
                lon_var = ds.variables[name]
                break

        if lon_var is not None:
            lons = np.array(lon_var[:]).flatten()
            lon_min, lon_max = normalize_longitude_range(lons)

        # Time extraction
        time_var = None
        for name in ["time", "t", "time_counter"]:
            if name in ds.variables:
                time_var = ds.variables[name]
                break

        if time_var is not None:
            time_vals = time_var[:]
            time_units = getattr(time_var, "units", None)

            if time_units and len(time_vals) > 0:
                try:
                    dates = nc.num2date(time_vals, time_units, calendar=getattr(time_var, "calendar", "standard"))
                    if not isinstance(dates, (list, np.ndarray)):
                        dates = [dates]
                    time_start = to_utc_iso(dates[0])
                    time_end = to_utc_iso(dates[-1])

                    if len(dates) > 1:
                        # Compute resolution in hours
                        dt1 = datetime.datetime.fromisoformat(time_start.replace("Z", "+00:00"))
                        dt2 = datetime.datetime.fromisoformat(to_utc_iso(dates[1]).replace("Z", "+00:00"))
                        time_res_hours = round(abs((dt2 - dt1).total_seconds()) / 3600.0, 2)
                except Exception as err:
                    warnings.append(f"Unable to parse NetCDF time units '{time_units}': {err}")

        # Depth extraction
        for dname in ["depth", "z", "level"]:
            if dname in ds.variables:
                dvals = np.array(ds.variables[dname][:]).flatten()
                if len(dvals) > 0:
                    depth_m = float(dvals[0])
                break

    # Conflict Audit
    if declared_start and time_start and declared_start[:10] != time_start[:10]:
        warnings.append(f"Declared start time ({declared_start}) conflicts with detected NetCDF time ({time_start}).")

    return MetOceanMetadata(
        provider=provider,
        dataset_name=dataset_name or fpath.name,
        detected_variables=detected_vars,
        detected_components=detected_comps,
        units=units,
        lat_min=lat_min,
        lat_max=lat_max,
        lon_min=lon_min,
        lon_max=lon_max,
        time_start_utc=time_start,
        time_end_utc=time_end,
        time_resolution_hours=time_res_hours,
        spatial_resolution_deg=spatial_res_deg,
        depth_m=depth_m,
        crs=crs_str,
        warnings=warnings,
    )


def _inspect_geotiff(fpath: Path, provider: Optional[str], dataset_name: Optional[str]) -> MetOceanMetadata:
    warnings: List[str] = []
    lat_min, lat_max, lon_min, lon_max = None, None, None, None
    crs_str = None

    try:
        with rasterio.open(str(fpath)) as src:
            crs_str = str(src.crs) if src.crs else "EPSG:4326"
            bounds = src.bounds
            
            if src.crs and src.crs.is_projected:
                transformer = pyproj.Transformer.from_crs(src.crs, "EPSG:4326", always_xy=True)
                lon1, lat1 = transformer.transform(bounds.left, bounds.bottom)
                lon2, lat2 = transformer.transform(bounds.right, bounds.top)
                lat_min, lat_max = min(lat1, lat2), max(lat1, lat2)
                lon_min, lon_max = normalize_longitude_range([lon1, lon2])
            else:
                lat_min, lat_max = bounds.bottom, bounds.top
                lon_min, lon_max = normalize_longitude_range([bounds.left, bounds.right])
    except Exception as err:
        warnings.append(f"Error reading GeoTIFF metadata: {err}")

    return MetOceanMetadata(
        provider=provider,
        dataset_name=dataset_name or fpath.name,
        detected_variables=["raster_band"],
        lat_min=lat_min,
        lat_max=lat_max,
        lon_min=lon_min,
        lon_max=lon_max,
        crs=crs_str,
        warnings=warnings,
    )


def _inspect_csv(
    fpath: Path,
    provider: Optional[str],
    dataset_name: Optional[str],
    declared_start: Optional[str],
    declared_end: Optional[str],
) -> MetOceanMetadata:
    detected_vars: List[str] = []
    detected_comps: Dict[str, str] = {}
    warnings: List[str] = []

    lats: List[float] = []
    lons: List[float] = []
    times: List[str] = []

    with open(fpath, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames:
            detected_vars = list(reader.fieldnames)
            for fname in reader.fieldnames:
                fl = fname.lower()
                if fl in ["u_current", "u_curr", "uo"]:
                    detected_comps["u_current"] = fname
                elif fl in ["v_current", "v_curr", "vo"]:
                    detected_comps["v_current"] = fname
                elif fl in ["u_wind", "u10", "wind_u"]:
                    detected_comps["u_wind"] = fname
                elif fl in ["v_wind", "v10", "wind_v"]:
                    detected_comps["v_wind"] = fname
                elif fl in ["swh", "hs"]:
                    detected_comps["swh"] = fname

        for row in reader:
            for k_lat in ["lat", "latitude", "lat_deg"]:
                if k_lat in row and row[k_lat]:
                    try:
                        lats.append(float(row[k_lat]))
                        break
                    except ValueError:
                        pass

            for k_lon in ["lon", "longitude", "lon_deg"]:
                if k_lon in row and row[k_lon]:
                    try:
                        lons.append(float(row[k_lon]))
                        break
                    except ValueError:
                        pass

            for k_t in ["time", "timestamp", "datetime", "time_utc"]:
                if k_t in row and row[k_t]:
                    t_iso = to_utc_iso(row[k_t])
                    if t_iso:
                        times.append(t_iso)
                        break

    lat_min = float(min(lats)) if lats else None
    lat_max = float(max(lats)) if lats else None
    lon_min, lon_max = normalize_longitude_range(lons) if lons else (None, None)

    times_sorted = sorted(times) if times else []
    time_start = times_sorted[0] if times_sorted else declared_start
    time_end = times_sorted[-1] if times_sorted else declared_end

    return MetOceanMetadata(
        provider=provider,
        dataset_name=dataset_name or fpath.name,
        detected_variables=detected_vars,
        detected_components=detected_comps,
        lat_min=lat_min,
        lat_max=lat_max,
        lon_min=lon_min,
        lon_max=lon_max,
        time_start_utc=time_start,
        time_end_utc=time_end,
        crs="EPSG:4326",
        warnings=warnings,
    )
