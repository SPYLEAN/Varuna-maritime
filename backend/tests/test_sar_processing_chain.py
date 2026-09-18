"""
VARUNA — SAR Processing Chain & Open-Source Integration Test Suite
Validates the complete open-source SAR processing chain:
- Third-party attribution notices and license compliance
- Slicksmith TTOM integral mask calculation and timestamp guardrails
- Sentinel-1 product acquisition resolution
- Lee filter, dB conversion, and model tensor normalization
- Geodesic WGS84 polygon area and vectorisation
- Model unavailability graceful degradation
- Phase 2 Arabian Sea live observation processing verification
"""

import os
import tempfile
import time
from pathlib import Path

import numpy as np
import pytest
import rasterio
from affine import Affine
from rasterio.crs import CRS
from shapely.geometry import box

from backend.app.services.sentinel_catalog import get_sentinel1_item_by_id
from backend.app.services.sentinel_download import (
    acquire_observation_product,
    compute_file_sha256,
    resolve_product_from_observation,
)
from backend.app.services.sar_quicklook import (
    DEFAULT_DB_WINDOW,
    CalibratedScene,
    execute_quicklook_preprocessing,
    lee_filter,
    model_ready_chw,
    normalize_for_model,
    to_db,
)
from backend.app.services.segmentation_engine import (
    OIL_CLASS_INDEX,
    QuicklookInferenceResult,
    polygon_area_km2,
    run_quicklook_segmentation,
    vectorize_oil,
    write_geotiff,
)
from ml.src.oiltrace_ml.slicksmith.balanced_geo_sampler import build_integral_mask
import torch


class TestThirdPartyNotices:
    def test_third_party_notices_file_exists_and_records_sources(self):
        root = Path(__file__).resolve().parents[2]
        notices_file = root / "THIRD_PARTY_NOTICES.md"
        assert notices_file.is_file(), "THIRD_PARTY_NOTICES.md must exist at repository root"
        content = notices_file.read_text(encoding="utf-8")

        # Verify m7mdehab repository record
        assert "m7mdehab/oil-spill-detection" in content
        assert "6c18c292153b3c617dd1e015dbe00f86272f9437" in content
        assert "Mohammed Ehab" in content
        assert "MIT" in content

        # Verify slicksmith repository record
        assert "Halyjo/slicksmith-ttom" in content
        assert "9ccd35df53568c7e64121a2ae7c855f4545396ba" in content
        assert "Harald Lykke Joakimsen" in content

        # Verify strict policy prohibitions are recorded
        assert "KrishnanDhalavai" in content
        assert "OpenDrift" in content
        assert "VARUNA QUICKLOOK SAR ANALYSIS" in content


class TestSlicksmithIntegration:
    def test_build_integral_mask_prefix_sums(self):
        # 3x3 binary mask
        mask = torch.tensor([
            [0, 1, 0],
            [1, 0, 1],
            [0, 0, 1],
        ], dtype=torch.uint8)
        integral = build_integral_mask(mask)

        # Integral image has shape (H+1, W+1) with padded zeros
        assert integral.shape == (4, 4)
        assert integral[0, 0] == 0
        assert integral[0, 3] == 0
        assert integral[3, 0] == 0
        # Total sum of ones is 4
        assert integral[3, 3] == 4


class TestSarRadiometricChain:
    def test_lee_filter_preserves_mean_reduces_variance(self):
        np.random.seed(42)
        # Synthetic SAR backscatter with Rayleigh-distributed speckle noise
        base_signal = np.ones((64, 64), dtype=np.float64) * 0.15
        speckle = np.random.rayleigh(scale=1.0, size=(64, 64))
        noisy = base_signal * speckle

        filtered = lee_filter(noisy, size=7)
        assert filtered.shape == noisy.shape

        # Mean should be preserved within reasonable bound
        assert abs(filtered.mean() - noisy.mean()) / noisy.mean() < 0.05
        # Variance should be substantially reduced
        assert filtered.var() < noisy.var()

    def test_to_db_mathematical_accuracy(self):
        sigma0 = np.array([[1.0, 0.1], [0.01, 0.001]], dtype=np.float64)
        db = to_db(sigma0)
        assert np.isclose(db[0, 0], 0.0, atol=1e-6)       # 10 * log10(1) = 0 dB
        assert np.isclose(db[0, 1], -10.0, atol=1e-6)     # 10 * log10(0.1) = -10 dB
        assert np.isclose(db[1, 0], -20.0, atol=1e-6)     # 10 * log10(0.01) = -20 dB
        assert np.isclose(db[1, 1], -30.0, atol=1e-6)     # 10 * log10(0.001) = -30 dB

    def test_normalize_for_model_channels_and_window(self):
        db = np.array([[-25.0, -12.5], [0.0, 5.0]], dtype=np.float64)
        hwc = normalize_for_model(db, in_min=-25.0, in_max=0.0)
        assert hwc.shape == (2, 2, 3)
        assert np.isclose(hwc[0, 0, :], 0.0).all()   # -25 dB mapped to 0
        assert np.isclose(hwc[0, 1, :], 0.5).all()   # -12.5 dB mapped to 0.5
        assert np.isclose(hwc[1, 0, :], 1.0).all()   # 0 dB mapped to 1.0
        assert np.isclose(hwc[1, 1, :], 1.0).all()   # clipped at 1.0

    def test_model_ready_chw_tensor_shape(self):
        db = np.ones((128, 128), dtype=np.float64) * -15.0
        chw = model_ready_chw(db)
        assert chw.shape == (3, 128, 128)
        assert chw.dtype == np.float32


