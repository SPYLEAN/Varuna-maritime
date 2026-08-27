import hashlib
import json
from pathlib import Path
import cv2
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.storage import storage
from backend.app.services.spill_geometry import analyze_spill_geometry
from ml.src.oiltrace_ml.train import train_model


@pytest.fixture(autouse=True)
def temp_storage(tmp_path):
    original_dir = storage.storage_dir
    storage.storage_dir = tmp_path / "cases"
    storage.storage_dir.mkdir(parents=True, exist_ok=True)
    yield
    storage.storage_dir = original_dir


client = TestClient(app)


def test_single_rectangular_component(tmp_path):
    mask = np.zeros((100, 100), dtype=np.uint8)
    mask[20:40, 10:50] = 255  # 20 rows x 40 cols = 800 pixels

    mask_path = tmp_path / "single_rect_mask.png"
    sar_path = tmp_path / "sar_dummy.png"
    overlay_path = tmp_path / "overlay.png"

    cv2.imwrite(str(mask_path), mask)
    cv2.imwrite(str(sar_path), np.ones((100, 100), dtype=np.uint8) * 128)

    summary, geojson, over_out = analyze_spill_geometry(
        binary_mask_path=mask_path,
        source_image_path=sar_path,
        overlay_out_path=overlay_path,
        min_component_size_pixels=1,
    )

    stats = summary["scene_level_statistics"]
    assert stats["num_components"] == 1
    assert stats["total_oil_pixels"] == 800
    assert stats["total_oil_fraction"] == 800 / 10000.0
    assert summary["georeferenced"] is False
    assert summary["total_area_km2"] is None

    comp = summary["components"][0]
    assert comp["pixel_area"] == 800
    assert comp["bbox_pixel"] == [10, 20, 40, 20]
    assert abs(comp["centroid_pixel"][0] - 29.5) < 1.5
    assert abs(comp["centroid_pixel"][1] - 29.5) < 1.5
    assert Path(over_out).exists()


def test_horizontal_and_vertical_ellipse_orientation(tmp_path):
    sar_path = tmp_path / "sar_dummy.png"
    cv2.imwrite(str(sar_path), np.ones((120, 120), dtype=np.uint8) * 128)

    # 1. Horizontal Rectangle (10 rows x 80 cols)
    mask_h = np.zeros((120, 120), dtype=np.uint8)
    mask_h[50:60, 20:100] = 255
    path_h = tmp_path / "mask_h.png"
    cv2.imwrite(str(path_h), mask_h)

    summary_h, _, _ = analyze_spill_geometry(path_h, sar_path, tmp_path / "over_h.png")
    comp_h = summary_h["components"][0]
    assert abs(comp_h["major_axis_length_px"] - 80.0) < 5.0
    assert abs(comp_h["minor_axis_length_px"] - 10.0) < 5.0
    # Horizontal orientation should be near 0 or 180 degrees
    assert comp_h["orientation_angle_deg"] < 15.0 or comp_h["orientation_angle_deg"] > 165.0

    # 2. Vertical Rectangle (80 rows x 10 cols)
    mask_v = np.zeros((120, 120), dtype=np.uint8)
    mask_v[20:100, 50:60] = 255
    path_v = tmp_path / "mask_v.png"
    cv2.imwrite(str(path_v), mask_v)

    summary_v, _, _ = analyze_spill_geometry(path_v, sar_path, tmp_path / "over_v.png")
    comp_v = summary_v["components"][0]
    assert abs(comp_v["major_axis_length_px"] - 80.0) < 5.0
    assert abs(comp_v["minor_axis_length_px"] - 10.0) < 5.0
    # Vertical orientation should be near 90 degrees
    assert abs(comp_v["orientation_angle_deg"] - 90.0) < 15.0


def test_multiple_disconnected_components(tmp_path):
    mask = np.zeros((100, 100), dtype=np.uint8)
    mask[10:20, 10:20] = 255  # 100 pixels
    mask[50:80, 50:60] = 255  # 300 pixels

    mask_path = tmp_path / "multi_mask.png"
    sar_path = tmp_path / "sar_dummy.png"
    overlay_path = tmp_path / "overlay.png"

    cv2.imwrite(str(mask_path), mask)
    cv2.imwrite(str(sar_path), np.ones((100, 100), dtype=np.uint8) * 128)

    summary, _, _ = analyze_spill_geometry(
        binary_mask_path=mask_path,
        source_image_path=sar_path,
        overlay_out_path=overlay_path,
    )

    stats = summary["scene_level_statistics"]
    assert stats["num_components"] == 2
    assert stats["total_oil_pixels"] == 400
    assert stats["largest_component_pixels"] == 300
    assert stats["largest_component_fraction"] == 300 / 400.0


def test_empty_mask_null_safeguards(tmp_path):
    mask = np.zeros((64, 64), dtype=np.uint8)
    mask_path = tmp_path / "empty_mask.png"
    sar_path = tmp_path / "sar_dummy.png"
    overlay_path = tmp_path / "overlay.png"

    cv2.imwrite(str(mask_path), mask)
    cv2.imwrite(str(sar_path), np.zeros((64, 64), dtype=np.uint8))

    summary, geojson, _ = analyze_spill_geometry(
        binary_mask_path=mask_path,
        source_image_path=sar_path,
        overlay_out_path=overlay_path,
    )

    stats = summary["scene_level_statistics"]
    assert stats["num_components"] == 0
    assert stats["total_oil_pixels"] == 0
    assert stats["largest_component_fraction"] is None
    assert stats["fragmentation_index_per_pixel"] is None
    assert stats["components_per_10000_oil_pixels"] is None
    assert stats["scene_centroid_pixel"] is None
    assert len(summary["components"]) == 0


