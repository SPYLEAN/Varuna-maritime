"""FastAPI Router for VARUNA Intelligence Agent & Operational Decision Support.

Exposes:
- GET /api/v1/intelligence/status
- POST /api/v1/cases/{case_id}/intelligence/ask
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from backend.app.services.varuna_intelligence import (
    VarunaIntelligenceAnswer,
    ask_varuna_intelligence,
    check_bedrock_status,
)
from backend.app.storage import storage

router = APIRouter(tags=["VARUNA Intelligence"])


class AskIntelligenceRequest(BaseModel):
    """User operational query payload."""
    question: str = Field(
        ...,
        min_length=2,
        max_length=1000,
        description="Natural-language operational question regarding the incident case.",
        examples=["What requires attention first?"],
    )
    case_id: Optional[str] = Field(
        default="R001_WAKASHIO",
        description="Target case ID for the query (defaults to R001_WAKASHIO).",
    )


class IntelligenceStatusResponse(BaseModel):
    """VARUNA Intelligence service readiness and provider configuration status."""
    enabled: bool
    framework: str = "STRANDS"
    model_provider: str
    model_id: Optional[str] = None
    mode: str = "DETERMINISTIC_FALLBACK"
    strands_used: bool = False
    status: str


@router.get(
    "/intelligence/status",
    response_model=IntelligenceStatusResponse,
    summary="Get VARUNA Intelligence agent status",
)
def get_intelligence_status() -> IntelligenceStatusResponse:
    """Retrieve operational status and readiness of the Strands / Bedrock agent.
    
    SECURITY GUARANTEE: Never exposes AWS credentials or internal secrets.
    """
    info = check_bedrock_status()
    return IntelligenceStatusResponse(
        enabled=info["enabled"],
        framework="STRANDS",
        model_provider=info["model_provider"],
        model_id=info["model_id"],
        mode=info.get("mode", "DETERMINISTIC_FALLBACK"),
        strands_used=info.get("strands_used", False),
        status=info["status"],
    )


@router.post(
    "/cases/{case_id}/intelligence/ask",
    response_model=VarunaIntelligenceAnswer,
    summary="Ask VARUNA Intelligence an operational question about an incident",
)
def ask_case_intelligence(
    case_id: str,
    payload: AskIntelligenceRequest,
) -> VarunaIntelligenceAnswer:
    """Ask an evidence-grounded operational question about an incident.
    
    Routes through the approved Strands agent tools or the deterministic grounded fallback.
    """
    clean_q = payload.question.strip()
    if not clean_q:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Question cannot be empty or whitespace only.",
        )

    # Validate case existence before processing
    raw_case = storage.get_case(case_id)
    if not raw_case and case_id.upper() not in ["R001_WAKASHIO", "R001", "CASE_R001"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case '{case_id}' not found.",
        )

    answer = ask_varuna_intelligence(case_id=case_id, question=clean_q)
    return answer


@router.post(
    "/ask",
    response_model=VarunaIntelligenceAnswer,
    summary="Ask VARUNA Intelligence an operational question (direct /ask endpoint)",
)
@router.post(
    "/intelligence/ask",
    response_model=VarunaIntelligenceAnswer,
    summary="Ask VARUNA Intelligence an operational question (direct /intelligence/ask endpoint)",
)
def ask_intelligence_direct(
    payload: AskIntelligenceRequest,
) -> VarunaIntelligenceAnswer:
    """Direct alias for querying VARUNA Intelligence."""
    target_case = payload.case_id or "R001_WAKASHIO"
    return ask_case_intelligence(case_id=target_case, payload=payload)


@router.get(
    "/cases/{case_id}/intelligence/response-priority",
    summary="Get explainable marine response priority analysis for an incident",
)
def get_case_response_priority(case_id: str) -> Dict[str, Any]:
    """Evaluates response priority rankings and arrival windows for environmental receptors."""
    raw_case = storage.get_case(case_id)
    if not raw_case and case_id.upper() not in ["R001_WAKASHIO", "R001", "CASE_R001"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case '{case_id}' not found.",
        )

    if raw_case:
        stored_rp = raw_case.get("workflow", {}).get("stages", {}).get("RESPONSE PRIORITIZED", {}).get("data")
        if stored_rp and stored_rp.get("highest_priority_receptor"):
            return {
                "status": "SUCCESS",
                "engine_execution_mode": stored_rp.get("engine_execution_mode", "REAL"),
                "effective_evidence_mode": stored_rp.get("effective_evidence_mode", "SYNTHETIC_DEMO"),
                "highest_priority_receptor": stored_rp.get("highest_priority_receptor"),
                "response_window_hours": stored_rp.get("response_window_hours"),
                "receptors": stored_rp.get("receptors", [stored_rp.get("highest_priority_receptor")]),
                "limitations": [
                    "Receptor distances and arrival horizons are computed from evaluated drift envelope.",
                    "Tactical containment requires on-scene acoustic or visual verification."
                ]
            }
        lat = raw_case.get("latitude", lat)
        lon = raw_case.get("longitude", lon)

    from backend.app.services.response_priority import evaluate_case_response_priorities
    return evaluate_case_response_priorities(
        case_lat=lat,
        case_lon=lon,
        forecast_data={},
        engine_execution_mode="REAL",
    )
