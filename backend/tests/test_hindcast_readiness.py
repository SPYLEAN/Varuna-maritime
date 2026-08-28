from __future__ import annotations
import datetime
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import cv2
import netCDF4 as nc
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.storage import storage
from backend.app.services.metocean_inspector import inspect_metocean_file, normalize_longitude, normalize_longitude_range
from backend.app.services.hindcast_readiness import evaluate_hindcast_readiness
from ml.src.oiltrace_ml.train import train_model


@pytest.fixture(autouse=True)
def temp_storage(tmp_path):
    original_dir = storage.storage_dir
    storage.storage_dir = tmp_path / "cases"
    storage.storage_dir.mkdir(parents=True, exist_ok=True)
    yield
    storage.storage_dir = original_dir


client = TestClient(app)


def _create_synthetic_netcdf(
    out_path: Path,
    lats: np.ndarray,
    lons: np.ndarray,
    times_utc: List[str],
    has_currents: bool = True,
    has_wind: bool = False,
):
    with nc.Dataset(str(out_path), "w", format="NETCDF4") as ds:
        ds.createDimension("lat", len(lats))
        ds.createDimension("lon", len(lons))
        ds.createDimension("time", len(times_utc))

        v_lat = ds.createVariable("lat", "f4", ("lat",))
        v_lon = ds.createVariable("lon", "f4", ("lon",))
        v_time = ds.createVariable("time", "f8", ("time",))

        v_lat[:] = lats
        v_lon[:] = lons
        v_time.units = "seconds since 1970-01-01 00:00:00"

        timestamps = [
            datetime.datetime.fromisoformat(t.replace("Z", "+00:00")).timestamp()
            for t in times_utc
        ]
        v_time[:] = timestamps

        if has_currents:
            u_curr = ds.createVariable("u_current", "f4", ("time", "lat", "lon"))
            v_curr = ds.createVariable("v_current", "f4", ("time", "lat", "lon"))
            u_curr[:, :, :] = np.ones((len(times_utc), len(lats), len(lons))) * 0.2
            v_curr[:, :, :] = np.ones((len(times_utc), len(lats), len(lons))) * -0.1

        if has_wind:
            u_w = ds.createVariable("u_wind", "f4", ("time", "lat", "lon"))
            v_w = ds.createVariable("v_wind", "f4", ("time", "lat", "lon"))
            u_w[:, :, :] = np.ones((len(times_utc), len(lats), len(lons))) * 5.0
            v_w[:, :, :] = np.ones((len(times_utc), len(lats), len(lons))) * 3.0


def test_longitude_normalization_conventions():
    assert normalize_longitude(0.0) == 0.0
    assert normalize_longitude(180.0) == 180.0
    assert normalize_longitude(-180.0) == -180.0
    assert normalize_longitude(287.5) == -72.5
    assert normalize_longitude(350.0) == -10.0
    assert normalize_longitude(72.8) == 72.8

    lons_0_360 = [287.0, 289.0]
    lmin, lmax = normalize_longitude_range(lons_0_360)
    assert lmin == -73.0
    assert lmax == -71.0


def test_synthetic_csv_metocean_inspection(tmp_path):
    csv_path = tmp_path / "synthetic_currents.csv"
    content = "time,latitude,longitude,u_current,v_current\n"
    content += "2026-08-27T00:00:00Z,18.5,72.5,0.15,-0.05\n"
    content += "2026-08-27T12:00:00Z,19.5,73.5,0.20,-0.10\n"
    csv_path.write_text(content)

    meta = inspect_metocean_file(csv_path)
    assert "u_current" in meta.detected_components
    assert "v_current" in meta.detected_components
    assert meta.lat_min == 18.5
    assert meta.lat_max == 19.5
    assert meta.lon_min == 72.5
    assert meta.lon_max == 73.5
    assert meta.time_start_utc == "2026-08-27T00:00:00Z"
    assert meta.time_end_utc == "2026-08-27T12:00:00Z"


