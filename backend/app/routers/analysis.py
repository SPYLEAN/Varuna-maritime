from __future__ import annotations
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import uuid
from typing import Optional
from fastapi import APIRouter, HTTPException, status
from ..schemas import AnalysisResult, OilDetectionRequest, StatusEnum
from ..storage import storage
from ml.src.oiltrace_ml.infer import run_inference

router = APIRouter(prefix="/cases/{case_id}/analysis", tags=["Analysis"])


@router.post("/oil-detection", response_model=AnalysisResult)
def run_oil_detection_analysis(case_id: str, payload: Optional[OilDetectionRequest] = None) -> AnalysisResult:
    if payload is None:
        payload = OilDetectionRequest()

    raw_case = storage.get_case(case_id)
    if not raw_case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case '{case_id}' not found",
        )

    an_id = f"an_{uuid.uuid4().hex[:8]}"
    started_at = datetime.now(timezone.utc).isoformat()
    evidence_list = raw_case.get("data_manifest", {}).get("evidence", [])

    # 1. Locate SAR image evidence item
    sar_evidence = None
    if payload.sar_evidence_id:
        for ev in evidence_list:
            if ev.get("evidence_id") == payload.sar_evidence_id:
                sar_evidence = ev
                break
    else:
        # Pick the latest SAR image evidence item
        sar_candidates = [ev for ev in evidence_list if ev.get("evidence_type") == "sar_image"]
        if sar_candidates:
            sar_evidence = sar_candidates[-1]

    # Handle missing SAR evidence
    if not sar_evidence:
        now_iso = datetime.now(timezone.utc).isoformat()
        res = AnalysisResult(
            analysis_id=an_id,
            case_id=case_id,
            module="oil_detection",
            module_version="1.0.0",
            configuration={"checkpoint_path": payload.checkpoint_path, "threshold": payload.threshold},
            started_at=started_at,
            completed_at=now_iso,
            status=StatusEnum.INSUFFICIENT_DATA,
            confidence=None,
            warnings=["No SAR image evidence found for this case. Upload a SAR image first."],
            error="Missing SAR image evidence",
        )

        if "analysis_status" not in raw_case:
            raw_case["analysis_status"] = {}
        raw_case["analysis_status"]["oil_detection"] = StatusEnum.INSUFFICIENT_DATA.value

        gen_results = raw_case.get("data_manifest", {}).get("generated_analysis_results", [])
        gen_results.append(res.model_dump())
        raw_case["data_manifest"]["generated_analysis_results"] = gen_results

        storage.save_case(raw_case)
        return res

    # 2. Locate model checkpoint file
    ckpt_str = payload.checkpoint_path or "models/oiltrace_unet.pt"
    ckpt_path = Path(ckpt_str)

    if not ckpt_path.exists():
        now_iso = datetime.now(timezone.utc).isoformat()
        res = AnalysisResult(
            analysis_id=an_id,
            case_id=case_id,
            module="oil_detection",
            module_version="1.0.0",
            input_evidence_ids=[sar_evidence["evidence_id"]],
            input_hashes=[sar_evidence.get("sha256", "")],
            configuration={"checkpoint_path": str(ckpt_path), "threshold": payload.threshold},
            started_at=started_at,
            completed_at=now_iso,
            status=StatusEnum.INSUFFICIENT_DATA,
            confidence=None,
            warnings=[f"Trained oil detection model checkpoint missing at: '{ckpt_path}'."],
            error=f"Model checkpoint file not found: {ckpt_path}",
        )

        if "analysis_status" not in raw_case:
            raw_case["analysis_status"] = {}
        raw_case["analysis_status"]["oil_detection"] = StatusEnum.INSUFFICIENT_DATA.value

        gen_results = raw_case.get("data_manifest", {}).get("generated_analysis_results", [])
        gen_results.append(res.model_dump())
        raw_case["data_manifest"]["generated_analysis_results"] = gen_results

        storage.save_case(raw_case)
        return res

    # Check input SAR file on disk
    sar_path = Path(sar_evidence["stored_path"])
    if not sar_path.exists():
        now_iso = datetime.now(timezone.utc).isoformat()
        res = AnalysisResult(
            analysis_id=an_id,
            case_id=case_id,
            module="oil_detection",
            module_version="1.0.0",
            input_evidence_ids=[sar_evidence["evidence_id"]],
            input_hashes=[sar_evidence.get("sha256", "")],
            configuration={"checkpoint_path": str(ckpt_path), "threshold": payload.threshold},
            started_at=started_at,
            completed_at=now_iso,
            status=StatusEnum.INSUFFICIENT_DATA,
            confidence=None,
            warnings=[f"SAR image file on disk not found: '{sar_path}'."],
            error=f"SAR file missing on disk: {sar_path}",
        )

        if "analysis_status" not in raw_case:
            raw_case["analysis_status"] = {}
        raw_case["analysis_status"]["oil_detection"] = StatusEnum.INSUFFICIENT_DATA.value

        gen_results = raw_case.get("data_manifest", {}).get("generated_analysis_results", [])
        gen_results.append(res.model_dump())
        raw_case["data_manifest"]["generated_analysis_results"] = gen_results

        storage.save_case(raw_case)
        return res

    # 3. Compute Checkpoint SHA256 for strict model provenance
    ckpt_sha256 = hashlib.sha256(ckpt_path.read_bytes()).hexdigest()

    # 4. Set status to running
    outputs_dir = storage.get_case_outputs_dir(case_id)
    bin_out_path = outputs_dir / f"oil_detection_binary_{an_id}.png"
    prob_out_path = outputs_dir / f"oil_detection_prob_{an_id}.png"

    if "analysis_status" not in raw_case:
        raw_case["analysis_status"] = {}
    raw_case["analysis_status"]["oil_detection"] = StatusEnum.RUNNING.value
    storage.save_case(raw_case)

    # 5. Run U-Net Inference
    try:
        inf_res = run_inference(
            checkpoint_path=ckpt_path,
            image_path=sar_path,
            binary_out_path=bin_out_path,
            prob_out_path=prob_out_path,
            threshold=payload.threshold,
        )
    except Exception as err:
        now_iso = datetime.now(timezone.utc).isoformat()
        res = AnalysisResult(
            analysis_id=an_id,
            case_id=case_id,
            module="oil_detection",
            module_version="1.0.0",
            input_evidence_ids=[sar_evidence["evidence_id"]],
            input_hashes=[sar_evidence.get("sha256", "")],
            configuration={
                "checkpoint_path": str(ckpt_path),
                "checkpoint_sha256": ckpt_sha256,
                "threshold": payload.threshold,
            },
            started_at=started_at,
            completed_at=now_iso,
            status=StatusEnum.FAILED,
            confidence=None,
            error=f"Inference execution failed: {err}",
        )

        raw_case["analysis_status"]["oil_detection"] = StatusEnum.FAILED.value
        gen_results = raw_case.get("data_manifest", {}).get("generated_analysis_results", [])
        gen_results.append(res.model_dump())
        raw_case["data_manifest"]["generated_analysis_results"] = gen_results
        storage.save_case(raw_case)
        return res

    completed_at = datetime.now(timezone.utc).isoformat()

    # Compute SHA256 of output files
    bin_bytes = bin_out_path.read_bytes()
    bin_sha256 = hashlib.sha256(bin_bytes).hexdigest()

    prob_sha256 = None
    if prob_out_path.exists():
        prob_bytes = prob_out_path.read_bytes()
        prob_sha256 = hashlib.sha256(prob_bytes).hexdigest()

    # Register generated output mask record in data_manifest.oil_masks
    oil_mask_record = {
        "output_id": f"mask_{an_id}",
        "analysis_id": an_id,
        "binary_mask_path": str(bin_out_path),
        "probability_mask_path": str(prob_out_path),
        "binary_mask_sha256": bin_sha256,
        "probability_mask_sha256": prob_sha256,
        "oil_fraction": inf_res["oil_fraction"],
        "mean_probability": inf_res["mean_probability"],
        "mean_oil_probability": inf_res["mean_oil_probability"],
        "max_probability": inf_res["max_probability"],
        "threshold": inf_res["threshold"],
        "generated_at": completed_at,
    }
    oil_masks_list = raw_case.get("data_manifest", {}).get("oil_masks", [])
    oil_masks_list.append(oil_mask_record)
    raw_case["data_manifest"]["oil_masks"] = oil_masks_list

    # Complete analysis result (confidence set to None for uncalibrated model)
    res = AnalysisResult(
        analysis_id=an_id,
        case_id=case_id,
        module="oil_detection",
        module_version="1.0.0",
        input_evidence_ids=[sar_evidence["evidence_id"]],
        input_hashes=[sar_evidence.get("sha256", "")],
        configuration={
            "checkpoint_path": str(ckpt_path),
            "checkpoint_sha256": ckpt_sha256,
            "threshold": payload.threshold,
        },
        started_at=started_at,
        completed_at=completed_at,
        status=StatusEnum.COMPLETED,
        confidence=None,
        result={
            "oil_fraction": inf_res["oil_fraction"],
            "mean_probability": inf_res["mean_probability"],
            "mean_oil_probability": inf_res["mean_oil_probability"],
            "max_probability": inf_res["max_probability"],
            "threshold": inf_res["threshold"],
            "binary_mask_path": str(bin_out_path),
            "probability_mask_path": str(prob_out_path),
            "binary_mask_sha256": bin_sha256,
            "probability_mask_sha256": prob_sha256,
            "original_shape": inf_res["original_shape"],
        },
    )

    raw_case["analysis_status"]["oil_detection"] = StatusEnum.COMPLETED.value
    gen_results = raw_case.get("data_manifest", {}).get("generated_analysis_results", [])
    gen_results.append(res.model_dump())
    raw_case["data_manifest"]["generated_analysis_results"] = gen_results

    storage.save_case(raw_case)
    return res
