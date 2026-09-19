"""Evidence Gate Service for Varuna.

Evaluates candidate oil slick polygons before initiation of OpenDrift numerical simulations.
Enforces RULE 7: "Do not send every dark patch into OpenDrift."

Produces explainable decisions:
- PHYSICS_ELIGIBLE
- REVIEW_REQUIRED
- REJECTED_LOOKALIKE
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger("varuna.services.evidence_gate")


class GateScores(BaseModel):
    segmentation_score: float = Field(..., description="Normalized segmentation confidence [0, 1]")
    morphology_score: float = Field(..., description="Slick shape suitability [0, 1]")
    environmental_score: float = Field(..., description="Metocean wind/current physical viability [0, 1]")
    lookalike_risk_score: float = Field(..., description="Probability/penalty of natural phenomenon [0, 1]")
    overall_confidence: float = Field(..., description="Composite decision confidence [0, 1]")


class EvidenceGateDecision(BaseModel):
    status: str = Field(..., description="PHYSICS_ELIGIBLE, REVIEW_REQUIRED, or REJECTED_LOOKALIKE")
    candidate_id: str
    scores: GateScores
    decision_reasons: List[str]
    physics_eligible: bool
    recommended_action: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


def evaluate_candidate_for_physics(
    candidate_id: str,
    area_km2: float,
    mean_evidence_score: float,
    max_evidence_score: float,
    solidity: float,
    elongation: float,
    wind_speed_ms: Optional[float] = None,
    distance_to_land_km: Optional[float] = None,
    min_area_km2: float = 0.05,
    max_area_km2: float = 150.0,
) -> EvidenceGateDecision:
    """Evaluate candidate polygon attributes against physical feasibility criteria."""
    reasons: List[str] = []
    
    # 1. Segmentation Evidence Analysis
    seg_score = float(np_clip((mean_evidence_score * 0.6 + max_evidence_score * 0.4), 0.0, 1.0))
    if mean_evidence_score >= 0.75:
        reasons.append(f"Strong dual-polarization backscatter damping (mean evidence: {mean_evidence_score:.2f})")
    elif mean_evidence_score >= 0.50:
        reasons.append(f"Moderate oil evidence score ({mean_evidence_score:.2f}) within actionable threshold")
    else:
        reasons.append(f"Weak oil evidence score ({mean_evidence_score:.2f}) below baseline detection threshold")

    # 2. Morphology Analysis
    # Mineral oil slicks under drift typically elongate along current/wind shear (elongation > 1.3)
    # Circular blobs (solidity > 0.95, elongation ~ 1.0) often indicate rain cells, biogenic blooms, or SAR nadir artifacts
    morph_reasons: List[str] = []
    morph_penalty = 0.0
    
    if area_km2 < min_area_km2:
        morph_penalty += 0.35
        morph_reasons.append(f"Area ({area_km2:.3f} km²) is below minimum physical simulation threshold ({min_area_km2} km²)")
    elif area_km2 > max_area_km2:
        morph_penalty += 0.40
        morph_reasons.append(f"Area ({area_km2:.1f} km²) exceeds realistic single continuous slick envelope ({max_area_km2} km²)")
    else:
        morph_reasons.append(f"Geometry area ({area_km2:.3f} km²) within valid operational spill scale")

    if elongation >= 1.5:
        morph_reasons.append(f"High elongation ({elongation:.2f}) consistent with advective slick drift streak")
    elif elongation < 1.15 and solidity > 0.92:
        morph_penalty += 0.30
        morph_reasons.append(f"Near-circular morphology (solidity={solidity:.2f}, elongation={elongation:.2f}) suggests biogenic bloom or atmospheric cell")
    else:
        morph_reasons.append(f"Morphological elongation ({elongation:.2f}) and solidity ({solidity:.2f}) acceptable")

    morph_score = float(max(0.0, 1.0 - morph_penalty))
    reasons.extend(morph_reasons)

    # 3. Environmental Compatibility
    # SAR oil detection operates reliably between ~2.5 m/s (minimum capillary wave generation)
    # and ~12.0 m/s (upper limit before turbulent wave breaking disperses oil droplets into water column)
    env_score = 1.0
    env_reasons: List[str] = []
    lookalike_risk = 0.10

    if wind_speed_ms is not None:
        if wind_speed_ms < 2.5:
            env_score -= 0.50
            lookalike_risk += 0.60
            env_reasons.append(f"Low wind speed ({wind_speed_ms:.1f} m/s < 2.5 m/s): high risk of low-wind calm sea lookalike")
        elif wind_speed_ms > 14.0:
            env_score -= 0.40
            lookalike_risk += 0.20
            env_reasons.append(f"High wind speed ({wind_speed_ms:.1f} m/s > 14 m/s): slick likely dispersed into water column; high surface clutter")
        elif 3.0 <= wind_speed_ms <= 10.0:
            env_reasons.append(f"Optimal SAR wind regime ({wind_speed_ms:.1f} m/s): capillary waves dampened reliably by mineral oil")
        else:
            env_reasons.append(f"Wind speed ({wind_speed_ms:.1f} m/s) within marginal operational window")
    else:
        env_reasons.append("Environmental forcing wind speed not provided; default neutral meteorological prior applied")

    if distance_to_land_km is not None:
        if distance_to_land_km < 0.3:
            env_score -= 0.30
            lookalike_risk += 0.30
            env_reasons.append(f"Proximity to coast ({distance_to_land_km*1000:.0f}m < 300m): possible land-shadow or shallow bathymetry false positive")

    reasons.extend(env_reasons)

    # 4. Synthesize Decision
    overall_conf = float(np_clip(
        (seg_score * 0.45 + morph_score * 0.30 + env_score * 0.25) * (1.0 - lookalike_risk * 0.5),
        0.0,
        1.0,
    ))

    if lookalike_risk >= 0.60 or seg_score < 0.40 or area_km2 < (min_area_km2 * 0.5):
        status = "REJECTED_LOOKALIKE"
        physics_eligible = False
        action = "Reject candidate. Do not execute OpenDrift simulation. Mark as suspected natural lookalike or clutter in incident record."
    elif overall_conf >= 0.70 and seg_score >= 0.65 and area_km2 >= min_area_km2 and morph_score >= 0.60:
        status = "PHYSICS_ELIGIBLE"
        physics_eligible = True
        action = "Eligible for physics simulation. Automatically initiate OpenDrift hindcast and forward response forecast."
    else:
        status = "REVIEW_REQUIRED"
        physics_eligible = False
        action = "Flag for operational review. Candidate exhibits marginal attributes; require human operator approval prior to OpenDrift simulation."

    scores = GateScores(
        segmentation_score=round(seg_score, 4),
        morphology_score=round(morph_score, 4),
        environmental_score=round(env_score, 4),
        lookalike_risk_score=round(lookalike_risk, 4),
        overall_confidence=round(overall_conf, 4),
    )

    return EvidenceGateDecision(
        status=status,
        candidate_id=candidate_id,
        scores=scores,
        decision_reasons=reasons,
        physics_eligible=physics_eligible,
        recommended_action=action,
        metadata={
            "area_km2": area_km2,
            "mean_evidence_score": mean_evidence_score,
            "max_evidence_score": max_evidence_score,
            "solidity": solidity,
            "elongation": elongation,
            "wind_speed_ms": wind_speed_ms,
            "distance_to_land_km": distance_to_land_km,
        },
    )


def np_clip(val: float, low: float, high: float) -> float:
    return max(low, min(high, val))
