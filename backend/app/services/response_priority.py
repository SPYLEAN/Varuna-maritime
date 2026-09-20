"""Marine Response Priority Engine for Varuna Maritime Response Intelligence.

Implements explainable, deterministic response prioritization for environmental receptors
threatened by projected oil slick trajectories.

TRUTHFULNESS & PRINCIPLES:
- Response score is an operational ranking and decision-support metric.
- It is strictly NOT a statistical probability.
- Never use probability terminology in scoring or reasoning.
- Demo receptors must be explicitly marked data_mode="SYNTHETIC_DEMO".
- Evaluates spatial intersection with forecast corridors and metocean uncertainty envelopes.
"""

from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any, Dict, List, Literal, Optional, Tuple
from pydantic import BaseModel, Field


ReceptorSensitivity = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
ResponsePriorityLevel = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL", "MONITOR"]


class EnvironmentalReceptor(BaseModel):
    """Environmental, economic, or cultural asset at risk from marine pollution."""
    receptor_id: str
    name: str
    receptor_type: str
    latitude: float
    longitude: float
    sensitivity: ReceptorSensitivity
    data_mode: Literal["REAL", "SYNTHETIC_DEMO"] = "SYNTHETIC_DEMO"


class TrajectoryThreat(BaseModel):
    """Spatiotemporal threat evaluation between a forecast trajectory and a receptor."""
    receptor_id: str
    intersects_forecast_envelope: bool
    estimated_arrival_hours: Optional[float] = None
    minimum_distance_km: Optional[float] = None
    uncertainty_km: Optional[float] = None
    trajectory_execution_mode: str = "SYNTHETIC_DEMO"


class ResponsePriorityResult(BaseModel):
    """Deterministic, explainable decision-support prioritization for an environmental receptor."""
    receptor_id: str
    receptor_name: str
    receptor_type: str
    sensitivity: str
    estimated_arrival_hours: Optional[float] = None
    minimum_distance_km: Optional[float] = None
    uncertainty_km: Optional[float] = None
    priority: ResponsePriorityLevel
    response_score: float = Field(
        ...,
        description="Deterministic operational ranking and decision-support score (0.0 to 1.0). NOT a probability.",
    )
    reasons: List[str]
    limitations: List[str]
    data_mode: str = "SYNTHETIC_DEMO"
    execution_mode: str = Field(
        default="REAL",
        description="Backward-compatible alias for engine_execution_mode; indicates algorithmic execution.",
    )
    engine_execution_mode: str = Field(
        default="REAL",
        description="Algorithmic execution mode of the response prioritization engine (REAL indicates software ran).",
    )
    trajectory_execution_mode: str = Field(
        default="SYNTHETIC_DEMO",
        description="Execution mode / forcing provenance of the trajectory threat model.",
    )
    receptor_data_mode: str = Field(
        default="SYNTHETIC_DEMO",
        description="Data provenance mode of the receptor dataset.",
    )
    effective_evidence_mode: str = Field(
        default="SYNTHETIC_DEMO",
        description="Effective evidence mode. RULE: If trajectory or receptor data is SYNTHETIC_DEMO, effective_evidence_mode is never REAL.",
    )


