"""
SAMUDRANETRA — LIVE OPERATIONAL PROTOTYPE ORCHESTRATION TEST SUITE
Tests job manager, GeoTIFF validator, MarineCadastre AIS CSV parser, OpenDrift forecast engine,
and live API orchestration endpoints.
"""

import time
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services.job_manager import job_manager, JobState
from backend.app.services.geotiff_validator import validate_geotiff_raster, GeoTiffValidationError
from backend.app.services.ais_csv_ingestion import parse_marinecadastre_ais_csv, AisCsvValidationError
from backend.app.services.opendrift_forecast_engine import run_opendrift_forward_forecast

client = TestClient(app)
R001_DIR = Path(r"C:\Users\tanvi\OneDrive\Documents\Oil Spill\SamudraNetra-Research\R001_WAKASHIO")


def test_job_manager_lifecycle():
    """Tests job creation, step progress updates, log tracking, and completion."""
    job = job_manager.create_job("TEST_JOB", "R001_WAKASHIO")
    assert job.status == JobState.QUEUED
    assert job.progress_pct == 0.0

    job.update_progress(50.0, "RUNNING_STAGE_1", "Processing stage 1...")
    assert job.progress_pct == 50.0
    assert job.current_step == "RUNNING_STAGE_1"
    assert len(job.logs) == 1

    job.mark_complete({"result": "OK"})
    assert job.status == JobState.COMPLETE
    assert job.progress_pct == 100.0
    assert job.result == {"result": "OK"}


def test_geotiff_validator():
    """Tests GeoTIFF raster validator with valid and corrupt input files."""
    sar_raw_file = R001_DIR / "01_raw_sar" / "subset_4_of_R001_WAKASHIO_20200810_S1B_VV_SIGMA0_DB.dim"
    res = validate_geotiff_raster(str(sar_raw_file))
    assert res["valid"] is True
    assert res["validation_status"].startswith("PASS")

    with pytest.raises(GeoTiffValidationError):
        validate_geotiff_raster("non_existent_file.tif")


def test_ais_csv_ingestion():
    """Tests MarineCadastre AIS CSV log ingestion and validation."""
    ais_file = R001_DIR / "07_results" / "final_qa" / "R001_FINAL_RELEASE_MANIFEST.json"
    
    # Test valid CSV parsing with temporary file
    temp_csv = Path("scratch") / "test_ais_marinecadastre.csv"
    temp_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(temp_csv, "w", encoding="utf-8") as f:
        f.write("MMSI,BaseDateTime,LAT,LON,SOG,COG,Heading,VesselName,IMO,CallSign,VesselType,Status,Length,Width,Draft\n")
        f.write("352000000,2020-08-10T01:00:00Z,-20.40,57.70,12.5,135,135,VESSEL_BETA,IMO9876543,3ABC,Cargo,0,290,45,11.5\n")

    parsed = parse_marinecadastre_ais_csv(str(temp_csv))
    assert parsed["valid"] is True
    assert parsed["unique_vessels_count"] == 1
    assert parsed["total_records_ingested"] == 1

    # Test invalid CSV header
    invalid_csv = Path("scratch") / "test_invalid_ais.csv"
    with open(invalid_csv, "w", encoding="utf-8") as f:
        f.write("INVALID_HEADER1,INVALID_HEADER2\n1,2\n")

    with pytest.raises(AisCsvValidationError):
        parse_marinecadastre_ais_csv(str(invalid_csv))


def test_opendrift_forward_forecast_engine():
    """Tests native OpenDrift forward forecast engine (T0 -> T+48h)."""
    forecast_res = run_opendrift_forward_forecast(
        case_id="R001_WAKASHIO",
        slick_lat=-20.4382,
        slick_lon=57.7432,
        t0_iso="2020-08-10T01:38:07Z",
        forecast_horizons_hours=[6, 12, 24, 48],
        num_particles=100
    )
    assert forecast_res["product_type"] == "FORECAST"
    assert "T+48h" in forecast_res["envelopes"]
    assert "T+48h" in forecast_res["particles"]
    assert len(forecast_res["particles"]["T+48h"]) == 100
    assert forecast_res["forcing_support"]["era5_wind"] == "AVAILABLE_VALIDATED"


def test_api_investigation_creation():
    """Tests POST /api/cases endpoint for benchmark and custom cases."""
    res_bm = client.post("/api/cases", json={"case_type": "BENCHMARK"})
    assert res_bm.status_code == 200
    assert res_bm.json()["case_id"] == "R001_WAKASHIO"

    res_cust = client.post("/api/cases", json={"case_type": "CUSTOM", "case_name": "Test Incident"})
    assert res_cust.status_code == 200
    assert res_cust.json()["case_id"] == "CUSTOM_CASE"


def test_api_slick_detection_job():
    """Tests POST /api/cases/R001_WAKASHIO/detect and job status polling."""
    trig_res = client.post("/api/cases/R001_WAKASHIO/detect")
    assert trig_res.status_code == 200
    job_id = trig_res.json()["job_id"]

    # Poll job status
    time.sleep(0.5)
    poll_res = client.get(f"/api/jobs/{job_id}")
    assert poll_res.status_code == 200
    assert poll_res.json()["job_type"] == "SLICK_DETECTION"


def test_api_forecast_job():
    """Tests POST /api/cases/R001_WAKASHIO/forecast job trigger."""
    trig_res = client.post("/api/cases/R001_WAKASHIO/forecast", json={"scenario": "C"})
    assert trig_res.status_code == 200
    job_id = trig_res.json()["job_id"]
    assert job_id.startswith("JOB_")


def test_api_automated_investigation():
    """Tests POST /api/cases/R001_WAKASHIO/automate end-to-end orchestration job."""
    trig_res = client.post("/api/cases/R001_WAKASHIO/automate")
    assert trig_res.status_code == 200
    job_id = trig_res.json()["job_id"]
    assert job_id.startswith("JOB_")


def test_api_investigation_review():
    """Tests GET /api/cases/R001_WAKASHIO/review 11-stage status matrix."""
    rev_res = client.get("/api/cases/R001_WAKASHIO/review")
    assert rev_res.status_code == 200
    m = rev_res.json()["stages_matrix"]
    assert m["OBSERVATION"]["status"] == "PASS"
    assert m["DETECTION"]["status"] == "PASS"
    assert m["HINDCAST"]["status"] == "PASS"
    assert m["FORECAST"]["status"] == "PASS"
    assert m["VESSEL_PRIORITISATION"]["status"] == "PASS"
    assert m["PROVENANCE"]["status"] == "PASS"
