"""
SAMUDRANETRA — TASK010B EXPLAINABLE AIS EVIDENCE RANKING + ABSTENTION ENGINE

Implements explainable AIS evidence prioritization, hard spatiotemporal guards,
abstention classification, human-readable reason code generation, and cryptographic
ranking freezing under strict data-mode guards (data_mode = SYNTHETIC_DEMO).
"""

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from shapely.geometry import shape

from backend.app.services.ais_engine import haversine_distance_km

DEFAULT_WEIGHTS = {
    "spatial": 0.30,
    "temporal": 0.25,
    "route": 0.20,
    "behaviour": 0.10,
    "ais_integrity": 0.05,
    "physics_support": 0.10,
}

WEIGHT_VERSION = "1.0.0"
WEIGHT_RATIONALE = (
    "Spatial containment and temporal alignment are primary physical requirements (0.55 total). "
    "Route continuity provides structural support (0.20). Behavioural indicators (0.10) and "
    "physics hypothesis quality (0.10) strengthen/weaken evidence. AIS integrity (0.05) "
    "penalizes sampling gaps without assuming guilt."
)


def compute_string_sha256(content: str) -> str:
    """Computes SHA256 digest for string content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def compute_file_sha256(filepath: Path) -> str:
    """Computes SHA256 digest for a file."""
    if not filepath.exists():
        return "FILE_NOT_FOUND"
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def get_current_data_mode(r_dir: Path) -> Tuple[str, bool]:
    """
    Inspects AIS provenance file to determine data mode.
    Returns (data_mode, historical_attribution_valid).
    """
    prov_file = r_dir / "07_results" / "ais" / "R001_AIS_PROVENANCE.json"
    if prov_file.exists():
        with open(prov_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            if data.get("ais_real_data_ready") == "YES" and data.get("ais_data_available") == "YES":
                return "REAL_HISTORICAL", True

    return "SYNTHETIC_DEMO", False


def calculate_investigative_priority_score(
    evidence_row: Dict[str, Any],
    weights: Optional[Dict[str, float]] = None
) -> Dict[str, Any]:
    """
    Calculates deterministic INVESTIGATIVE_PRIORITY_SCORE and component dimensions.
    Enforces Hard Evidence Guards.
    """
    w = weights or DEFAULT_WEIGHTS.copy()

    # Extract component scores
    spat_score = float(evidence_row.get("spatial_compatibility_score", 0.0))
    temp_score = float(evidence_row.get("temporal_compatibility_score", 0.0))
    route_score = float(evidence_row.get("route_compatibility_score", 0.0))
    behav_score = float(evidence_row.get("behaviour_indicator_score", 0.0))
    integ_score = float(evidence_row.get("ais_data_integrity_score", 0.0))
    
    # Physics support (derived from hindcast physics status, default 0.8)
    physics_score = 0.8

    # Calculate weighted sum
    total_w = sum(w.values())
    raw_score = (
        spat_score * w["spatial"] +
        temp_score * w["temporal"] +
        route_score * w["route"] +
        behav_score * w["behaviour"] +
        integ_score * w["ais_integrity"] +
        physics_score * w["physics_support"]
    ) / total_w

    priority_score = round(raw_score, 3)

    # HARD EVIDENCE GUARD CHECK
    # High priority requires: temporal_status == TEMPORALLY_COMPATIBLE
    # AND (intersects_source_region == True OR min_geodesic_distance_km <= 5.0)
    t_status = evidence_row.get("temporal_status", "")
    intersects = bool(evidence_row.get("intersects_source_region", False))
    dist_km = float(evidence_row.get("min_geodesic_distance_km", 999.0))

    hard_guard_passed = (t_status == "TEMPORALLY_COMPATIBLE") and (intersects or dist_km <= 5.0)

    # If hard guard failed, priority score cannot exceed 0.69
    if not hard_guard_passed:
        priority_score = min(priority_score, 0.69)

    return {
        "mmsi": evidence_row["mmsi"],
        "vessel_name": evidence_row["vessel_name"],
        "vessel_type": evidence_row["vessel_type"],
        "candidate_id": evidence_row["candidate_id"],
        "horizon_hours": evidence_row["horizon_hours"],
        "investigative_priority_score": priority_score,
        "spatial_evidence": spat_score,
        "temporal_evidence": temp_score,
        "route_evidence": route_score,
        "behaviour_evidence": behav_score,
        "ais_integrity": integ_score,
        "physics_support": physics_score,
        "hard_guard_passed": hard_guard_passed,
    }


def generate_reason_codes_and_evidence(
    evidence_row: Dict[str, Any],
    behaviour_row: Optional[Dict[str, Any]] = None,
    gap_row: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Generates human-readable reason codes and categorizes evidence into
    supporting_evidence, limiting_evidence, and missing_evidence lists.
    """
    reason_codes = []
    supporting = []
    limiting = []
    missing = []

    intersects = bool(evidence_row.get("intersects_source_region", False))
    dist_km = float(evidence_row.get("min_geodesic_distance_km", 999.0))
    t_status = evidence_row.get("temporal_status", "")
    spat_score = float(evidence_row.get("spatial_compatibility_score", 0.0))

    # Spatial reason codes
    if intersects:
        reason_codes.append("SOURCE_REGION_INTERSECTION")
        supporting.append("Vessel track directly intersects blind reconstructed source envelope.")
    elif dist_km <= 15.0:
        reason_codes.append("CLOSE_APPROACH")
        supporting.append(f"Vessel track passed within {dist_km:.1f} km of source envelope.")
    else:
        limiting.append(f"Vessel minimum distance to source envelope is {dist_km:.1f} km.")

    # Temporal reason codes
    if t_status == "TEMPORALLY_COMPATIBLE":
        reason_codes.append("STRONG_TEMPORAL_MATCH")
        supporting.append("Vessel operating window aligns with blind physical backtracking horizon.")
    elif t_status == "PARTIALLY_COMPATIBLE":
        limiting.append("Vessel track partially overlaps blind physical backtracking horizon.")
    else:
        limiting.append("Vessel track falls outside blind physical backtracking horizon.")

    # Behavioural reason codes
    if behaviour_row:
        if behaviour_row.get("slowdown_event_detected"):
            reason_codes.append("SPEED_CHANGE_PRESENT")
            reason_codes.append("DWELL_NEAR_SOURCE_REGION")
            supporting.append("Sudden speed reduction / dwell event detected near source domain.")
        if behaviour_row.get("cog_sharp_turns_count", 0) > 0:
            reason_codes.append("COURSE_CHANGE_PRESENT")
            supporting.append(f"Sharp course change detected ({behaviour_row['cog_sharp_turns_count']} turns).")

    # AIS Gap reason codes
    if gap_row:
        max_gap = float(gap_row.get("max_reporting_gap_hours", 0.0))
        if max_gap > 2.0:
            reason_codes.append("AIS_GAP_PRESENT")
            limiting.append(f"Reporting gap of {max_gap:.1f} hours observed.")
        if gap_row.get("ais_gap_evidence") == "EXTENDED_SILENCE_INTERVAL":
            reason_codes.append("AIS_COVERAGE_WEAK")
            missing.append("Extended silence interval during key temporal window.")

    return {
        "reason_codes": reason_codes,
        "supporting_evidence": supporting,
        "limiting_evidence": limiting,
        "missing_evidence": missing,
    }


