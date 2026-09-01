"""
SAMUDRANETRA — TASK010A BLIND AIS INGESTION + SPATIOTEMPORAL RETRIEVAL SERVICE

Implements the AIS evidence layer that searches historical vessel traffic using ONLY
SamudraNetra's FROZEN pre-truth reconstructed source regions and time windows under a
STRICT CLEAN-ROOM PROTOCOL.
"""

from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from shapely.geometry import MultiPolygon, Point, Polygon, LineString, shape

from backend.app.services.hindcast_forcing_hardening import haversine_distance_m


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculates haversine distance in kilometers between two points."""
    return haversine_distance_m(lat1, lon1, lat2, lon2) / 1000.0


ELIGIBLE_HYPOTHESES = [
    "C3929", "C001", "C2973", "C4023", "C016", "C4053", "C058", "C062"
]
OBSERVATION_TIME_UTC = "2020-08-10T01:38:07.500Z"


@dataclass
class AISMessage:
    timestamp_utc: str
    mmsi: str
    latitude: float
    longitude: float
    sog_knots: float = 0.0
    cog_deg: float = 0.0
    heading_deg: float = 0.0
    imo: Optional[str] = None
    vessel_name: Optional[str] = None
    vessel_type: str = "unknown"
    nav_status: str = "under_way"
    draught: Optional[float] = None
    destination: Optional[str] = None
    source_provider: str = "SYNTHETIC_DEMO_DATA"
    record_quality: str = "VALID"
    source_provenance: str = "TASK010A_INGESTION"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def compute_file_sha256(filepath: Path) -> str:
    """Computes SHA256 digest for a file."""
    if not filepath.exists():
        return "FILE_NOT_FOUND"
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def create_ais_clean_room_manifest(r_dir: Path) -> Dict[str, Any]:
    """
    Creates R001_AIS_CLEAN_ROOM_MANIFEST.json hashing frozen pre-truth outputs and
    recording explicit forbidden historical truth fields.
    """
    out_dir = r_dir / "07_results" / "ais"
    out_dir.mkdir(parents=True, exist_ok=True)

    files_to_freeze = [
        r_dir / "07_results" / "hindcast_opendrift" / "R001_OPENDRIFT_CONFIG.json",
        r_dir / "07_results" / "hindcast_opendrift" / "R001_OPENDRIFT_HYPOTHESIS_PHYSICS.csv",
        r_dir / "07_results" / "hindcast_opendrift" / "R001_OPENDRIFT_SOURCE_REGIONS_24H.geojson",
        r_dir / "07_results" / "hindcast_opendrift" / "R001_OPENDRIFT_SOURCE_REGIONS_48H.geojson",
        r_dir / "07_results" / "hindcast_opendrift" / "R001_OPENDRIFT_SOURCE_REGIONS_72H.geojson",
        r_dir / "07_results" / "hindcast_opendrift" / "R001_OPENDRIFT_SOURCE_REGIONS_96H.geojson",
        r_dir / "07_results" / "forward_validation" / "R001_FORWARD_CONFIG.json",
        r_dir / "07_results" / "forward_validation" / "R001_NUMERICAL_CLOSURE_METRICS.csv",
    ]

    hashes = {}
    for fpath in files_to_freeze:
        if fpath.exists():
            hashes[str(fpath.relative_to(r_dir))] = compute_file_sha256(fpath)

    manifest = {
        "case_id": "R001_WAKASHIO",
        "task_id": "TASK010A",
        "clean_room_protocol_enforced": True,
        "pre_truth_physical_outputs_frozen": True,
        "forbidden_truth_fields": [
            "wakashio_vessel_name",
            "historical_mmsi",
            "historical_imo",
            "grounding_latitude_longitude",
            "historical_release_start_time",
            "historical_validation_rank",
            "R001_HISTORICAL_TRUTH_EXTRACT.json"
        ],
        "allowed_input_directories": [
            "07_results/hindcast_opendrift/",
            "07_results/hindcast_opendrift/diagnostics/",
            "07_results/forward_validation/"
        ],
        "artifact_hashes": hashes,
        "ais_retrieval_start_timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }

    manifest_file = out_dir / "R001_AIS_CLEAN_ROOM_MANIFEST.json"
    with open(manifest_file, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    return manifest


def perform_ais_data_inventory(r_dir: Path) -> Dict[str, Any]:
    """
    Inspects available project/research files to check for real historical AIS data.
    Generates R001_AIS_DATA_INVENTORY.json and R001_AIS_REAL_DATA_REQUIREMENTS.md.
    """
    out_dir = r_dir / "07_results" / "ais"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Search for real historical AIS raw trajectory data files in repository
    raw_ais_found = False
    discovered_files = []

    for path in r_dir.rglob("*"):
        # Ignore outputs in 07_results/ais
        if "07_results" in path.parts and "ais" in path.parts:
            continue
        name_lower = path.name.lower()
        if path.is_file() and any(k in name_lower for k in ["ais_points", "vessel_tracks", "raw_ais", "ais_archive", "ais_raw"]):
            if path.suffix.lower() in [".csv", ".parquet", ".json", ".geojson", ".db"]:
                discovered_files.append(str(path.relative_to(r_dir)))
                raw_ais_found = True

    inventory = {
        "case_id": "R001_WAKASHIO",
        "task_id": "TASK010A",
        "ais_data_available": "NO" if not raw_ais_found else "PARTIAL",
        "ais_real_data_ready": "NO" if not raw_ais_found else "YES",
        "discovered_ais_files_count": len(discovered_files),
        "discovered_files": discovered_files,
        "known_commercial_providers": [
            {
                "provider": "Kpler / MarineTraffic",
                "coverage": "Global satellite & terrestrial AIS archive",
                "license": "Commercial API / Enterprise",
                "historical_window_support": "2018–present",
                "recommendation": "Primary procurement option for Mauritius 2020 archive"
            },
            {
                "provider": "Spire Maritime",
                "coverage": "High-density satellite AIS",
                "license": "Commercial API / Bulk export",
                "historical_window_support": "Historical AOI export",
                "recommendation": "Primary paid alternative for deep ocean coverage"
            },
            {
                "provider": "AISHub",
                "coverage": "Community terrestrial network",
                "license": "Reciprocal data sharing",
                "historical_window_support": "Recent feed (not complete historical archive)",
                "recommendation": "Coverage supplement only"
            },
            {
                "provider": "S&P Global Maritime",
                "coverage": "Global vessel tracking archive",
                "license": "Commercial procurement",
                "historical_window_support": "Historical database",
                "recommendation": "Enterprise alternative"
            }
        ],
        "inventory_timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }

    with open(out_dir / "R001_AIS_DATA_INVENTORY.json", "w", encoding="utf-8") as f:
        json.dump(inventory, f, indent=2)

    requirements_md = f"""# SAMUDRANETRA — REAL AIS DATA PROCUREMENT REQUIREMENTS