def test_minimum_component_size_filtering(tmp_path):
    mask = np.zeros((100, 100), dtype=np.uint8)
    mask[5:7, 5:6] = 255      # 2 micro pixels
    mask[30:50, 30:50] = 255  # 400 pixels

    mask_path = tmp_path / "filtered_mask.png"
    sar_path = tmp_path / "sar_dummy.png"
    overlay_path = tmp_path / "overlay.png"

    cv2.imwrite(str(mask_path), mask)
    cv2.imwrite(str(sar_path), np.zeros((100, 100), dtype=np.uint8))

    summary, _, _ = analyze_spill_geometry(
        binary_mask_path=mask_path,
        source_image_path=sar_path,
        overlay_out_path=overlay_path,
        min_component_size_pixels=10,
    )

    stats = summary["scene_level_statistics"]
    assert stats["num_components"] == 1
    assert summary["components"][0]["pixel_area"] == 400


def test_web_mercator_equal_area_reprojection(tmp_path):
    # Web Mercator EPSG:3857 suffers high latitude area distortion.
    # Verify that Web Mercator rasters are reprojected to World Equal-Area ESRI:54034.
    tif_path = tmp_path / "web_mercator_sar.tif"
    mask_path = tmp_path / "geo_mask.png"
    overlay_path = tmp_path / "overlay.png"

    transform = from_origin(500000, 2000000, 10, 10)
    arr = (np.random.rand(100, 100) * 255).astype(np.uint8)

    with rasterio.open(
        tif_path,
        "w",
        driver="GTiff",
        height=100,
        width=100,
        count=1,
        dtype=arr.dtype,
        crs="EPSG:3857",
        transform=transform,
    ) as dst:
        dst.write(arr, 1)

    mask = np.zeros((100, 100), dtype=np.uint8)
    mask[20:40, 20:40] = 255
    cv2.imwrite(str(mask_path), mask)

    summary, geojson, _ = analyze_spill_geometry(
        binary_mask_path=mask_path,
        source_image_path=tif_path,
        overlay_out_path=overlay_path,
    )

    assert summary["georeferenced"] is True
    assert summary["source_crs"] == "EPSG:3857"
    assert summary["analysis_crs"] == "ESRI:54034"
    assert summary["area_calculation_method"] == "World Equal-Area Cylindrical Projection (ESRI:54034)"
    assert summary["total_area_m2"] > 0
    assert summary["total_area_km2"] > 0


def test_missing_oil_detection_returns_insufficient_data():
    res_case = client.post("/cases", json={"name": "No Oil Detection Case"})
    case_id = res_case.json()["case_id"]

    res_an = client.post(f"/cases/{case_id}/analysis/spill-geometry", json={})
    assert res_an.status_code == 200
    an_data = res_an.json()

    assert an_data["status"] == "insufficient_data"
    assert an_data["confidence"] is None
    assert "No completed oil detection analysis found" in an_data["warnings"][0]


def test_successful_spill_geometry_analysis_pipeline(tmp_path):
    dummy_img_dir = tmp_path / "t_img"
    dummy_mask_dir = tmp_path / "t_mask"
    dummy_img_dir.mkdir()
    dummy_mask_dir.mkdir()

    for i in range(2):
        cv2.imwrite(str(dummy_img_dir / f"s_{i}.png"), np.zeros((32, 32), dtype=np.uint8))
        cv2.imwrite(str(dummy_mask_dir / f"s_{i}.png"), np.zeros((32, 32), dtype=np.uint8))

    ckpt_path = tmp_path / "test_model.pt"
    train_model(images_dir=dummy_img_dir, masks_dir=dummy_mask_dir, epochs=1, batch_size=2, image_size=32, out_path=ckpt_path, seed=42)

    res_case = client.post("/cases", json={"name": "Full Geometry Pipeline Case"})
    case_id = res_case.json()["case_id"]

    sar_bytes = cv2.imencode(".png", np.ones((32, 32), dtype=np.uint8) * 128)[1].tobytes()
    res_ev = client.post(f"/cases/{case_id}/evidence", files={"file": ("sar_scene.png", sar_bytes, "image/png")}, data={"evidence_type": "sar_image"})
    sar_ev_id = res_ev.json()["evidence_id"]

    res_oil = client.post(f"/cases/{case_id}/analysis/oil-detection", json={"checkpoint_path": str(ckpt_path), "sar_evidence_id": sar_ev_id})
    assert res_oil.status_code == 200
    oil_an_id = res_oil.json()["analysis_id"]

    res_geom = client.post(f"/cases/{case_id}/analysis/spill-geometry", json={"oil_detection_analysis_id": oil_an_id})
    assert res_geom.status_code == 200
    geom_data = res_geom.json()

    assert geom_data["status"] == "completed"
    assert geom_data["module"] == "spill_geometry"
    assert geom_data["confidence"] is None
    assert geom_data["configuration"]["source_oil_detection_analysis_id"] == oil_an_id

    res_dict = geom_data["result"]
    assert "scene_level_statistics" in res_dict
    assert "components" in res_dict
    assert Path(res_dict["contour_overlay_path"]).exists()
    assert Path(res_dict["geometry_json_path"]).exists()

    expected_overlay_sha256 = hashlib.sha256(Path(res_dict["contour_overlay_path"]).read_bytes()).hexdigest()
    expected_json_sha256 = hashlib.sha256(Path(res_dict["geometry_json_path"]).read_bytes()).hexdigest()

    assert res_dict["contour_overlay_sha256"] == expected_overlay_sha256
    assert res_dict["geometry_json_sha256"] == expected_json_sha256
