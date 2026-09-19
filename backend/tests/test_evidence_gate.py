"""Unit tests for Varuna Evidence Gate Service."""

import pytest
from backend.app.services.evidence_gate import evaluate_candidate_for_physics


def test_physics_eligible_candidate():
    decision = evaluate_candidate_for_physics(
        candidate_id="SLICK_001",
        area_km2=1.2,
        mean_evidence_score=0.88,
        max_evidence_score=0.98,
        solidity=0.75,
        elongation=2.4,
        wind_speed_ms=6.5,
        distance_to_land_km=15.0,
    )

    assert decision.status == "PHYSICS_ELIGIBLE"
    assert decision.physics_eligible is True
    assert decision.scores.overall_confidence > 0.70
    assert any("optimal" in r.lower() or "strong" in r.lower() for r in decision.decision_reasons)


def test_rejected_lookalike_low_wind():
    decision = evaluate_candidate_for_physics(
        candidate_id="SLICK_002",
        area_km2=0.5,
        mean_evidence_score=0.45,
        max_evidence_score=0.55,
        solidity=0.95,
        elongation=1.05,
        wind_speed_ms=1.5,  # Low wind regime -> calm sea lookalike
        distance_to_land_km=10.0,
    )

    assert decision.status == "REJECTED_LOOKALIKE"
    assert decision.physics_eligible is False
    assert decision.scores.lookalike_risk_score >= 0.60
    assert any("low wind" in r.lower() for r in decision.decision_reasons)


def test_rejected_lookalike_negligible_area():
    decision = evaluate_candidate_for_physics(
        candidate_id="SLICK_003",
        area_km2=0.005,  # Below threshold
        mean_evidence_score=0.60,
        max_evidence_score=0.70,
        solidity=0.80,
        elongation=1.5,
        wind_speed_ms=5.0,
    )

    assert decision.status == "REJECTED_LOOKALIKE"
    assert decision.physics_eligible is False


def test_review_required_marginal_attributes():
    decision = evaluate_candidate_for_physics(
        candidate_id="SLICK_004",
        area_km2=0.06,  # Just above minimum
        mean_evidence_score=0.55,  # Moderate score
        max_evidence_score=0.68,
        solidity=0.82,
        elongation=1.3,
        wind_speed_ms=11.5,  # Marginal high wind
        distance_to_land_km=5.0,
    )

    assert decision.status == "REVIEW_REQUIRED"
    assert decision.physics_eligible is False
    assert "review" in decision.recommended_action.lower()
