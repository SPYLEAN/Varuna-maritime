from __future__ import annotations
from pathlib import Path
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse
from ..storage import storage

router = APIRouter(prefix="/cases/{case_id}", tags=["Files"])


@router.get("/evidence/{evidence_id}/file")
def get_evidence_file(case_id: str, evidence_id: str):
    raw_case = storage.get_case(case_id)
    if not raw_case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case '{case_id}' not found",
        )

    evidence_list = raw_case.get("data_manifest", {}).get("evidence", [])
    ev_record = None
    for ev in evidence_list:
        if ev.get("evidence_id") == evidence_id:
            ev_record = ev
            break

    if not ev_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evidence '{evidence_id}' not found in case '{case_id}'",
        )

    stored_path = Path(ev_record.get("stored_path", "")).resolve()
    evidence_dir = storage.get_case_evidence_dir(case_id).resolve()

    if not stored_path.exists() or not str(stored_path).startswith(str(evidence_dir)):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evidence file not found or inaccessible",
        )

    media_type = ev_record.get("mime_type") or "application/octet-stream"
    return FileResponse(path=str(stored_path), media_type=media_type, filename=ev_record.get("original_filename"))


@router.get("/outputs/{filename}")
def get_output_file(case_id: str, filename: str):
    raw_case = storage.get_case(case_id)
    if not raw_case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case '{case_id}' not found",
        )

    safe_name = Path(filename).name
    outputs_dir = storage.get_case_outputs_dir(case_id).resolve()
    target_path = (outputs_dir / safe_name).resolve()

    if not target_path.exists() or not str(target_path).startswith(str(outputs_dir)):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Output file not found or inaccessible",
        )

    media_type = "image/png" if safe_name.endswith(".png") else "application/octet-stream"
    return FileResponse(path=str(target_path), media_type=media_type, filename=safe_name)
