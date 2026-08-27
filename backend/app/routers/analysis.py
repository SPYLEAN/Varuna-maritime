from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import uuid
from typing import Optional
from fastapi import APIRouter, HTTPException, status
from ..schemas import AnalysisResult, OilDetectionRequest, SpillGeometryRequest, StatusEnum
from ..storage import storage
from ..services.spill_geometry import analyze_spill_geometry
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
    if payload.checkpoint_path:
        ckpt_path = Path(payload.checkpoint_path)
    else:
        v0_path = Path("models/oil_detection/samudranetra_oilseg_v0.pt")
        default_path = Path("models/oiltrace_unet.pt")
        if v0_path.exists():
            ckpt_path = v0_path
        elif default_path.exists():
            ckpt_path = default_path
        else:
            ckpt_path = v0_path

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


@router.post("/spill-geometry", response_model=AnalysisResult)
def run_spill_geometry_analysis(case_id: str, payload: Optional[SpillGeometryRequest] = None) -> AnalysisResult:
    if payload is None:
        payload = SpillGeometryRequest()

    raw_case = storage.get_case(case_id)
    if not raw_case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case '{case_id}' not found",
        )

    an_id = f"an_{uuid.uuid4().hex[:8]}"
    started_at = datetime.now(timezone.utc).isoformat()
    gen_results = raw_case.get("data_manifest", {}).get("generated_analysis_results", [])

    # Locate target completed oil_detection analysis result
    target_oil_an = None
    if payload.oil_detection_analysis_id:
        for res_item in gen_results:
            if res_item.get("analysis_id") == payload.oil_detection_analysis_id and res_item.get("module") == "oil_detection" and res_item.get("status") == "completed":
                target_oil_an = res_item
                break
    else:
        # Pick latest completed oil_detection analysis
        completed_oil_ans = [r for r in gen_results if r.get("module") == "oil_detection" and r.get("status") == "completed"]
        if completed_oil_ans:
            target_oil_an = completed_oil_ans[-1]

    # Handle missing prerequisite completed oil_detection analysis
    if not target_oil_an or not target_oil_an.get("result", {}).get("binary_mask_path"):
        now_iso = datetime.now(timezone.utc).isoformat()
        res = AnalysisResult(
            analysis_id=an_id,
            case_id=case_id,
            module="spill_geometry",
            module_version="1.0.0",
            configuration={
                "oil_detection_analysis_id": payload.oil_detection_analysis_id,
                "min_component_size_pixels": payload.min_component_size_pixels,
            },
            started_at=started_at,
            completed_at=now_iso,
            status=StatusEnum.INSUFFICIENT_DATA,
            confidence=None,
            warnings=["No completed oil detection analysis found for this case. Run oil-detection analysis first."],
            error="Missing required completed oil_detection analysis",
        )

        if "analysis_status" not in raw_case:
            raw_case["analysis_status"] = {}
        raw_case["analysis_status"]["spill_geometry"] = StatusEnum.INSUFFICIENT_DATA.value

        gen_results.append(res.model_dump())
        raw_case["data_manifest"]["generated_analysis_results"] = gen_results
        storage.save_case(raw_case)
        return res

    oil_res_dict = target_oil_an["result"]
    bin_mask_path = Path(oil_res_dict["binary_mask_path"])

    if not bin_mask_path.exists():
        now_iso = datetime.now(timezone.utc).isoformat()
        res = AnalysisResult(
            analysis_id=an_id,
            case_id=case_id,
            module="spill_geometry",
            module_version="1.0.0",
            source_analysis_id=target_oil_an["analysis_id"],
            configuration={
                "source_oil_detection_analysis_id": target_oil_an["analysis_id"],
                "min_component_size_pixels": payload.min_component_size_pixels,
            },
            started_at=started_at,
            completed_at=now_iso,
            status=StatusEnum.INSUFFICIENT_DATA,
            confidence=None,
            warnings=[f"Oil detection binary mask file missing on disk: '{bin_mask_path}'."],
            error=f"Binary mask file not found: {bin_mask_path}",
        )

        raw_case["analysis_status"]["spill_geometry"] = StatusEnum.INSUFFICIENT_DATA.value
        gen_results.append(res.model_dump())
        raw_case["data_manifest"]["generated_analysis_results"] = gen_results
        storage.save_case(raw_case)
        return res

    # Locate source SAR image evidence
    evidence_list = raw_case.get("data_manifest", {}).get("evidence", [])
    sar_ev = None
    input_ev_id = target_oil_an.get("input_evidence_ids", [None])[0]
    if input_ev_id:
        for ev in evidence_list:
            if ev.get("evidence_id") == input_ev_id:
                sar_ev = ev
                break
    if not sar_ev:
        sar_candidates = [ev for ev in evidence_list if ev.get("evidence_type") == "sar_image"]
        if sar_candidates:
            sar_ev = sar_candidates[-1]

    if not sar_ev or not Path(sar_ev.get("stored_path", "")).exists():
        now_iso = datetime.now(timezone.utc).isoformat()
        res = AnalysisResult(
            analysis_id=an_id,
            case_id=case_id,
            module="spill_geometry",
            module_version="1.0.0",
            source_analysis_id=target_oil_an["analysis_id"],
            configuration={
                "source_oil_detection_analysis_id": target_oil_an["analysis_id"],
                "min_component_size_pixels": payload.min_component_size_pixels,
            },
            started_at=started_at,
            completed_at=now_iso,
            status=StatusEnum.INSUFFICIENT_DATA,
            confidence=None,
            warnings=["Source SAR image evidence file missing for spill geometry analysis."],
            error="Source SAR image file not found on disk",
        )

        raw_case["analysis_status"]["spill_geometry"] = StatusEnum.INSUFFICIENT_DATA.value
        gen_results.append(res.model_dump())
        raw_case["data_manifest"]["generated_analysis_results"] = gen_results
        storage.save_case(raw_case)
        return res

    sar_path = Path(sar_ev["stored_path"])
    outputs_dir = storage.get_case_outputs_dir(case_id)
    overlay_path = outputs_dir / f"spill_geometry_overlay_{an_id}.png"
    geom_json_path = outputs_dir / f"spill_geometry_{an_id}.json"
    geojson_path = outputs_dir / f"spill_geometry_{an_id}.geojson"

    # Set status running
    raw_case["analysis_status"]["spill_geometry"] = StatusEnum.RUNNING.value
    storage.save_case(raw_case)

    # 4. Run Spill Geometry Engine
    try:
        geom_summary, geojson_dict, overlay_str = analyze_spill_geometry(
            binary_mask_path=bin_mask_path,
            source_image_path=sar_path,
            overlay_out_path=overlay_path,
            min_component_size_pixels=payload.min_component_size_pixels,
        )

        # Save JSON geometry output
        geom_json_path.write_text(json.dumps(geom_summary, indent=2))
        geom_json_sha256 = hashlib.sha256(geom_json_path.read_bytes()).hexdigest()

        # Save GeoJSON if georeferenced
        geojson_sha256 = None
        geojson_out_str = None
        if geojson_dict is not None:
            geojson_path.write_text(json.dumps(geojson_dict, indent=2))
            geojson_sha256 = hashlib.sha256(geojson_path.read_bytes()).hexdigest()
            geojson_out_str = str(geojson_path)

        overlay_sha256 = hashlib.sha256(overlay_path.read_bytes()).hexdigest()

    except Exception as err:
        now_iso = datetime.now(timezone.utc).isoformat()
        res = AnalysisResult(
            analysis_id=an_id,
            case_id=case_id,
            module="spill_geometry",
            module_version="1.0.0",
            source_analysis_id=target_oil_an["analysis_id"],
            configuration={
                "source_oil_detection_analysis_id": target_oil_an["analysis_id"],
                "min_component_size_pixels": payload.min_component_size_pixels,
            },
            started_at=started_at,
            completed_at=now_iso,
            status=StatusEnum.FAILED,
            confidence=None,
            error=f"Spill geometry calculation failed: {err}",
        )

        raw_case["analysis_status"]["spill_geometry"] = StatusEnum.FAILED.value
        gen_results.append(res.model_dump())
        raw_case["data_manifest"]["generated_analysis_results"] = gen_results
        storage.save_case(raw_case)
        return res

    completed_at = datetime.now(timezone.utc).isoformat()

    # Complete analysis result
    res_dict = {
        "source_oil_detection_analysis_id": target_oil_an["analysis_id"],
        "source_binary_mask_sha256": oil_res_dict.get("binary_mask_sha256"),
        "georeferenced": geom_summary["georeferenced"],
        "source_crs": geom_summary["source_crs"],
        "area_calculation_method": geom_summary["area_calculation_method"],
        "total_area_m2": geom_summary["total_area_m2"],
        "total_area_km2": geom_summary["total_area_km2"],
        "geographic_centroid": geom_summary["geographic_centroid"],
        "scene_level_statistics": geom_summary["scene_level_statistics"],
        "components": geom_summary["components"],
        "contour_overlay_path": overlay_str,
        "contour_overlay_sha256": overlay_sha256,
        "geometry_json_path": str(geom_json_path),
        "geometry_json_sha256": geom_json_sha256,
        "geojson_path": geojson_out_str,
        "geojson_sha256": geojson_sha256,
    }

    res = AnalysisResult(
        analysis_id=an_id,
        case_id=case_id,
        module="spill_geometry",
        module_version="1.0.0",
        input_evidence_ids=[sar_ev["evidence_id"]],
        input_hashes=[sar_ev.get("sha256", "")],
        configuration={
            "source_oil_detection_analysis_id": target_oil_an["analysis_id"],
            "source_binary_mask_sha256": oil_res_dict.get("binary_mask_sha256"),
            "min_component_size_pixels": payload.min_component_size_pixels,
        },
        started_at=started_at,
        completed_at=completed_at,
        status=StatusEnum.COMPLETED,
        confidence=None,
        result=res_dict,
    )

    raw_case["analysis_status"]["spill_geometry"] = StatusEnum.COMPLETED.value
    gen_results.append(res.model_dump())
    raw_case["data_manifest"]["generated_analysis_results"] = gen_results

    storage.save_case(raw_case)
    return res
