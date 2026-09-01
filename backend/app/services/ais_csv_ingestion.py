"""
SAMUDRANETRA — MARINECADASTRE AIS CSV INGESTION SERVICE
Ingests, validates, and parses MarineCadastre-compatible standard AIS CSV logs:
MMSI, BaseDateTime, LAT, LON, SOG, COG, Heading, VesselName, IMO, CallSign, VesselType, Status, Length, Width, Draft.
"""

import csv
import os
from typing import Dict, Any, List, Optional
from datetime import datetime

class AisCsvValidationError(Exception):
    pass

REQUIRED_FIELDS = {"mmsi", "lat", "lon"}
SUPPORTED_HEADERS = {
    "mmsi", "basedatetime", "datetime", "timestamp", "lat", "lon", "latitude", "longitude",
    "sog", "cog", "heading", "vesselname", "imo", "callsign", "vesseltype", "status",
    "length", "width", "draft"
}

def parse_marinecadastre_ais_csv(file_path: str) -> Dict[str, Any]:
    """
    Parses and validates MarineCadastre-compatible AIS CSV log file.
    Returns structured AIS data inventory and vessel track points.
    """
    if not os.path.exists(file_path):
        raise AisCsvValidationError(f"File not found: {file_path}")

    filename = os.path.basename(file_path)
    records: List[Dict[str, Any]] = []
    vessel_map: Dict[int, List[Dict[str, Any]]] = {}

    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise AisCsvValidationError("CSV file is empty or missing header row.")

        # Normalize header column names to lowercase
        header_map = {col.strip().lower(): col for col in reader.fieldnames}

        # Check required fields
        if not (("mmsi" in header_map) and ("lat" in header_map or "latitude" in header_map) and ("lon" in header_map or "longitude" in header_map)):
            raise AisCsvValidationError("CSV missing required columns: MMSI, LAT, LON.")

        lat_col = header_map.get("lat") or header_map.get("latitude")
        lon_col = header_map.get("lon") or header_map.get("longitude")
        mmsi_col = header_map.get("mmsi")
        time_col = header_map.get("basedatetime") or header_map.get("datetime") or header_map.get("timestamp")
        name_col = header_map.get("vesselname")
        type_col = header_map.get("vesseltype")
        sog_col = header_map.get("sog")
        cog_col = header_map.get("cog")

        for idx, row in enumerate(reader):
            try:
                mmsi = int(float(row[mmsi_col]))
                lat = float(row[lat_col])
                lon = float(row[lon_col])
                
                # Check valid coordinates
                if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
                    continue

                dt_str = row.get(time_col, "") if time_col else "2020-08-10T01:38:00Z"
                v_name = row.get(name_col, f"VESSEL_{mmsi}") if name_col else f"VESSEL_{mmsi}"
                v_type = row.get(type_col, "Cargo") if type_col else "Cargo"
                sog = float(row.get(sog_col, 10.0)) if sog_col and row.get(sog_col) else 10.0
                cog = float(row.get(cog_col, 0.0)) if cog_col and row.get(cog_col) else 0.0

                rec = {
                    "mmsi": mmsi,
                    "timestamp_utc": dt_str,
                    "lat": lat,
                    "lon": lon,
                    "sog_knots": sog,
                    "cog_degrees": cog,
                    "vessel_name": v_name,
                    "vessel_type": v_type
                }
                records.append(rec)

                if mmsi not in vessel_map:
                    vessel_map[mmsi] = []
                vessel_map[mmsi].append(rec)
            except (ValueError, TypeError):
                continue

    if not records:
        raise AisCsvValidationError("No valid AIS coordinate rows found in CSV.")

    vessels_summary = []
    for mmsi, pts in vessel_map.items():
        vessels_summary.append({
            "mmsi": mmsi,
            "vessel_name": pts[0]["vessel_name"],
            "vessel_type": pts[0]["vessel_type"],
            "track_points_count": len(pts),
            "start_time": pts[0]["timestamp_utc"],
            "end_time": pts[-1]["timestamp_utc"]
        })

    return {
        "valid": True,
        "file_name": filename,
        "total_records_ingested": len(records),
        "unique_vessels_count": len(vessels_summary),
        "vessels_summary": vessels_summary,
        "raw_records": records[:200],  # Sample points
        "validation_status": "PASS",
        "data_mode": "HISTORICAL_CSV_UPLOAD"
    }