def test_non_georeferenced_spill_rejection_in_readiness(tmp_path):
    # 1. Create case with non-georeferenced benchmark SAR image
    res_c = client.post("/cases", json={"name": "PNG Benchmark Case", "observation_timestamp": "2026-08-27T12:00:00Z"})
    case_id = res_c.json()["case_id"]

    png_bytes = cv2.imencode(".png", np.ones((64, 64), dtype=np.uint8) * 128)[1].tobytes()
    res_ev = client.post(f"/cases/{case_id}/evidence", files={"file": ("bench_sar.png", png_bytes, "image/png")}, data={"evidence_type": "sar_image"})
    sar_ev_id = res_ev.json()["evidence_id"]

    # Dummy U-Net checkpoint (at least 2 samples)
    dummy_img_dir = tmp_path / "dummy_png"
    dummy_img_dir.mkdir(parents=True, exist_ok=True)
    for i in range(2):
        cv2.imwrite(str(dummy_img_dir / f"s_{i}.png"), np.zeros((32, 32), dtype=np.uint8))
        cv2.imwrite(str(dummy_img_dir / f"m_{i}.png"), np.zeros((32, 32), dtype=np.uint8))

    ckpt_path = dummy_img_dir / "m.pt"
    train_model(images_dir=dummy_img_dir, masks_dir=dummy_img_dir, epochs=1, batch_size=2, image_size=32, out_path=ckpt_path, seed=42)

    res_oil = client.post(f"/cases/{case_id}/analysis/oil-detection", json={"checkpoint_path": str(ckpt_path), "sar_evidence_id": sar_ev_id})
    oil_an_id = res_oil.json()["analysis_id"]

    client.post(f"/cases/{case_id}/analysis/spill-geometry", json={"oil_detection_analysis_id": oil_an_id})

    # Run Hindcast Readiness
    res_read = client.post(f"/cases/{case_id}/analysis/hindcast-readiness", json={"hindcast_hours": 12})
    assert res_read.status_code == 200
    rdata = res_read.json()

    assert rdata["status"] == "insufficient_data"
    assert rdata["confidence"] is None
    assert rdata["result"]["ready_for_hindcast"] is False
    assert "missing_georeferencing" in rdata["result"]["reasons"]
    assert "Hindcasting requires georeferenced spill geometry." in rdata["warnings"][0]


def test_missing_observation_time_rejection(tmp_path):
    res_c = client.post("/cases", json={"name": "No Obs Time Case"})
    case_id = res_c.json()["case_id"]

    res_read = client.post(f"/cases/{case_id}/analysis/hindcast-readiness", json={})
    assert res_read.status_code == 200
    rdata = res_read.json()

    assert rdata["status"] == "insufficient_data"
    assert "missing_spill_geometry" in rdata["result"]["reasons"]