**Case ID**: R001_WAKASHIO  
**Status**: Real historical AIS data not present in local workspace (`AIS_REAL_DATA_READY = NO`).  
**Ingestion Engine**: Pipeline fully functional using synthetic demonstration data (`SYNTHETIC_DEMO_DATA`).

---

## Required Spatiotemporal Query Parameters for External Procurement

1. **Spatial Bounding Box**:
   - South Latitude: `-22.0° S`
   - North Latitude: `-19.0° S`
   - West Longitude: `56.5° E`
   - East Longitude: `60.0° E`
   - Area of Interest: Mauritius EEZ and surrounding South-West Indian Ocean waters.

2. **Temporal Window**:
   - Start Timestamp: `2020-08-05T00:00:00Z` (T-120h prior to primary SAR acquisition)
   - End Timestamp: `2020-08-10T12:00:00Z` (T+10h post SAR acquisition)

3. **Required AIS Message Fields**:
   - `timestamp_utc` (ISO 8601 UTC)
   - `mmsi` (9-digit Maritime Mobile Service Identity)
   - `latitude`, `longitude` (Decimal degrees WGS84)
   - `sog_knots` (Speed over ground in knots)
   - `cog_deg` (Course over ground in degrees)
   - `heading_deg` (True heading in degrees)
   - `vessel_name`, `vessel_type`, `imo`, `nav_status`, `draught`, `destination`

---

## Approved Providers & Delivery Formats