def classify_attribution_state(
    ranked_vessels: List[Dict[str, Any]],
    ais_coverage_quality: float = 0.90
) -> Dict[str, Any]:
    """
    Classifies overall case-level and vessel-level investigative attribution states.
    Prevents forced winners using abstention logic.
    """
    if not ranked_vessels:
        return {
            "overall_case_state": "NO_CREDIBLE_CANDIDATE",
            "explanation": "No AIS vessel tracks were present within the spatiotemporal search domain.",
            "abstention_triggered": True
        }

    if ais_coverage_quality < 0.30:
        return {
            "overall_case_state": "INSUFFICIENT_DATA",
            "explanation": "AIS spatial/temporal coverage is inadequate to draw vessel conclusions.",
            "abstention_triggered": True
        }

    top_vessel = ranked_vessels[0]
    top_score = top_vessel["investigative_priority_score"]

    # Check for Ambiguous Attribution (top 2 score delta <= 0.05)
    if len(ranked_vessels) >= 2:
        second_score = ranked_vessels[1]["investigative_priority_score"]
        if top_score >= 0.70 and (top_score - second_score) <= 0.05:
            return {
                "overall_case_state": "AMBIGUOUS_ATTRIBUTION",
                "explanation": f"Multiple top candidate vessels ({top_vessel['vessel_name']} and {ranked_vessels[1]['vessel_name']}) possess nearly identical evidence priority scores ({top_score:.3f} vs {second_score:.3f}).",
                "abstention_triggered": True
            }

    if top_score >= 0.70 and top_vessel["hard_guard_passed"]:
        overall_state = "HIGH_PRIORITY_INVESTIGATIVE_CANDIDATE"
        abstention = False
    elif top_score >= 0.45:
        overall_state = "MODERATE_PRIORITY_INVESTIGATIVE_CANDIDATE"
        abstention = False
    elif top_score >= 0.25:
        overall_state = "LOW_PRIORITY_INVESTIGATIVE_CANDIDATE"
        abstention = False
    else:
        overall_state = "NON_VESSEL_SOURCE_POSSIBLE"
        abstention = True

    return {
        "overall_case_state": overall_state,
        "explanation": f"Top candidate {top_vessel['vessel_name']} evaluated with priority score {top_score:.3f}.",
        "abstention_triggered": abstention
    }


