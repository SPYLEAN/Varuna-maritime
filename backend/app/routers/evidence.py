from __future__ import annotations
from datetime import datetime, timezone
import uuid
from typing import List, Optional
from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from ..schemas import Evidence, EvidenceType
from ..storage import storage

router = APIRouter(prefix="/cases/{case_id}/evidence", tags=["Evidence"])


@router.post("", response_model=Evidence, status_code=status.HTTP_201_CREATED)
async def upload_evidence(
    case_id: str,
    file: UploadFile = File(...),
    evidence_type: EvidenceType = Form(...),
    source: Optional[str] = Form(None),
    acquisition_timestamp: Optional[str] = Form(None),
    is_synthetic: bool = Form(False),
    is_human_verified: bool = Form(False),
    notes: Optional[str] = Form(None),
) -> Evidence:
    raw_case = storage.get_case(case_id)
    if not raw_case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case '{case_id}' not found",
        )

    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file must have a filename",
        )

    content_bytes = await file.read()
    try:
        stored_path, file_size, sha256_hex = storage.save_evidence_file(case_id, file.filename, content_bytes)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        )

    ev_id = f"ev_{uuid.uuid4().hex[:8]}"
    now_iso = datetime.now(timezone.utc).isoformat()

    evidence_model = Evidence(
        evidence_id=ev_id,
        case_id=case_id,
        evidence_type=evidence_type,
        original_filename=file.filename,
        stored_path=stored_path,
        mime_type=file.content_type,
        file_size=file_size,
        sha256=sha256_hex,
        source=source,
        acquisition_timestamp=acquisition_timestamp,
        uploaded_at=now_iso,
        is_synthetic=is_synthetic,
        is_human_verified=is_human_verified,
        notes=notes,
    )

    ev_dict = evidence_model.model_dump()

    # Store evidence metadata in data_manifest.evidence
    if "data_manifest" not in raw_case or not isinstance(raw_case["data_manifest"], dict):
        raw_case["data_manifest"] = {}

    evidence_list = raw_case["data_manifest"].get("evidence", [])
    evidence_list.append(ev_dict)
    raw_case["data_manifest"]["evidence"] = evidence_list

    # Categorize into manifest lists
    cat_key_map = {
        EvidenceType.SAR_IMAGE: "satellite_imagery",
        EvidenceType.OIL_MASK: "oil_masks",
        EvidenceType.AIS: "ais_data",
        EvidenceType.MET_OCEAN: "met_ocean_data",
        EvidenceType.RESEARCH_NOTE: "research_notes",
    }
    cat_key = cat_key_map.get(evidence_type)
    if cat_key:
        cat_list = raw_case["data_manifest"].get(cat_key, [])
        cat_list.append(ev_dict)
        raw_case["data_manifest"][cat_key] = cat_list

    storage.save_case(raw_case)
    return evidence_model


@router.get("", response_model=List[Evidence])
def list_evidence(case_id: str, evidence_type: Optional[EvidenceType] = None) -> List[Evidence]:
    raw_case = storage.get_case(case_id)
    if not raw_case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case '{case_id}' not found",
        )

    evidence_list = raw_case.get("data_manifest", {}).get("evidence", [])
    items = [Evidence(**item) for item in evidence_list]
    if evidence_type:
        items = [item for item in items if item.evidence_type == evidence_type]
    return items
