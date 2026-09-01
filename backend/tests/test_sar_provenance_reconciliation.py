import json
from pathlib import Path
import pytest

from backend.app.services.sar_provenance_reconciliation import (
    reconcile_sar_provenance,
    run_sar_provenance_reconciliation_pipeline,
    PRODUCT_A_ID,
    PRODUCT_B_ID,
)


def test_sar_provenance_reconciliation_actual_r001():
    r001_p = Path(r"C:\Users\tanvi\OneDrive\Documents\Oil Spill\SamudraNetra-Research\R001_WAKASHIO")
    rec = reconcile_sar_provenance(r001_p)

    assert rec["authoritative_raw_product_id"] == PRODUCT_A_ID
    assert rec["product_a_status"] == "MATCH"
    assert rec["product_b_status"] == "NO MATCH"
    assert rec["product_b_superseded"] is True
    assert rec["processed_vv_lineage"] == "VERIFIED"
    assert rec["processed_vh_lineage"] == "VERIFIED"
    assert rec["scene_start_time_utc"] == "2020-08-10T01:37:55Z"
    assert rec["scene_stop_time_utc"] == "2020-08-10T01:38:20Z"
    assert rec["scene_midpoint_time_utc"] == "2020-08-10T01:38:07.500Z"
    assert rec["observation_timestamp_used_for_physics"] == "2020-08-10T01:38:07.500Z"
    assert rec["hycom_vertical_sensitivity"] == "NOT_APPLICABLE_SINGLE_LAYER"
    assert rec["hycom_vertical_sensitivity_available"] is False
    assert rec["status"] == "PASS"


def test_ambiguous_or_missing_product_lineage(tmp_path):
    # Dummy directory with no matching SAR product
    rec = reconcile_sar_provenance(tmp_path)

    assert rec["authoritative_raw_product_id"] == "AMBIGUOUS"
    assert rec["product_a_status"] == "UNKNOWN"
    assert rec["product_b_status"] == "UNKNOWN"
    assert rec["status"] == "BLOCKED_PROVENANCE"
    assert rec["task009b_ready"] is False


def test_pipeline_execution_and_deliverables(tmp_path):
    r001_p = Path(r"C:\Users\tanvi\OneDrive\Documents\Oil Spill\SamudraNetra-Research\R001_WAKASHIO")
    out_d = tmp_path / "provenance_out"

    res = run_sar_provenance_reconciliation_pipeline(r001_p, out_d)

    assert res["status"] == "PASS"
    assert res["task009b_ready"] is True
    assert (out_d / "R001_SAR_PROVENANCE_RECONCILIATION.json").exists()
    assert (out_d / "R001_SAR_PROVENANCE_RECONCILIATION.md").exists()