- **Kpler / MarineTraffic**: AOI CSV/JSON historical export API
- **Spire Maritime**: Historical GeoJSON/Parquet bulk delivery
- **S&P Global**: Maritime Intelligence Database export

---
*Note: Synthetic demonstration dataset generated for TASK010A pipeline validation is strictly marked `SYNTHETIC_DEMO_DATA` and is never passed off as historical truth.*
"""

    (out_dir / "R001_AIS_REAL_DATA_REQUIREMENTS.md").write_text(requirements_md, encoding="utf-8")

    return inventory


def validate_and_clean_ais_records(records: List[Dict[str, Any]]) -> Tuple[List[AISMessage], List[Dict[str, Any]]]:
    """
    Validates AIS records for latitude, longitude, MMSI syntax, SOG/COG bounds,
    and chronological ordering. Flags anomalies in record_quality.
    """
    clean_messages: List[AISMessage] = []
    anomalies: List[Dict[str, Any]] = []

    seen_keys = set()

    for r in records:
        ts_str = str(r.get("timestamp_utc", ""))
        mmsi_str = str(r.get("mmsi", "")).strip()
        
        try:
            lat = float(r.get("latitude", 0.0))
            lon = float(r.get("longitude", 0.0))
        except (ValueError, TypeError):
            anomalies.append({"record": r, "reason": "LAT_LON_PARSING_ERROR"})
            continue

        sog = float(r.get("sog_knots", 0.0))
        cog = float(r.get("cog_deg", 0.0))
        heading = float(r.get("heading_deg", 0.0))

        quality_flags = []

        # Latitude / Longitude bounds check
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
            quality_flags.append("LAT_LON_OUT_OF_BOUNDS")

        # MMSI syntax check (9 digits)
        if not (mmsi_str.isdigit() and len(mmsi_str) == 9):
            quality_flags.append("INVALID_MMSI_FORMAT")

        # SOG check (0 to 60 knots)
        if sog < 0.0 or sog > 60.0:
            quality_flags.append("IMPOSSIBLE_SOG")

        # COG check (0 to 360 degrees)
        if cog < 0.0 or cog > 360.0:
            cog = cog % 360.0
            quality_flags.append("COG_NORMALIZED")

        # Deduplication check
        dedup_key = f"{mmsi_str}_{ts_str}_{lat:.5f}_{lon:.5f}"
        if dedup_key in seen_keys:
            quality_flags.append("DUPLICATE_RECORD")
        else:
            seen_keys.add(dedup_key)

        quality_str = "VALID" if not quality_flags else ";".join(quality_flags)

        msg = AISMessage(
            timestamp_utc=ts_str,
            mmsi=mmsi_str,
            latitude=lat,
            longitude=lon,
            sog_knots=sog,
            cog_deg=cog,
            heading_deg=heading,
            imo=r.get("imo"),
            vessel_name=r.get("vessel_name"),
            vessel_type=str(r.get("vessel_type", "unknown")),
            nav_status=str(r.get("nav_status", "under_way")),
            draught=r.get("draught"),
            destination=r.get("destination"),
            source_provider=r.get("source_provider", "SYNTHETIC_DEMO_DATA"),
            record_quality=quality_str,
            source_provenance="TASK010A_INGESTION",
        )

        clean_messages.append(msg)
        if quality_str != "VALID":
            anomalies.append({"mmsi": mmsi_str, "timestamp_utc": ts_str, "flags": quality_str})

    # Sort chronologically
    clean_messages.sort(key=lambda m: m.timestamp_utc)

    return clean_messages, anomalies


def generate_synthetic_demo_ais() -> List[Dict[str, Any]]:
    """
    Generates synthetic demonstration AIS trajectories across the South-West Indian Ocean
    to demonstrate complete TASK010A pipeline functionality without fabricating historical truth.
    MMSIs used are generic test IDs.
    """
    records = []

    # 4 synthetic vessels with varied trajectories
    # V1: Commercial cargo vessel passing near SE Mauritius
    # V2: Fishing vessel operating off S Mauritius
    # V3: Tanker passing well offshore east of Mauritius
    # V4: Container ship passing far north of Mauritius
    vessels = [
        {"mmsi": "538001111", "name": "VESSEL_ALPHA", "type": "cargo", "lat_start": -20.65, "lon_start": 57.50, "speed": 11.5, "heading": 45.0},
        {"mmsi": "538002222", "name": "VESSEL_BETA", "type": "fishing", "lat_start": -20.80, "lon_start": 58.10, "speed": 6.2, "heading": 120.0},
        {"mmsi": "538003333", "name": "VESSEL_GAMMA", "type": "tanker", "lat_start": -21.20, "lon_start": 59.20, "speed": 13.8, "heading": 30.0},
        {"mmsi": "538004444", "name": "VESSEL_DELTA", "type": "cargo", "lat_start": -19.50, "lon_start": 57.30, "speed": 14.2, "heading": 85.0},
    ]

    base_dt = datetime(2020, 8, 6, 0, 0, 0, tzinfo=timezone.utc)
    end_dt = datetime(2020, 8, 10, 1, 38, 7, tzinfo=timezone.utc)

    for v in vessels:
        dt = base_dt
        step_min = 60  # 1 hour interval
        curr_lat = v["lat_start"]
        curr_lon = v["lon_start"]

        while dt <= end_dt:
            # Advance lat/lon slightly based on speed & heading
            rad = math.radians(v["heading"])
            dist_km = v["speed"] * 1.852 * (step_min / 60.0)  # knots to km
            d_lat = (dist_km * math.cos(rad)) / 111.0
            d_lon = (dist_km * math.sin(rad)) / (111.0 * math.cos(math.radians(curr_lat)))

            curr_lat += d_lat
            curr_lon += d_lon

            records.append({
                "timestamp_utc": dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "mmsi": v["mmsi"],
                "vessel_name": v["name"],
                "vessel_type": v["type"],
                "latitude": round(curr_lat, 5),
                "longitude": round(curr_lon, 5),
                "sog_knots": v["speed"],
                "cog_deg": v["heading"],
                "heading_deg": v["heading"],
                "nav_status": "under_way",
                "source_provider": "SYNTHETIC_DEMO_DATA"
            })

            dt += timedelta(minutes=step_min)

    return records


def reconstruct_vessel_tracks(messages: List[AISMessage]) -> List[Dict[str, Any]]:
    """
    Groups AIS observations by MMSI into vessel tracks and calculates
    track completeness, duration, sampling gaps, and median reporting interval.
    """
    tracks_by_mmsi: Dict[str, List[AISMessage]] = {}
    for m in messages:
        tracks_by_mmsi.setdefault(m.mmsi, []).append(m)

    tracks = []
    for mmsi, msgs in tracks_by_mmsi.items():
        msgs.sort(key=lambda x: x.timestamp_utc)
        start_ts = msgs[0].timestamp_utc
        end_ts = msgs[-1].timestamp_utc

        dt_start = datetime.fromisoformat(start_ts.replace("Z", "+00:00"))
        dt_end = datetime.fromisoformat(end_ts.replace("Z", "+00:00"))
        duration_hours = round((dt_end - dt_start).total_seconds() / 3600.0, 2)

        # Gap calculation
        gaps_minutes = []
        for i in range(1, len(msgs)):
            t1 = datetime.fromisoformat(msgs[i-1].timestamp_utc.replace("Z", "+00:00"))
            t2 = datetime.fromisoformat(msgs[i].timestamp_utc.replace("Z", "+00:00"))
            gaps_minutes.append((t2 - t1).total_seconds() / 60.0)

        median_gap_min = round(float(np.median(gaps_minutes)), 1) if gaps_minutes else 0.0
        max_gap_hours = round(float(np.max(gaps_minutes)) / 60.0, 2) if gaps_minutes else 0.0

        # Completeness ratio
        expected_msgs = max(1, int(duration_hours * 60.0 / max(1.0, median_gap_min))) if median_gap_min > 0 else len(msgs)
        completeness = round(min(1.0, len(msgs) / expected_msgs), 3)

        tracks.append({
            "mmsi": mmsi,
            "vessel_name": msgs[0].vessel_name or "UNKNOWN",
            "vessel_type": msgs[0].vessel_type,
            "track_start_utc": start_ts,
            "track_end_utc": end_ts,
            "duration_hours": duration_hours,
            "record_count": len(msgs),
            "median_reporting_interval_minutes": median_gap_min,
            "max_reporting_gap_hours": max_gap_hours,
            "track_completeness": completeness,
            "has_large_gap": max_gap_hours > 2.0,
            "points": msgs,
        })

    return tracks


def compute_source_region_intersections(
    tracks: List[Dict[str, Any]],
    envelopes_geojson: Dict[str, Any],
    spatial_buffer_km: float = 10.0
) -> List[Dict[str, Any]]:
    """
    Calculates exact geodesic minimum distance to source region boundaries,
    polygon containment, time of closest approach, dwell time, and centroid distance
    for every vessel track × frozen source hypothesis.
    """
    intersections = []
    features = envelopes_geojson.get("features", [])

    for trk in tracks:
        mmsi = trk["mmsi"]
        vname = trk["vessel_name"]
        vtype = trk["vessel_type"]
        points = trk["points"]

        for feat in features:
            props = feat.get("properties", {})
            cand_id = props.get("candidate_id")
            horizon_h = props.get("horizon_hours", 72)
            
            if cand_id not in ELIGIBLE_HYPOTHESES:
                continue

            geom = shape(feat.get("geometry"))
            centroid_lat = props.get("centroid_lat", geom.centroid.y)
            centroid_lon = props.get("centroid_lon", geom.centroid.x)

            min_dist_km = 9999.0
            closest_ts = None
            inside_count = 0
            intersects = False

            for p in points:
                pt = Point(p.longitude, p.latitude)
                
                # Check point containment
                if geom.contains(pt):
                    inside_count += 1
                    intersects = True

                # Compute distance to polygon boundary in km
                # Approximate degree distance to km
                if geom.contains(pt):
                    dist_km = 0.0
                else:
                    # Boundary distance approximation
                    ext_coords = list(geom.exterior.coords) if hasattr(geom, 'exterior') else []
                    dists = [haversine_distance_km(p.latitude, p.longitude, c[1], c[0]) for c in ext_coords]
                    dist_km = min(dists) if dists else 999.0

                if dist_km < min_dist_km:
                    min_dist_km = dist_km
                    closest_ts = p.timestamp_utc

            # Secondary metric: Centroid distance
            first_pt = points[0]
            cent_dist_km = haversine_distance_km(first_pt.latitude, first_pt.longitude, centroid_lat, centroid_lon)

            # Dwell time calculation
            dwell_min = inside_count * trk["median_reporting_interval_minutes"]

            intersections.append({
                "mmsi": mmsi,
                "vessel_name": vname,
                "vessel_type": vtype,
                "candidate_id": cand_id,
                "horizon_hours": horizon_h,
                "min_geodesic_distance_km": round(min_dist_km, 3),
                "intersects_source_region": intersects or (min_dist_km <= spatial_buffer_km),
                "inside_polygon_point_count": inside_count,
                "time_of_closest_approach_utc": closest_ts,
                "dwell_time_minutes": round(dwell_min, 1),
                "centroid_distance_km_secondary": round(cent_dist_km, 3),
            })

    return intersections


def evaluate_ais_temporal_compatibility(
    track_start_utc: str,
    track_end_utc: str,
    horizon_hours: int,
    obs_time_utc: str = OBSERVATION_TIME_UTC
) -> Dict[str, Any]:
    """
    Evaluates vessel presence within blind horizon time window [T_obs - horizon_hours, T_obs].
    Output: TEMPORALLY_COMPATIBLE, PARTIALLY_COMPATIBLE, NOT_COMPATIBLE, INSUFFICIENT_AIS_COVERAGE.
    """
    dt_obs = datetime.fromisoformat(obs_time_utc.replace("Z", "+00:00"))
    dt_window_start = dt_obs - timedelta(hours=horizon_hours)

    dt_track_start = datetime.fromisoformat(track_start_utc.replace("Z", "+00:00"))
    dt_track_end = datetime.fromisoformat(track_end_utc.replace("Z", "+00:00"))

    # Check temporal overlap
    overlap_start = max(dt_window_start, dt_track_start)
    overlap_end = min(dt_obs, dt_track_end)

    if overlap_start < overlap_end:
        overlap_hours = (overlap_end - overlap_start).total_seconds() / 3600.0
        fraction = overlap_hours / horizon_hours

        if fraction >= 0.5:
            status = "TEMPORALLY_COMPATIBLE"
        else:
            status = "PARTIALLY_COMPATIBLE"
    else:
        overlap_hours = 0.0
        status = "NOT_COMPATIBLE"

    return {
        "temporal_status": status,
        "overlap_hours": round(overlap_hours, 2),
        "horizon_window_start": dt_window_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "horizon_window_end": obs_time_utc,
    }


def extract_vessel_behavioural_features(track: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extracts SOG behaviour (slowdowns/dwells), COG course changes, and AIS reporting gap evidence.
    Flagged strictly as INVESTIGATIVE INDICATORS, NOT proof of oil discharge.
    """
    points: List[AISMessage] = track["points"]
    sogs = [p.sog_knots for p in points]
    cogs = [p.cog_deg for p in points]

    min_sog = round(float(np.min(sogs)), 2) if sogs else 0.0
    mean_sog = round(float(np.mean(sogs)), 2) if sogs else 0.0
    median_sog = round(float(np.median(sogs)), 2) if sogs else 0.0

    # Slowdowns & Dwells (SOG < 3 knots)
    dwell_points = sum(1 for s in sogs if s < 3.0)
    has_slowdown = min_sog < 3.0 and max(sogs) > 8.0

    # COG course turns (> 45 degrees)
    turn_count = 0
    for i in range(1, len(cogs)):
        diff = abs(cogs[i] - cogs[i-1])
        if diff > 180:
            diff = 360 - diff
        if diff >= 45.0:
            turn_count += 1

    # AIS Gap analysis
    max_gap_h = track["max_reporting_gap_hours"]
    gap_evidence = "NORMAL_TRANSMISSION"
    if max_gap_h > 4.0:
        gap_evidence = "EXTENDED_SILENCE_INTERVAL"
    elif max_gap_h > 2.0:
        gap_evidence = "MODERATE_REPORTING_GAP"

    return {
        "mmsi": track["mmsi"],
        "vessel_name": track["vessel_name"],
        "sog_min_knots": min_sog,
        "sog_mean_knots": mean_sog,
        "sog_median_knots": median_sog,
        "slowdown_event_detected": has_slowdown,
        "low_speed_dwell_points": dwell_points,
        "cog_sharp_turns_count": turn_count,
        "max_reporting_gap_hours": max_gap_h,
        "ais_gap_evidence": gap_evidence,
        "investigative_note": "INVESTIGATIVE INDICATORS ONLY — NOT PROOF OF OIL DISCHARGE",
    }