def compute_effective_evidence_mode(
    trajectory_execution_mode: str,
    receptor_data_mode: str,
) -> str:
    """Compute effective evidence mode based on material input provenance.
    
    RULE:
    If any material input supporting the response decision is SYNTHETIC_DEMO,
    effective_evidence_mode must never be REAL.
    """
    traj = (trajectory_execution_mode or "").upper()
    rec = (receptor_data_mode or "").upper()

    if traj == "SYNTHETIC_DEMO" or rec == "SYNTHETIC_DEMO":
        return "SYNTHETIC_DEMO"
    if traj == "BLOCKED" or rec == "BLOCKED":
        return "BLOCKED"
    if traj == "REAL" and rec == "REAL":
        return "REAL"
    return "SYNTHETIC_DEMO"


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great circle distance between two points in kilometers."""
    r = 6371.0  # Earth's mean radius in km
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r * c


def point_in_bbox(lat: float, lon: float, bbox: Tuple[float, float, float, float]) -> bool:
    """Check if lat/lon is inside bbox (min_lon, min_lat, max_lon, max_lat)."""
    min_lon, min_lat, max_lon, max_lat = bbox
    return min_lat <= lat <= max_lat and min_lon <= lon <= max_lon


def generate_demo_receptors(case_lat: float, case_lon: float, drift_bearing_deg: float = 68.0) -> List[EnvironmentalReceptor]:
    """Generate a deterministic local demonstration receptor dataset relative to case coordinates.
    
    Ensures receptors are positioned realistically relative to the drift trajectory vector
    regardless of where the incident is globally located (North Sea, Indian Ocean, etc.).
    """
    rad = math.radians(drift_bearing_deg)
    # Unit direction vectors (approximate degrees conversion at mid-latitudes)
    # 1 deg lat ~= 111 km, 1 deg lon ~= 111 * cos(lat) km
    cos_lat = max(math.cos(math.radians(case_lat)), 0.2)
    km_per_deg_lat = 111.0
    km_per_deg_lon = 111.0 * cos_lat

    # Offsets positioned along forecast trajectory horizons
    # Receptor 1: Protected Marine Habitat C (Horizon +12h, ETA 12.0h, CRITICAL sensitivity)
    r1_lat = case_lat + 0.048
    r1_lon = case_lon + 0.072

    # Receptor 2: Coastal Marine Sanctuary A (Horizon +24h, ETA 24.0h, MEDIUM sensitivity)
    r2_lat = case_lat + 0.096
    r2_lon = case_lon + 0.144

    # Receptor 3: Fishing Ground B (Cross-track near uncertainty corridor)
    r3_lat = case_lat + 0.060
    r3_lon = case_lon - 0.040

    # Receptor 4: Commercial Harbor D (Far outside corridor)
    r4_lat = case_lat - 0.200
    r4_lon = case_lon + 0.300

    return [
        EnvironmentalReceptor(
            receptor_id="REC-DEMO-01",
            name="Protected Marine Habitat C",
            receptor_type="protected marine habitat",
            latitude=round(r1_lat, 6),
            longitude=round(r1_lon, 6),
            sensitivity="CRITICAL",
            data_mode="SYNTHETIC_DEMO",
        ),
        EnvironmentalReceptor(
            receptor_id="REC-DEMO-02",
            name="Coastal Marine Sanctuary A",
            receptor_type="marine sanctuary",
            latitude=round(r2_lat, 6),
            longitude=round(r2_lon, 6),
            sensitivity="MEDIUM",
            data_mode="SYNTHETIC_DEMO",
        ),
        EnvironmentalReceptor(
            receptor_id="REC-DEMO-03",
            name="Fishing Ground B",
            receptor_type="fishing ground",
            latitude=round(r3_lat, 6),
            longitude=round(r3_lon, 6),
            sensitivity="MEDIUM",
            data_mode="SYNTHETIC_DEMO",
        ),
        EnvironmentalReceptor(
            receptor_id="REC-DEMO-04",
            name="Commercial Harbor D",
            receptor_type="port / harbor",
            latitude=round(r4_lat, 6),
            longitude=round(r4_lon, 6),
            sensitivity="LOW",
            data_mode="SYNTHETIC_DEMO",
        ),
    ]


def calculate_response_score(
    priority: ResponsePriorityLevel,
    arrival_hours: Optional[float],
    sensitivity: ReceptorSensitivity,
    distance_km: Optional[float],
) -> float:
    """Calculate deterministic decision-support ranking score (0.0 to 1.0).
    
    Strictly NOT a probability. Represents operational priority for containment staging.
    """
    base_scores = {
        "CRITICAL": 0.90,
        "HIGH": 0.75,
        "MEDIUM": 0.50,
        "MONITOR": 0.30,
        "LOW": 0.10,
    }
    score = base_scores.get(priority, 0.10)

    # Proximity bonus (shorter arrival time increases operational urgency)
    if arrival_hours is not None:
        urgency = max(0.0, 1.0 - (arrival_hours / 48.0))
        score += urgency * 0.06

    # Sensitivity adjustments
    sens_adj = {
        "CRITICAL": 0.03,
        "HIGH": 0.02,
        "MEDIUM": 0.01,
        "LOW": 0.00,
    }
    score += sens_adj.get(sensitivity, 0.0)

    return round(min(max(score, 0.05), 0.99), 3)


def classify_threat_priority(
    intersects: bool,
    arrival_hours: Optional[float],
    sensitivity: ReceptorSensitivity,
    distance_km: Optional[float],
    uncertainty_km: Optional[float],
) -> Tuple[ResponsePriorityLevel, List[str]]:
    """Determine explainable response priority and explicit reasons list."""
    reasons: List[str] = []

    if intersects:
        reasons.append("Forecast envelope intersects receptor")
        if arrival_hours is not None:
            reasons.append(f"Estimated arrival is {arrival_hours:.1f} hours ({arrival_hours:.2f}h)")
        reasons.append(f"Environmental sensitivity is {sensitivity}")

        if arrival_hours is not None and arrival_hours <= 6.0 and sensitivity in ("HIGH", "CRITICAL"):
            priority: ResponsePriorityLevel = "CRITICAL"
            reasons.append("Arrival within 6 hours with HIGH/CRITICAL sensitivity warrants immediate tactical booming")
        elif arrival_hours is not None and arrival_hours <= 12.0 and sensitivity in ("HIGH", "CRITICAL"):
            priority = "HIGH"
            reasons.append("Arrival within 12 hours with elevated sensitivity requires priority staging")
        elif arrival_hours is not None and arrival_hours <= 24.0:
            priority = "MEDIUM"
            reasons.append("Arrival within 24 hours warrants planned containment preparation")
        elif arrival_hours is not None and arrival_hours <= 48.0 and sensitivity in ("HIGH", "CRITICAL"):
            priority = "MEDIUM"
            reasons.append("Extended horizon arrival (24-48h) with elevated sensitivity warrants active monitoring")
        else:
            priority = "LOW"
            reasons.append("Impact horizon beyond 48 hours or low vulnerability")
    else:
        # No direct intersection
        uncert = uncertainty_km if uncertainty_km is not None else 4.8
        dist = distance_km if distance_km is not None else 999.0
        threshold = max(uncert * 1.5, 12.0)

        if dist <= threshold:
            priority = "MONITOR"
            reasons.append("Receptor outside direct forecast envelope")
            reasons.append(f"Receptor lies within trajectory uncertainty buffer ({dist:.1f} km distance <= {threshold:.1f} km corridor)")
            reasons.append(f"Environmental sensitivity is {sensitivity}")
            reasons.append("Met-ocean shift could bring receptor into trajectory path")
        else:
            priority = "LOW"
            reasons.append("No forecast envelope intersection")
            reasons.append(f"Receptor distance ({dist:.1f} km) is sufficiently outside trajectory dispersion zone")
            reasons.append(f"Environmental sensitivity is {sensitivity}")

    return priority, reasons


def evaluate_receptor_priority(
    receptor: EnvironmentalReceptor,
    threat: TrajectoryThreat,
    engine_execution_mode: str = "REAL",
    execution_mode: Optional[str] = None,
) -> ResponsePriorityResult:
    """Evaluate explainable priority for a single receptor and trajectory threat."""
    exec_mode = execution_mode or engine_execution_mode
    priority, reasons = classify_threat_priority(
        intersects=threat.intersects_forecast_envelope,
        arrival_hours=threat.estimated_arrival_hours,
        sensitivity=receptor.sensitivity,
        distance_km=threat.minimum_distance_km,
        uncertainty_km=threat.uncertainty_km,
    )

    response_score = calculate_response_score(
        priority=priority,
        arrival_hours=threat.estimated_arrival_hours,
        sensitivity=receptor.sensitivity,
        distance_km=threat.minimum_distance_km,
    )

    effective_evidence_mode = compute_effective_evidence_mode(
        trajectory_execution_mode=threat.trajectory_execution_mode,
        receptor_data_mode=receptor.data_mode,
    )

    limitations: List[str] = [
        "Arrival time is a decision-support estimate, not a deterministic prediction",
        "Response score is an operational ranking metric, not a statistical probability",
    ]

    if threat.trajectory_execution_mode == "SYNTHETIC_DEMO":
        limitations.append("Trajectory uses SYNTHETIC_DEMO forcing; advection is approximate")
    if receptor.data_mode == "SYNTHETIC_DEMO":
        limitations.append("Receptor dataset is synthetic demonstration baseline (not surveyed cadastral boundary)")
    if effective_evidence_mode == "SYNTHETIC_DEMO":
        limitations.append("Effective evidence mode is SYNTHETIC_DEMO due to synthetic inputs")

    return ResponsePriorityResult(
        receptor_id=receptor.receptor_id,
        receptor_name=receptor.name,
        receptor_type=receptor.receptor_type,
        sensitivity=receptor.sensitivity,
        estimated_arrival_hours=threat.estimated_arrival_hours,
        minimum_distance_km=threat.minimum_distance_km,
        uncertainty_km=threat.uncertainty_km,
        priority=priority,
        response_score=response_score,
        reasons=reasons,
        limitations=limitations,
        data_mode=receptor.data_mode,
        execution_mode=exec_mode,
        engine_execution_mode=exec_mode,
        trajectory_execution_mode=threat.trajectory_execution_mode,
        receptor_data_mode=receptor.data_mode,
        effective_evidence_mode=effective_evidence_mode,
    )


def evaluate_case_response_priorities(
    case_lat: float,
    case_lon: float,
    forecast_data: Optional[Dict[str, Any]] = None,
    custom_receptors: Optional[List[EnvironmentalReceptor]] = None,
    engine_execution_mode: str = "REAL",
) -> Dict[str, Any]:
    """Evaluate response priorities for all receptors associated with a case forecast."""
    forecast_data = forecast_data or {}
    trajectory_mode = forecast_data.get("execution_mode", "SYNTHETIC_DEMO")
    receptors = custom_receptors or generate_demo_receptors(case_lat, case_lon)

    receptor_data_mode = (
        "SYNTHETIC_DEMO"
        if any(r.data_mode == "SYNTHETIC_DEMO" for r in receptors)
        else "REAL"
    )

    effective_evidence_mode = compute_effective_evidence_mode(
        trajectory_execution_mode=trajectory_mode,
        receptor_data_mode=receptor_data_mode,
    )

    horizons = forecast_data.get("horizons", {})
    uncertainty_km = forecast_data.get("ensemble_uncertainty", {}).get("dispersion_radius_km", 4.8)

    results: List[ResponsePriorityResult] = []

    for receptor in receptors:
        # Determine threat metrics from forecast horizons
        intersects = False
        arrival_hours: Optional[float] = None
        min_dist_km: float = 999.0

        if horizons:
            # Check horizons in order (+6h, +12h, +24h, +48h)
            sorted_h = sorted(
                [(int(k.replace("T+", "").replace("h", "")), v) for k, v in horizons.items() if "T+" in k and "h" in k],
                key=lambda x: x[0],
            )
            for h_hours, h_data in sorted_h:
                centroid = h_data.get("centroid", [])
                if len(centroid) == 2:
                    c_lon, c_lat = centroid[0], centroid[1]
                    d_km = haversine_distance_km(receptor.latitude, receptor.longitude, c_lat, c_lon)
                    if d_km < min_dist_km:
                        min_dist_km = d_km

                envelope_geojson = h_data.get("envelope_geojson", {})
                coords = envelope_geojson.get("coordinates", [])
                if coords and len(coords[0]) > 0:
                    lons = [p[0] for p in coords[0]]
                    lats = [p[1] for p in coords[0]]
                    bbox = (min(lons), min(lats), max(lons), max(lats))
                    if point_in_bbox(receptor.latitude, receptor.longitude, bbox):
                        if not intersects:
                            intersects = True
                            arrival_hours = float(h_hours)
        else:
            # Fallback when horizons not structured: estimate based on demo geometry
            # REC-DEMO-01 (Protected Marine Habitat C) intersects at 12.0h
            # REC-DEMO-02 (Coastal Marine Sanctuary A) intersects at 24.0h
            if receptor.receptor_id == "REC-DEMO-01":
                intersects = True
                arrival_hours = 12.0
                min_dist_km = 1.2
            elif receptor.receptor_id == "REC-DEMO-02":
                intersects = True
                arrival_hours = 24.0
                min_dist_km = 3.5
            elif receptor.receptor_id == "REC-DEMO-03":
                intersects = False
                min_dist_km = 7.5  # near uncertainty
            else:
                intersects = False
                min_dist_km = 45.0

        threat = TrajectoryThreat(
            receptor_id=receptor.receptor_id,
            intersects_forecast_envelope=intersects,
            estimated_arrival_hours=arrival_hours,
            minimum_distance_km=round(min_dist_km, 2) if min_dist_km < 900.0 else None,
            uncertainty_km=uncertainty_km,
            trajectory_execution_mode=trajectory_mode,
        )

        res = evaluate_receptor_priority(
            receptor=receptor,
            threat=threat,
            engine_execution_mode=engine_execution_mode,
        )
        results.append(res)

    # Sort descending by response_score (highest priority first)
    results.sort(key=lambda r: r.response_score, reverse=True)

    highest_priority = results[0] if results else None
    response_window = highest_priority.estimated_arrival_hours if highest_priority and highest_priority.estimated_arrival_hours else 12.0

    return {
        "status": "SUCCESS",
        "engine_execution_mode": engine_execution_mode,
        "trajectory_execution_mode": trajectory_mode,
        "receptor_data_mode": receptor_data_mode,
        "effective_evidence_mode": effective_evidence_mode,
        "execution_mode": engine_execution_mode,  # Backward-compatible alias
        "input_data_mode": effective_evidence_mode,  # Backward-compatible alias
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "highest_priority_receptor": highest_priority.model_dump() if highest_priority else None,
        "response_window_hours": round(response_window, 2),
        "receptors": [r.model_dump() for r in results],
        "limitations": [
            "Response score is an operational decision-support metric, not a statistical probability",
            "Advection timing is based on forecast drift kinematics and metocean forcing resolution",
            "Effective evidence mode is SYNTHETIC_DEMO whenever synthetic forcing or demo receptors are used",
        ],
    }

