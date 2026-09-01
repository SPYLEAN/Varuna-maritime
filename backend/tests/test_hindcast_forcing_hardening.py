import json
import math
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
import xarray as xr

from backend.app.services.hindcast_forcing_hardening import (
    haversine_distance_m,
    trace_sar_acquisition_provenance,
    audit_hycom_wet_cell_offsets,
    audit_hycom_depth_sensitivity,
    audit_temporal_forcing_stability,
    inspect_cmems_wave_metadata,
    extract_stokes_wave_context,
    audit_96h_hindcast_coverage,
    generate_opendrift_reader_mapping,
    run_r001_hindcast_forcing_hardening_pipeline,
    MAX_PERMITTED_WET_CELL_OFFSET_M,
)


def test_haversine_distance_measurement():
    # Distance between Mauritius (-20.23, 57.70) and nearby point (-20.23, 57.71)
    # 0.01 deg lon at 20 deg S is approx 1045 meters
    d_m = haversine_distance_m(-20.23, 57.70, -20.23, 57.71)
    assert 1000.0 < d_m < 1100.0

    # Distance to self must be 0
    assert haversine_distance_m(-20.23, 57.70, -20.23, 57.70) == 0.0


def test_sar_provenance_tracing():
    r001_p = Path(r"C:\Users\tanvi\OneDrive\Documents\Oil Spill\SamudraNetra-Research\R001_WAKASHIO")
    prov = trace_sar_acquisition_provenance(r001_p)

    assert prov["satellite"] == "Sentinel-1B"
    assert prov["acquisition_timestamp_utc"] == "2020-08-10T01:37:55Z"
    assert prov["provenance_status"] == "PASS"


def test_max_offset_rejection_and_support():
    r001_p = Path(r"C:\Users\tanvi\OneDrive\Documents\Oil Spill\SamudraNetra-Research\R001_WAKASHIO")
    hycom_path = r001_p / "04_currents_hycom" / "uv3z_2020 (1).nc4"
    ds_hycom = xr.open_dataset(hycom_path)

    cand_rows = [
        {"candidate_id": "C001", "centroid_lat": -20.25, "centroid_lon": 57.94},  # Normal valid ocean
        {"candidate_id": "C_FAR", "centroid_lat": -10.00, "centroid_lon": 40.00}, # Far out of grid domain
    ]

    target_dt = pd.Timestamp("2020-08-10 01:37:55")
    hycom_meta = {
        "u_var": "water_u", "v_var": "water_v", "lat_name": "lat", "lon_name": "lon",
        "time_name": "time", "depth_name": "depth",
    }

    offset_rows, summary = audit_hycom_wet_cell_offsets(
        ds_hycom, cand_rows, target_dt, hycom_meta, max_permitted_offset_m=10000.0
    )

    ds_hycom.close()

    assert len(offset_rows) == 2
    assert offset_rows[0]["current_status"] == "VALID"
    assert offset_rows[1]["current_status"] == "INSUFFICIENT_SPATIAL_SUPPORT"
    assert summary["insufficient_spatial_support_count"] == 1


def test_cmems_variable_discovery_and_stokes_alignment():
    r001_p = Path(r"C:\Users\tanvi\OneDrive\Documents\Oil Spill\SamudraNetra-Research\R001_WAKASHIO")
    cmems_meta = inspect_cmems_wave_metadata(r001_p / "05_waves_cmems")

    assert cmems_meta["status"] == "AVAILABLE"
    assert cmems_meta["u_stokes_var"] == "VSDX"
    assert cmems_meta["v_stokes_var"] == "VSDY"
    assert cmems_meta["swh_var"] == "VHM0"

    cand_rows = [{"candidate_id": "C001", "centroid_lat": -20.25, "centroid_lon": 57.94}]
    target_dt = pd.Timestamp("2020-08-10 01:37:55")
    ds_cmems = xr.open_dataset(cmems_meta["file_path"])

    stokes_rows = extract_stokes_wave_context(ds_cmems, cand_rows, target_dt, cmems_meta)
    ds_cmems.close()

    assert len(stokes_rows) == 1
    assert stokes_rows[0]["stokes_speed_mps"] > 0.0
    assert stokes_rows[0]["significant_wave_height_m"] > 0.0


def test_opendrift_reader_mapping():
    era5_meta = {"file": "era5.nc", "u_var": "u10", "v_var": "v10"}
    hycom_meta = {"file": "hycom.nc", "u_var": "water_u", "v_var": "water_v"}
    cmems_meta = {"file": "cmems.nc", "status": "AVAILABLE", "u_stokes_var": "VSDX", "v_stokes_var": "VSDY", "swh_var": "VHM0"}

    mapping = generate_opendrift_reader_mapping(era5_meta, hycom_meta, cmems_meta)

    assert mapping["reader_readiness_status"] == "PASS"
    assert mapping["era5_reader"]["variable_mapping"]["u10"] == "x_wind"
    assert mapping["hycom_reader"]["variable_mapping"]["water_u"] == "x_sea_water_velocity"
    assert mapping["cmems_reader"]["variable_mapping"]["VSDX"] == "sea_surface_wave_stokes_drift_x_velocity"


def test_full_hindcast_forcing_hardening_pipeline(tmp_path):
    r001_p = Path(r"C:\Users\tanvi\OneDrive\Documents\Oil Spill\SamudraNetra-Research\R001_WAKASHIO")
    out_d = tmp_path / "hindcast_out"

    res = run_r001_hindcast_forcing_hardening_pipeline(r001_p, out_d)

    assert res["status"] == "PASS"
    assert res["provenance_status"] == "PASS"
    assert res["era5_96h_coverage"] == "PASS"
    assert res["hycom_96h_coverage"] == "PASS"
    assert res["cmems_96h_coverage"] == "PASS"
    assert res["ground_truth_accessed"] is False
    assert res["task009b_ready"] is True

    assert (out_d / "R001_HINDCAST_FORCING_AUDIT.json").exists()
    assert (out_d / "R001_HINDCAST_FORCING_AUDIT.md").exists()
    assert (out_d / "R001_HYCOM_WET_CELL_OFFSETS.csv").exists()
    assert (out_d / "R001_DEPTH_SENSITIVITY.csv").exists()
    assert (out_d / "R001_TEMPORAL_FORCING_STABILITY.csv").exists()
    assert (out_d / "R001_STOKES_CONTEXT.csv").exists()
    assert (out_d / "R001_OPENDRIFT_READER_MAP.json").exists()