def test_temporal_and_spatial_coverage_validation(tmp_path):
    # 1. Create artificial georeferenced GeoTIFF SAR pass at (18.9 N, 72.8 E)
    tif_path = tmp_path / "geo_sar.tif"
    transform = from_origin(72.7, 19.0, 0.002, 0.002)
    arr = (np.random.rand(100, 100) * 255).astype(np.uint8)

    with rasterio.open(
        tif_path,
        "w",
        driver="GTiff",
        height=100,
        width=100,
        count=1,
        dtype=arr.dtype,
        crs="EPSG:4326",
        transform=transform,
    ) as dst:
        dst.write(arr, 1)

    res_c = client.post("/cases", json={"name": "Georeferenced Case", "observation_timestamp": "2026-08-27T12:00:00Z"})
    case_id = res_c.json()["case_id"]

    tif_bytes = tif_path.read_bytes()
    res_ev = client.post(f"/cases/{case_id}/evidence", files={"file": ("geo_sar.tif", tif_bytes, "image/tiff")}, data={"evidence_type": "sar_image"})
    sar_ev_id = res_ev.json()["evidence_id"]

    # Run Oil Detection & Spill Geometry (2 samples for dummy U-Net training)
    dummy_img_dir = tmp_path / "dummy_geo"
    dummy_img_dir.mkdir(parents=True, exist_ok=True)
    for i in range(2):
        cv2.imwrite(str(dummy_img_dir / f"s_{i}.png"), np.zeros((32, 32), dtype=np.uint8))
        cv2.imwrite(str(dummy_img_dir / f"m_{i}.png"), np.zeros((32, 32), dtype=np.uint8))

    ckpt_path = dummy_img_dir / "m.pt"
    train_model(images_dir=dummy_img_dir, masks_dir=dummy_img_dir, epochs=1, batch_size=2, image_size=32, out_path=ckpt_path, seed=42)

    res_oil = client.post(f"/cases/{case_id}/analysis/oil-detection", json={"checkpoint_path": str(ckpt_path), "sar_evidence_id": sar_ev_id})
    oil_an_id = res_oil.json()["analysis_id"]

    client.post(f"/cases/{case_id}/analysis/spill-geometry", json={"oil_detection_analysis_id": oil_an_id})

    # Test A: Missing currents and wind
    res_r1 = client.post(f"/cases/{case_id}/analysis/hindcast-readiness", json={"hindcast_hours": 12})
    r1 = res_r1.json()
    assert r1["status"] == "insufficient_data"
    assert "missing_current_data" in r1["result"]["reasons"]
    assert "missing_wind_data" in r1["result"]["reasons"]

    # Test B: Add Ocean Current NetCDF with temporal gap (only 08:00..12:00, missing 00:00..08:00)
    curr_nc_path = tmp_path / "ocean_currents_short.nc"
    _create_synthetic_netcdf(
        curr_nc_path,
        lats=np.linspace(18.0, 20.0, 5),
        lons=np.linspace(72.0, 74.0, 5),
        times_utc=["2026-08-27T08:00:00Z", "2026-08-27T12:00:00Z"],
        has_currents=True,
    )
    client.post(f"/cases/{case_id}/evidence", files={"file": ("currents.nc", curr_nc_path.read_bytes(), "application/x-netcdf")}, data={"evidence_type": "ocean_current"})

    res_r2 = client.post(f"/cases/{case_id}/analysis/hindcast-readiness", json={"hindcast_hours": 12})
    r2 = res_r2.json()
    assert "current_temporal_gap" in r2["result"]["reasons"]

    # Test C: Add Complete Ocean Current + Wind NetCDF covering [00:00 .. 12:00]
    full_nc_path = tmp_path / "metocean_full.nc"
    _create_synthetic_netcdf(
        full_nc_path,
        lats=np.linspace(18.0, 20.0, 5),
        lons=np.linspace(72.0, 74.0, 5),
        times_utc=["2026-08-27T00:00:00Z", "2026-08-27T06:00:00Z", "2026-08-27T12:00:00Z"],
        has_currents=True,
        has_wind=True,
    )
    client.post(f"/cases/{case_id}/evidence", files={"file": ("metocean_full.nc", full_nc_path.read_bytes(), "application/x-netcdf")}, data={"evidence_type": "met_ocean"})

    # Check Readiness (12 hours hindcast from 12:00 -> required 00:00 to 12:00)
    res_r3 = client.post(f"/cases/{case_id}/analysis/hindcast-readiness", json={"hindcast_hours": 12})
    r3 = res_r3.json()

    assert r3["status"] == "completed"
    assert r3["confidence"] is None
    assert r3["result"]["ready_for_hindcast"] is True
    assert r3["result"]["reasons"] == []
    assert r3["result"]["environmental_coverage"]["ocean_current"]["spatial_coverage"] is True
    assert r3["result"]["environmental_coverage"]["ocean_current"]["temporal_coverage"] is True
    assert r3["result"]["environmental_coverage"]["wind"]["spatial_coverage"] is True
    assert r3["result"]["environmental_coverage"]["wind"]["temporal_coverage"] is True
