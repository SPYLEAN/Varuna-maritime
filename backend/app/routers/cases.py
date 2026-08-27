from __future__ import annotations
from datetime import datetime, timezone
import uuid
from typing import List
from fastapi import APIRouter, HTTPException, status
from ..schemas import (
    AnalystQuestion,
    AnalystQuestionCreate,
    Case,
    CaseCreate,
)
from ..storage import storage

router = APIRouter(prefix="/cases", tags=["Cases"])


@router.post("", response_model=Case, status_code=status.HTTP_201_CREATED)
def create_case(payload: CaseCreate) -> Case:
    case_id = f"case_{uuid.uuid4().hex[:8]}"
    now_iso = datetime.now(timezone.utc).isoformat()

    case_model = Case(
        case_id=case_id,
        name=payload.name,
        description=payload.description,
        observation_timestamp=payload.observation_timestamp or now_iso,
        latitude=payload.latitude,
        longitude=payload.longitude,
        source=payload.source,
        tags=payload.tags,
        created_at=now_iso,
    )

    case_dict = case_model.model_dump()
    storage.save_case(case_dict)
    return case_model


@router.get("", response_model=List[Case])
def list_cases() -> List[Case]:
    raw_cases = storage.list_cases()
    return [Case(**c) for c in raw_cases]


@router.get("/{case_id}", response_model=Case)
def get_case(case_id: str) -> Case:
    raw_case = storage.get_case(case_id)
    if not raw_case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case '{case_id}' not found",
        )
    return Case(**raw_case)


@router.post("/{case_id}/questions", response_model=AnalystQuestion, status_code=status.HTTP_201_CREATED)
def add_analyst_question(case_id: str, payload: AnalystQuestionCreate) -> AnalystQuestion:
    raw_case = storage.get_case(case_id)
    if not raw_case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case '{case_id}' not found",
        )

    q_id = f"q_{uuid.uuid4().hex[:8]}"
    now_iso = datetime.now(timezone.utc).isoformat()

    question_model = AnalystQuestion(
        question_id=q_id,
        question=payload.question,
        asked_by=payload.asked_by,
        created_at=now_iso,
    )

    # Ensure data_manifest and analyst_questions list exist
    if "data_manifest" not in raw_case or not isinstance(raw_case["data_manifest"], dict):
        raw_case["data_manifest"] = {}

    questions_list = raw_case["data_manifest"].get("analyst_questions", [])
    questions_list.append(question_model.model_dump())
    raw_case["data_manifest"]["analyst_questions"] = questions_list

    storage.save_case(raw_case)
    return question_model