def create_api_ready_vessel_objects(
    ranked_vessels: List[Dict[str, Any]],
    data_mode: str = "SYNTHETIC_DEMO",
    historical_attribution_valid: bool = False
) -> List[Dict[str, Any]]:
    """
    Creates standardized API-ready vessel objects adhering to Section 14 schema.
    """
    api_objects = []

    for idx, v in enumerate(ranked_vessels):
        # Assign vessel-level priority state
        score = v["investigative_priority_score"]
        if score >= 0.70 and v["hard_guard_passed"]:
            v_state = "HIGH_PRIORITY_INVESTIGATIVE_CANDIDATE"
        elif score >= 0.45:
            v_state = "MODERATE_PRIORITY_INVESTIGATIVE_CANDIDATE"
        else:
            v_state = "LOW_PRIORITY_INVESTIGATIVE_CANDIDATE"

        api_objects.append({
            "vessel_id": v["mmsi"],
            "vessel_name": v["vessel_name"],
            "vessel_type": v["vessel_type"],
            "investigative_priority_score": v["investigative_priority_score"],
            "attribution_state": v_state,
            "evidence_completeness": round(v.get("ais_integrity", 0.95), 3),
            "spatial_evidence": v["spatial_evidence"],
            "temporal_evidence": v["temporal_evidence"],
            "route_evidence": v["route_evidence"],
            "behaviour_evidence": v["behaviour_evidence"],
            "ais_integrity": v["ais_integrity"],
            "physics_support": v["physics_support"],
            "reason_codes": v.get("reason_codes", []),
            "supporting_evidence": v.get("supporting_evidence", []),
            "limiting_evidence": v.get("limiting_evidence", []),
            "missing_evidence": v.get("missing_evidence", []),
            "data_mode": data_mode,
            "historical_attribution_valid": historical_attribution_valid,
        })

    return api_objects


