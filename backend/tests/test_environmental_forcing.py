import json
import math
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
import xarray as xr

from backend.app.services.environmental_forcing import (
    verify_acquisition_timestamp,
    inspect_era5_metadata,
    inspect_hycom_metadata,
    extract_forcing_at_point,
    compute_relative_vectors,
    assign_physical_context_labels,
    run_r001_environmental_forcing_pipeline,
    DEFAULT_CONFIG,
)


def test_acquisition_timestamp_verification():
    r001_p = Path(r"C:\Users\tanvi\OneDrive\Documents\Oil Spill\SamudraNetra-Research\R001_WAKASHIO")
    res = verify_acquisition_timestamp(r001_p)

    assert res["acquisition_timestamp_utc"] == "2020-08-10T01:37:55Z"
    assert res["acquisition_date"] == "2020-08-10"
    assert abs(res["acquisition_hour"] - 1.63194) < 1e-3
    assert "source_metadata" in res


def test_era5_variable_discovery():
    r001_p = Path(r"C:\Users\tanvi\OneDrive\Documents\Oil Spill\SamudraNetra-Research\R001_WAKASHIO")
    meta = inspect_era5_metadata(r001_p / "03_wind_era5")

    assert meta["u_var"] == "u10"
    assert meta["v_var"] == "v10"
    assert meta["units"] == "m s**-1"
    assert meta["lat_name"] == "latitude"
    assert meta["lon_name"] == "longitude"


def test_hycom_variable_discovery():
    r001_p = Path(r"C:\Users\tanvi\OneDrive\Documents\Oil Spill\SamudraNetra-Research\R001_WAKASHIO")
    meta = inspect_hycom_metadata(r001_p / "04_currents_hycom" / "uv3z_2020 (1).nc4")

    assert meta["u_var"] == "water_u"
    assert meta["v_var"] == "water_v"
    assert meta["shallowest_depth_m"] == 0.0
    assert meta["lat_name"] == "lat"
    assert meta["lon_name"] == "lon"


def test_out_of_domain_detection(tmp_path):
    # Create tiny dummy dataset
    lats = np.array([-20.0, -19.0])
    lons = np.array([57.0, 58.0])
    times = pd.date_range("2020-08-10 00:00", "2020-08-10 03:00", freq="1h")

    ds = xr.Dataset(
        data_vars={
            "u10": (("time", "latitude", "longitude"), np.ones((4, 2, 2)), {"units": "m s**-1"}),
            "v10": (("time", "latitude", "longitude"), np.ones((4, 2, 2)), {"units": "m s**-1"}),
        },
        coords={"time": times, "latitude": lats, "longitude": lons},
    )

    u, v, status = extract_forcing_at_point(
        ds, "u10", "v10", -25.0, 57.5, pd.Timestamp("2020-08-10 01:00")
    )
    assert status == "OUT_OF_DOMAIN"

    u_in, v_in, status_in = extract_forcing_at_point(
        ds, "u10", "v10", -19.5, 57.5, pd.Timestamp("2020-08-10 01:00")
    )
    assert status_in == "VALID"
    assert u_in == 1.0 and v_in == 1.0


def test_vector_calculations_and_angle():
    # Wind blowing towards North (u=0, v=10 m/s), Current flowing towards North (u=0, v=1 m/s)
    # Wind-current angle should be 0 deg (aligned)
    res_aligned = compute_relative_vectors(0.0, 10.0, 0.0, 1.0)
    assert abs(res_aligned["wind_current_angle_deg"] - 0.0) < 1e-2
    assert abs(res_aligned["current_wind_speed_ratio"] - 0.1) < 1e-3

    # Wind blowing North (u=0, v=10), Current flowing East (u=1, v=0) -> 90 deg (crossing)
    res_cross = compute_relative_vectors(0.0, 10.0, 1.0, 0.0)
    assert abs(res_cross["wind_current_angle_deg"] - 90.0) < 1e-2

    labels = assign_physical_context_labels(res_aligned, DEFAULT_CONFIG)
    assert "STRONG_WIND" in labels or "MODERATE_WIND" in labels
    assert "WIND_CURRENT_ALIGNED" in labels


def test_no_ground_truth_or_vessel_usage():
    assert DEFAULT_CONFIG["ground_truth_accessed"] is False
    assert DEFAULT_CONFIG["historical_vessel_accessed"] is False


def test_full_pipeline_execution(tmp_path):
    r001_p = Path(r"C:\Users\tanvi\OneDrive\Documents\Oil Spill\SamudraNetra-Research\R001_WAKASHIO")
    out_d = tmp_path / "env_out"

    res = run_r001_environmental_forcing_pipeline(r001_p, out_d)

    assert res["status"] == "PASS"
    assert res["primary_candidates"] == 45
    assert res["wind_coverage"] == 45
    assert res["current_coverage"] == 45
    assert res["spatial_alignment"] == "PASS"
    assert res["temporal_alignment"] == "PASS"
    assert res["vector_validation"] == "PASS"
    assert res["ground_truth_accessed"] is False

    assert (out_d / "R001_ENVIRONMENTAL_FORCING.csv").exists()
    assert (out_d / "R001_ENVIRONMENTAL_FORCING.json").exists()
    assert (out_d / "R001_FORCING_ALIGNMENT_AUDIT.json").exists()
    assert (out_d / "R001_WIND_CONTEXT_MAP.png").exists()
    assert (out_d / "R001_CURRENT_CONTEXT_MAP.png").exists()