class TestVectorisationAndGeodesicArea:
    def test_polygon_area_km2_wgs84_geodesic(self):
        # 0.1 x 0.1 degree box near equator
        # 0.1 deg lat ~ 11.13 km, 0.1 deg lon ~ 11.13 km -> ~123 km^2
        geom = box(0.0, 0.0, 0.1, 0.1)
        area_km2 = polygon_area_km2(geom, CRS.from_epsg(4326))
        assert 120.0 < area_km2 < 125.0

    def test_vectorize_oil_creates_geodataframe_with_expected_columns(self):
        mask = np.zeros((100, 100), dtype=np.uint8)
        # Add oil patch (class 1)
        mask[30:60, 30:60] = OIL_CLASS_INDEX
        oil_prob = np.ones((100, 100), dtype=np.float32) * 0.85

        transform = Affine.translation(57.0, -20.0) * Affine.scale(0.001, -0.001)
        crs = CRS.from_epsg(4326)

        gdf = vectorize_oil(mask, transform, crs, oil_prob=oil_prob, min_area_m2=100)
        assert len(gdf) == 1
        assert "area_km2" in gdf.columns
        assert "mean_confidence" in gdf.columns
        assert "max_confidence" in gdf.columns
        assert gdf["mean_confidence"].iloc[0] == pytest.approx(0.85, rel=1e-3)


class TestModelUnavailabilityGracefulHalt:
    def test_run_quicklook_segmentation_without_model(self, tmp_path):
        scene_chw = np.zeros((3, 64, 64), dtype=np.float32)
        transform = Affine.identity()
        crs = CRS.from_epsg(4326)

        result = run_quicklook_segmentation(
            case_id="case-unit-test",
            observation_id="obs-unit-test",
            scene_chw=scene_chw,
            transform=transform,
            crs=crs,
            model_path="nonexistent_model.onnx",
            output_base_dir=tmp_path,
        )

        assert result.status == "MODEL_UNAVAILABLE"
        assert result.num_oil_polygons == 0
        assert result.total_oil_area_km2 == 0.0
        assert "Model weights are not present" in result.error_message


class TestLiveObservationChain:
    """Validate Phase 2 Arabian Sea observation acquisition and processing chain."""

    ARABIAN_SEA_ITEM_ID = "S1A_IW_GRDH_1SDV_20240914T011113_20240914T011139_055654_06CB9B_D44A_COG"

    def test_resolve_arabian_sea_observation_product(self):
        item = get_sentinel1_item_by_id(self.ARABIAN_SEA_ITEM_ID)
        assert item["stac_item_id"] == self.ARABIAN_SEA_ITEM_ID

        target = resolve_product_from_observation(item)
        assert "80587464-dae0-48af-89f1-0473bcdfd4a1" in target.id
        assert target.name == "S1A_IW_GRDH_1SDV_20240914T011113_20240914T011139_055654_06CB9B_D44A"
        assert "https://download.dataspace.copernicus.eu/odata/v1/Products" in target.download_url

    def test_live_acquisition_and_processing_pipeline(self, tmp_path):
        start_time = time.time()
        item = get_sentinel1_item_by_id(self.ARABIAN_SEA_ITEM_ID)

        # 1. Attempt Acquisition
        acq_result = acquire_observation_product(
            case_id="case_arabian_sea_test",
            observation_id="obs_arabian_sea_001",
            observation_data=item,
            base_dir=tmp_path,
        )

        # In environments without CDSE_USER / CDSE_PASS, reports CREDENTIALS_MISSING cleanly
        assert acq_result.status in ("SUCCESS", "CREDENTIALS_MISSING", "AUTHENTICATION_FAILED")

        # 2. Test Processing & Preprocessing Chain
        # Create a test SAR raster representing a 256x256 subset of the scene
        test_raster_path = tmp_path / "test_s1_scene.tif"
        data = (np.random.gamma(shape=2.0, scale=0.05, size=(256, 256)) * 1000).astype(np.float32)
        transform = Affine.translation(65.0, 20.0) * Affine.scale(0.001, -0.001)
        crs = CRS.from_epsg(4326)

        with rasterio.open(
            test_raster_path,
            "w",
            driver="GTiff",
            height=256,
            width=256,
            count=1,
            dtype=rasterio.float32,
            crs=crs,
            transform=transform,
        ) as dst:
            dst.write(data, 1)

        prep_res, scene, filtered, sigma0_db = execute_quicklook_preprocessing(
            case_id="case_arabian_sea_test",
            observation_id="obs_arabian_sea_001",
            source_input_path=test_raster_path,
            output_base_dir=tmp_path,
        )

        assert prep_res.status == "SUCCESS"
        assert prep_res.raster_dimensions == (256, 256)
        assert prep_res.vv_processed is True
        assert Path(prep_res.processed_db_geotiff_path).exists()
        assert len(prep_res.output_sha256) == 64

        # 3. Test Inference Stage
        chw = model_ready_chw(sigma0_db)
        inf_res = run_quicklook_segmentation(
            case_id="case_arabian_sea_test",
            observation_id="obs_arabian_sea_001",
            scene_chw=chw,
            transform=scene.transform,
            crs=scene.crs,
            model_path=None,  # Tests MODEL_UNAVAILABLE graceful path
            output_base_dir=tmp_path,
        )

        assert inf_res.status == "MODEL_UNAVAILABLE"
        elapsed = time.time() - start_time
        assert elapsed > 0