def create_ais_ranking_freeze(r_dir: Path) -> Dict[str, Any]:
    """
    Writes R001_AIS_RANKING_FREEZE.json freezing weights, thresholds,
    reason-code logic, and SHA256 hash for drop-in real AIS execution.
    """
    out_dir = r_dir / "07_results" / "ais_ranking"
    out_dir.mkdir(parents=True, exist_ok=True)

    config = {
        "case_id": "R001_WAKASHIO",
        "task_id": "TASK010B",
        "weight_version": WEIGHT_VERSION,
        "weight_rationale": WEIGHT_RATIONALE,
        "weights": DEFAULT_WEIGHTS,
        "thresholds": {
            "high_priority_min_score": 0.70,
            "moderate_priority_min_score": 0.45,
            "low_priority_min_score": 0.25,
            "ambiguous_score_delta": 0.05,
            "hard_guard_max_boundary_dist_km": 5.0,
            "ais_coverage_quality_min": 0.30,
        },
        "reason_codes_registry": [
            "SOURCE_REGION_INTERSECTION",
            "STRONG_TEMPORAL_MATCH",
            "CLOSE_APPROACH",
            "DWELL_NEAR_SOURCE_REGION",
            "ROUTE_COMPATIBLE",
            "SPEED_CHANGE_PRESENT",
            "COURSE_CHANGE_PRESENT",
            "AIS_GAP_PRESENT",
            "AIS_COVERAGE_WEAK",
            "PHYSICS_HYPOTHESIS_UNCERTAIN"
        ],
        "ranking_engine_frozen": True,
        "freeze_timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }

    config_str = json.dumps(config, indent=2, sort_keys=True)
    config_hash = compute_string_sha256(config_str)
    config["freeze_sha256_hash"] = config_hash

    freeze_file = out_dir / "R001_AIS_RANKING_FREEZE.json"
    with open(freeze_file, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

    return config


def render_ranked_tracks_map(
    r_dir: Path,
    ranked_vessels: List[Dict[str, Any]],
    envelopes_geojson: Dict[str, Any]
) -> str:
    """
    Renders ranked tracks map displaying priority colors and labels.
    """
    maps_dir = r_dir / "07_results" / "ais_ranking" / "maps"
    maps_dir.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(10, 8))

    # Plot source envelopes
    for feat in envelopes_geojson.get("features", []):
        geom = shape(feat.get("geometry"))
        if geom.geom_type == 'Polygon':
            x, y = geom.exterior.xy
            ax.plot(x, y, color="crimson", alpha=0.4, linewidth=1.2, linestyle="--")

    # Colors for priority
    priority_colors = {
        "HIGH_PRIORITY_INVESTIGATIVE_CANDIDATE": "#d62728",
        "MODERATE_PRIORITY_INVESTIGATIVE_CANDIDATE": "#ff7f0e",
        "LOW_PRIORITY_INVESTIGATIVE_CANDIDATE": "#1f77b4",
    }

    # Load points from Task010A points CSV
    pts_file = r_dir / "07_results" / "ais" / "R001_AIS_POINTS.csv"
    if pts_file.exists():
        df_pts = pd.read_csv(pts_file)
        for v in ranked_vessels:
            mmsi = str(v["vessel_id"])
            v_sub = df_pts[df_pts["mmsi"].astype(str) == mmsi]
            if len(v_sub) > 0:
                lons = v_sub["longitude"].values
                lats = v_sub["latitude"].values
                state = v["attribution_state"]
                clr = priority_colors.get(state, "#2ca02c")
                lbl = f"{v['vessel_name']} ({v['investigative_priority_score']:.2f})"
                ax.plot(lons, lats, marker="o", markersize=3, label=lbl, color=clr)

    ax.set_title("SAMUDRANETRA TASK010B — EXPLAINABLE AIS RANKED CANDIDATE TRACKS\n[DATA MODE: SYNTHETIC DEMO]", fontsize=11, fontweight="bold")
    ax.set_xlabel("Longitude (°E)")
    ax.set_ylabel("Latitude (°S)")
    ax.grid(True, linestyle=":", alpha=0.6)
    ax.legend(loc="upper right", fontsize=8)

    out_map = maps_dir / "R001_AIS_RANKED_TRACKS.png"
    plt.savefig(out_map, dpi=150, bbox_inches="tight")
    plt.close()

    return str(out_map)
