from __future__ import annotations

from pathlib import Path
import pytest

from backend.app.services.hindcast_execution_audit import audit_task009b_execution

R001_DIR = Path(r"C:\Users\tanvi\OneDrive\Documents\Oil Spill\SamudraNetra-Research\R001_WAKASHIO")


def test_audit_task009b_execution():
    """Verify execution authenticity and numerical adequacy audit on R001 Wakashio hindcast outputs."""
    audit = audit_task009b_execution(R001_DIR)

    assert audit["audit_status"] == "COMPLETED"
    assert audit["trajectory_engine"]["opendrift_execution"] == "NO"
    assert audit["trajectory_engine"]["model_class"] == "VectorTransportEngine"
    assert audit["negative_time_audit"]["time_progression_truly_backward"] is True
    assert audit["negative_time_audit"]["integration_timestep_seconds"] == -1800
    assert audit["windage_audit"]["windage_status"] == "JUSTIFIED_PARAMETER"
    assert audit["stokes_audit"]["double_counting"] == "YES"
    assert audit["forcing_audit"]["time_varying_forcing_verified"] is True
    assert audit["blindness_audit"]["blindness_scan_status"] == "PASS"

    h_dir = R001_DIR / "07_results" / "hindcast"
    assert (h_dir / "R001_TASK009B_EXECUTION_AUDIT.json").exists()
    assert (h_dir / "R001_TASK009B_EXECUTION_AUDIT.md").exists()


def test_engine_identification_and_proof():
    """Verify trajectory engine identification and runtime path proof."""
    audit = audit_task009b_execution(R001_DIR)
    eng = audit["trajectory_engine"]
    proof = audit["runtime_proof"]

    assert "VectorTransportEngine" in eng["model_class"]
    assert proof["code_path_verified"] is True
    assert len(proof["executed_imports"]) > 0


def test_stokes_double_counting_audit():
    """Verify Stokes drift double-counting detection when 3% windage is combined with explicit Stokes drift."""
    audit = audit_task009b_execution(R001_DIR)
    stokes = audit["stokes_audit"]

    assert stokes["explicit_stokes_reader"] == "YES"
    assert stokes["implicit_stokes_in_3percent_windage"] == "YES"
    assert stokes["double_counting"] == "YES"