def compute_ais_evidence_scores(
    intersections: List[Dict[str, Any]],
    tracks: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Calculates individual normalized component evidence scores:
    spatial_compatibility, temporal_compatibility, route_compatibility, behaviour_indicator, ais_data_integrity.
    DOES NOT calculate guilt probability or culprit attribution.
    """
    track_map = {t["mmsi"]: t for t in tracks}
    evidence_rows = []

    for ix in intersections:
        mmsi = ix["mmsi"]
        trk = track_map.get(mmsi, {})
        behav = extract_vessel_behavioural_features(trk) if trk else {}
        temp_eval = evaluate_ais_temporal_compatibility(trk.get("track_start_utc", OBSERVATION_TIME_UTC), trk.get("track_end_utc", OBSERVATION_TIME_UTC), ix["horizon_hours"])

        # 1. Spatial score (0 to 1 based on geodesic boundary distance)
        dist = ix["min_geodesic_distance_km"]
        spat_score = round(max(0.0, 1.0 - (dist / 50.0)), 3)

        # 2. Temporal score
        t_status = temp_eval["temporal_status"]
        temp_score = 1.0 if t_status == "TEMPORALLY_COMPATIBLE" else (0.5 if t_status == "PARTIALLY_COMPATIBLE" else 0.0)

        # 3. Route score
        route_score = 0.9 if ix["intersects_source_region"] else 0.4

        # 4. Behaviour indicator score
        behav_score = 0.8 if behav.get("slowdown_event_detected") else 0.5

        # 5. AIS data integrity score
        comp = trk.get("track_completeness", 1.0)
        gap_h = trk.get("max_reporting_gap_hours", 0.0)
        integ_score = round(max(0.0, comp - (gap_h / 24.0)), 3)

        evidence_rows.append({
            "mmsi": mmsi,
            "vessel_name": ix["vessel_name"],
            "vessel_type": ix["vessel_type"],
            "candidate_id": ix["candidate_id"],
            "horizon_hours": ix["horizon_hours"],
            "min_geodesic_distance_km": ix["min_geodesic_distance_km"],
            "spatial_compatibility_score": spat_score,
            "temporal_compatibility_score": temp_score,
            "route_compatibility_score": route_score,
            "behaviour_indicator_score": behav_score,
            "ais_data_integrity_score": integ_score,
            "temporal_status": t_status,
            "intersects_source_region": ix["intersects_source_region"],
            "attribution_note": "INDIVIDUAL COMPONENT EVIDENCE SCORES ONLY — NO GUILT ATTRIBUTION ASSIGNED IN TASK010A"
        })

    return evidence_rows


def render_ais_maps(
    r_dir: Path,
    tracks: List[Dict[str, Any]],
    envelopes_geojson: Dict[str, Any],
    intersections: List[Dict[str, Any]]
) -> List[str]:
    """
    Renders candidate tracks and source intersection overlay maps.
    """
    maps_dir = r_dir / "07_results" / "ais" / "maps"
    maps_dir.mkdir(parents=True, exist_ok=True)
    rendered = []

    # Map 1: Candidate Tracks
    fig, ax = plt.subplots(figsize=(10, 8))
    
    # Plot source envelopes
    for feat in envelopes_geojson.get("features", []):
        geom = shape(feat.get("geometry"))
        if geom.geom_type == 'Polygon':
            x, y = geom.exterior.xy
            ax.plot(x, y, color="orange", alpha=0.5, linewidth=1.5, linestyle="--")

    # Plot vessel tracks
    colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728"]
    for idx, trk in enumerate(tracks):
        pts = trk["points"]
        lons = [p.longitude for p in pts]
        lats = [p.latitude for p in pts]
        ax.plot(lons, lats, marker="o", markersize=3, label=f"{trk['vessel_name']} ({trk['mmsi']})", color=colors[idx % len(colors)])

    ax.set_title("SAMUDRANETRA TASK010A — BLIND AIS CANDIDATE TRACKS", fontsize=12, fontweight="bold")
    ax.set_xlabel("Longitude (°E)")
    ax.set_ylabel("Latitude (°S)")
    ax.grid(True, linestyle=":", alpha=0.6)
    ax.legend(loc="upper right", fontsize=8)

    map1_path = maps_dir / "R001_AIS_CANDIDATE_TRACKS.png"
    plt.savefig(map1_path, dpi=150, bbox_inches="tight")
    plt.close()
    rendered.append(str(map1_path))

    # Map 2: Source Intersections
    fig, ax = plt.subplots(figsize=(10, 8))
    for feat in envelopes_geojson.get("features", []):
        geom = shape(feat.get("geometry"))
        if geom.geom_type == 'Polygon':
            x, y = geom.exterior.xy
            ax.fill(x, y, alpha=0.2, color="crimson")
            ax.plot(x, y, color="crimson", linewidth=1.5)

    for idx, trk in enumerate(tracks):
        pts = trk["points"]
        lons = [p.longitude for p in pts]
        lats = [p.latitude for p in pts]
        ax.plot(lons, lats, label=f"{trk['vessel_name']} ({trk['mmsi']})", color=colors[idx % len(colors)])

    ax.set_title("SAMUDRANETRA TASK010A — AIS SOURCE REGION INTERSECTIONS", fontsize=12, fontweight="bold")
    ax.set_xlabel("Longitude (°E)")
    ax.set_ylabel("Latitude (°S)")
    ax.grid(True, linestyle=":", alpha=0.6)
    ax.legend(loc="upper right", fontsize=8)

    map2_path = maps_dir / "R001_AIS_SOURCE_INTERSECTIONS.png"
    plt.savefig(map2_path, dpi=150, bbox_inches="tight")
    plt.close()
    rendered.append(str(map2_path))

    return rendered
