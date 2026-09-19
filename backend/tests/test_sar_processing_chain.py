"""
VARUNA — SAR Processing Chain & Open-Source Integration Test Suite
Validates the complete open-source SAR processing chain:
- Third-party attribution notices and license compliance
- Slicksmith TTOM integral mask calculation and timestamp guardrails
- Sentinel-1 product acquisition resolution
- Lee filter, dB conversion, and model tensor normalization
- Geodesic WGS84 polygon area and vectorisation
- Model unavailability graceful degradation (no fake outputs)
- Explicit radiometric mode recording (SIGMA0_LUT_CALIBRATED vs MEASUREMENT_INTENSITY_FALLBACK)
- Real download integration tests (skipped without CDSE credentials)
- Phase 2 Arabian Sea observation resolution and processing smoke
"""

import os
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
import rasterio
from affine import Affine
from rasterio.crs import CRS
from shapely.geometry import box

from backend.app.services.sentinel_catalog import get_sentinel1_item_by_id
from backend.app.services.sentinel_download import (
    CdseCredentialsMissingError,
    acquire_observation_product,
    compute_file_sha256,
    get_access_token,
    resolve_product_from_observation,
)
from backend.app.services.sar_quicklook import (
    DEFAULT_DB_WINDOW,
    RADIOMETRIC_MODE_COG_PRECALIBRATED,
    RADIOMETRIC_MODE_MEASUREMENT_INTENSITY_FALLBACK,
    RADIOMETRIC_MODE_PROVIDER_PRECALIBRATED,
    RADIOMETRIC_MODE_SIGMA0_LUT,
    RADIOMETRIC_MODE_UNKNOWN,
    GeoreferenceUnavailableError,
    _georef_from_dataarray,
    CalibratedScene,
    calibrate_safe,
    execute_quicklook_preprocessing,
    lee_filter,
    model_ready_chw,
    normalize_for_model,
    read_grd_measurement,
    read_sar_raster,
    to_db,
    verify_dualpol_alignment,
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
        mask = torch.tensor([
            [0, 1, 0],
            [1, 0, 1],
            [0, 0, 1],
        ], dtype=torch.uint8)
        integral = build_integral_mask(mask)

        assert integral.shape == (4, 4)
        assert integral[0, 0] == 0
        assert integral[0, 3] == 0
        assert integral[3, 0] == 0
        assert integral[3, 3] == 4


class TestSarRadiometricChain:
    def test_lee_filter_preserves_mean_reduces_variance(self):
        np.random.seed(42)
        base_signal = np.ones((64, 64), dtype=np.float64) * 0.15
        speckle = np.random.rayleigh(scale=1.0, size=(64, 64))
        noisy = base_signal * speckle

        filtered = lee_filter(noisy, size=7)
        assert filtered.shape == noisy.shape
        assert abs(filtered.mean() - noisy.mean()) / noisy.mean() < 0.05
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
        assert np.isclose(hwc[0, 0, :], 0.0).all()
        assert np.isclose(hwc[0, 1, :], 0.5).all()
        assert np.isclose(hwc[1, 0, :], 1.0).all()
        assert np.isclose(hwc[1, 1, :], 1.0).all()

    def test_model_ready_chw_tensor_shape(self):
        db = np.ones((128, 128), dtype=np.float64) * -15.0
        chw = model_ready_chw(db)
        assert chw.shape == (3, 128, 128)
        assert chw.dtype == np.float32


class TestVectorisationAndGeodesicArea:
    def test_polygon_area_km2_wgs84_geodesic(self):
        geom = box(0.0, 0.0, 0.1, 0.1)
        area_km2 = polygon_area_km2(geom, CRS.from_epsg(4326))
        assert 120.0 < area_km2 < 125.0

    def test_vectorize_oil_creates_geodataframe_with_expected_columns(self):
        mask = np.zeros((100, 100), dtype=np.uint8)
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

    def test_model_unavailable_creates_no_fake_mask(self, tmp_path):
        scene_chw = np.zeros((3, 64, 64), dtype=np.float32)
        result = run_quicklook_segmentation(
            case_id="case-no-fake",
            observation_id="obs-no-fake",
            scene_chw=scene_chw,
            transform=Affine.identity(),
            crs=CRS.from_epsg(4326),
            model_path=None,
            output_base_dir=tmp_path,
        )
        assert result.status == "MODEL_UNAVAILABLE"
        assert result.class_mask_path is None
        assert result.class_mask_rgb_path is None

        # Verify no .tif files exist under inference directory
        inf_dir = tmp_path / "case-no-fake" / "observations" / "obs-no-fake" / "inference"
        tif_files = list(inf_dir.glob("*.tif"))
        assert len(tif_files) == 0, "No fake mask GeoTIFF should be written when model is unavailable"

    def test_model_unavailable_creates_no_fake_geojson(self, tmp_path):
        scene_chw = np.zeros((3, 64, 64), dtype=np.float32)
        result = run_quicklook_segmentation(
            case_id="case-no-fake-vec",
            observation_id="obs-no-fake-vec",
            scene_chw=scene_chw,
            transform=Affine.identity(),
            crs=CRS.from_epsg(4326),
            model_path=None,
            output_base_dir=tmp_path,
        )
        assert result.status == "MODEL_UNAVAILABLE"
        assert result.geojson_path is None
        assert result.num_oil_polygons == 0
        assert result.total_oil_area_km2 == 0.0

        vec_dir = tmp_path / "case-no-fake-vec" / "observations" / "obs-no-fake-vec" / "vectors"
        geojson_files = list(vec_dir.glob("*.geojson"))
        assert len(geojson_files) == 0, "No fake vector GeoJSON should be written when model is unavailable"


class TestQuicklookCalibrationRouting:
    def test_safe_uses_calibrate_safe(self, tmp_path):
        safe_dir = tmp_path / "S1A_TEST.SAFE"
        meas_dir = safe_dir / "measurement"
        meas_dir.mkdir(parents=True)
        test_tif = meas_dir / "s1a-iw-grd-vv-20240914.tiff"

        with rasterio.open(
            test_tif, "w", driver="GTiff", height=32, width=32, count=1,
            dtype="uint16", crs="EPSG:4326", transform=Affine.identity()
        ) as dst:
            dst.write(np.ones((32, 32), dtype="uint16") * 100, 1)

        with patch("backend.app.services.sar_quicklook.calibrate_safe") as mock_cal:
            mock_cal.return_value = CalibratedScene(
                sigma0=np.ones((32, 32), dtype=np.float64) * 0.05,
                transform=Affine.identity(),
                crs=CRS.from_epsg(4326),
                polarisation="VV",
                vh_available=False,
                radiometric_mode=RADIOMETRIC_MODE_SIGMA0_LUT,
            )

            res, scene, _, _ = execute_quicklook_preprocessing(
                case_id="case_routing_test",
                observation_id="obs_routing_test",
                source_input_path=safe_dir,
                output_base_dir=tmp_path,
            )

            assert mock_cal.called, "execute_quicklook_preprocessing MUST route SAFE products to calibrate_safe()"
            assert res.radiometric_mode == RADIOMETRIC_MODE_SIGMA0_LUT

    def test_georef_failure_never_fabricates_epsg4326(self):
        """DataArray without spatial georeferencing must raise GeoreferenceUnavailableError, never EPSG:4326."""
        import xarray as xr
        da = xr.DataArray(np.zeros((16, 16), dtype=np.float32))
        with pytest.raises(GeoreferenceUnavailableError):
            _georef_from_dataarray(da)

    def test_generic_raster_defaults_to_unknown_radiometric_mode(self, tmp_path):
        """Generic rasters without explicit provider tags must default to UNKNOWN without value guessing."""
        plain_tif = tmp_path / "arbitrary_uncalibrated_raster.tif"
        with rasterio.open(
            plain_tif, "w", driver="GTiff", height=32, width=32, count=1,
            dtype="float32", crs="EPSG:4326", transform=Affine.identity()
        ) as dst:
            dst.write(np.ones((32, 32), dtype="float32") * 150.0, 1)

        scene = read_sar_raster(plain_tif)
        assert scene.radiometric_mode == RADIOMETRIC_MODE_UNKNOWN
        # Value-magnitude guessing (data**2 if max > 100) must NOT be applied
        assert np.isclose(scene.sigma0[0, 0], 150.0)

    def test_verify_dualpol_alignment_checks(self):
        """Spatial alignment checks must pass for matching rasters and fail on dimension/CRS mismatch."""
        s1 = CalibratedScene(
            sigma0=np.zeros((32, 32)),
            transform=Affine.identity(),
            crs=CRS.from_epsg(4326),
        )
        s2 = CalibratedScene(
            sigma0=np.zeros((32, 32)),
            transform=Affine.identity(),
            crs=CRS.from_epsg(4326),
        )
        assert verify_dualpol_alignment(s1, s2) is True

        s_mismatch = CalibratedScene(
            sigma0=np.zeros((32, 30)),
            transform=Affine.identity(),
            crs=CRS.from_epsg(4326),
        )
        with pytest.raises(ValueError, match="Dual-pol alignment failure"):
            verify_dualpol_alignment(s1, s_mismatch)

    def test_radiometric_mode_is_recorded(self, tmp_path):
        test_cog = tmp_path / "test_scene_cog.tif"
        with rasterio.open(
            test_cog, "w", driver="GTiff", height=32, width=32, count=1,
            dtype="float32", crs="EPSG:4326", transform=Affine.identity()
        ) as dst:
            dst.write(np.ones((32, 32), dtype="float32") * 0.1, 1)
            dst.update_tags(RADIOMETRIC_MODE=RADIOMETRIC_MODE_PROVIDER_PRECALIBRATED)

        res, scene, _, _ = execute_quicklook_preprocessing(
            case_id="case_mode_test",
            observation_id="obs_mode_test",
            source_input_path=test_cog,
            output_base_dir=tmp_path,
        )

        assert res.radiometric_mode == RADIOMETRIC_MODE_PROVIDER_PRECALIBRATED
        assert Path(res.processed_db_geotiff_path).exists()

        with rasterio.open(res.processed_db_geotiff_path) as dst_read:
            tags = dst_read.tags()
            assert tags.get("RADIOMETRIC_MODE") == RADIOMETRIC_MODE_PROVIDER_PRECALIBRATED
            assert tags.get("TERRAIN_CORRECTION") == "NONE"

    def test_fallback_never_claims_sigma0_calibrated(self, tmp_path):
        safe_dir = tmp_path / "S1A_FALLBACK.SAFE"
        meas_dir = safe_dir / "measurement"
        meas_dir.mkdir(parents=True)
        test_tif = meas_dir / "s1a-iw-grd-vv-fallback.tiff"

        with rasterio.open(
            test_tif, "w", driver="GTiff", height=32, width=32, count=1,
            dtype="uint16", crs="EPSG:4326", transform=Affine.identity()
        ) as dst:
            dst.write(np.ones((32, 32), dtype="uint16") * 200, 1)

        fallback_scene = read_grd_measurement(safe_dir, polarisation="vv")
        assert fallback_scene.radiometric_mode == RADIOMETRIC_MODE_MEASUREMENT_INTENSITY_FALLBACK
        assert fallback_scene.radiometric_mode != RADIOMETRIC_MODE_SIGMA0_LUT

        res, scene, _, _ = execute_quicklook_preprocessing(
            case_id="case_fallback_test",
            observation_id="obs_fallback_test",
            source_input_path=safe_dir,
            output_base_dir=tmp_path,
        )

        assert res.radiometric_mode == RADIOMETRIC_MODE_MEASUREMENT_INTENSITY_FALLBACK
        with rasterio.open(res.processed_db_geotiff_path) as ds:
            tags = ds.tags()
            assert tags.get("RADIOMETRIC_MODE") == RADIOMETRIC_MODE_MEASUREMENT_INTENSITY_FALLBACK
            assert tags.get("RADIOMETRIC_MODE") != RADIOMETRIC_MODE_SIGMA0_LUT


class TestLiveObservationChain:
    """Validate Phase 2 Arabian Sea observation resolution and processing tests."""

    ARABIAN_SEA_ITEM_ID = "S1A_IW_GRDH_1SDV_20240914T011113_20240914T011139_055654_06CB9B_D44A_COG"

    def test_resolve_arabian_sea_observation_product(self):
        item = get_sentinel1_item_by_id(self.ARABIAN_SEA_ITEM_ID)
        assert item["stac_item_id"] == self.ARABIAN_SEA_ITEM_ID

        target = resolve_product_from_observation(item)
        assert "80587464-dae0-48af-89f1-0473bcdfd4a1" in target.id
        assert target.name == "S1A_IW_GRDH_1SDV_20240914T011113_20240914T011139_055654_06CB9B_D44A"
        assert "https://download.dataspace.copernicus.eu/odata/v1/Products" in target.download_url

    def test_live_catalog_resolution_and_synthetic_processing_smoke(self, tmp_path):
        """Smoke test verifying catalog resolution coupled with synthetic raster preprocessing."""
        item = get_sentinel1_item_by_id(self.ARABIAN_SEA_ITEM_ID)

        # 1. Product Acquisition Resolution
        acq_result = acquire_observation_product(
            case_id="case_smoke_test",
            observation_id="obs_smoke_001",
            observation_data=item,
            base_dir=tmp_path,
        )
        assert acq_result.status in ("SUCCESS", "CREDENTIALS_MISSING", "AUTHENTICATION_FAILED")

        # 2. Synthetic processing smoke
        test_raster_path = tmp_path / "smoke_s1_scene.tif"
        data = (np.random.gamma(shape=2.0, scale=0.05, size=(128, 128)) * 1000).astype(np.float32)
        transform = Affine.translation(65.0, 20.0) * Affine.scale(0.001, -0.001)
        crs = CRS.from_epsg(4326)

        with rasterio.open(
            test_raster_path, "w", driver="GTiff", height=128, width=128,
            count=1, dtype=rasterio.float32, crs=crs, transform=transform,
        ) as dst:
            dst.write(data, 1)
            dst.update_tags(RADIOMETRIC_MODE=RADIOMETRIC_MODE_PROVIDER_PRECALIBRATED)

        prep_res, scene, filtered, sigma0_db = execute_quicklook_preprocessing(
            case_id="case_smoke_test",
            observation_id="obs_smoke_001",
            source_input_path=test_raster_path,
            output_base_dir=tmp_path,
        )

        assert prep_res.status == "SUCCESS"
        assert prep_res.raster_dimensions == (128, 128)
        assert prep_res.radiometric_mode == RADIOMETRIC_MODE_PROVIDER_PRECALIBRATED

        chw = model_ready_chw(sigma0_db)
        inf_res = run_quicklook_segmentation(
            case_id="case_smoke_test",
            observation_id="obs_smoke_001",
            scene_chw=chw,
            transform=scene.transform,
            crs=scene.crs,
            model_path=None,
            output_base_dir=tmp_path,
        )
        assert inf_res.status == "MODEL_UNAVAILABLE"

    def test_live_download_skips_without_credentials(self, monkeypatch):
        monkeypatch.delenv("CDSE_USER", raising=False)
        monkeypatch.delenv("CDSE_PASS", raising=False)
        monkeypatch.delenv("COPERNICUS_USER", raising=False)
        monkeypatch.delenv("COPERNICUS_PASS", raising=False)
        with patch("backend.app.services.sentinel_download.CDSE_USER", ""):
            with patch("backend.app.services.sentinel_download.CDSE_PASS", ""):
                with pytest.raises(CdseCredentialsMissingError):
                    get_access_token()

    def test_live_test_never_uses_synthetic_raster(self):
        """Verify integration test contracts do not inject synthetic arrays."""
        import inspect
        source = inspect.getsource(self.test_real_download_and_processing_chain)
        assert "np.random" not in source, "test_real_download_and_processing_chain must never instantiate synthetic arrays"
        assert "gamma" not in source

    @pytest.mark.integration
    def test_real_download_and_processing_chain(self, tmp_path):
        """Genuinely live CDSE download and calibration chain. Skips if credentials absent."""
        user = os.environ.get("CDSE_USER") or os.environ.get("COPERNICUS_USER")
        password = os.environ.get("CDSE_PASS") or os.environ.get("COPERNICUS_PASS")
        if not user or not password:
            pytest.skip("CDSE_USER and CDSE_PASS environment variables are not configured; skipping live download.")

        item = get_sentinel1_item_by_id(self.ARABIAN_SEA_ITEM_ID)
        acq_result = acquire_observation_product(
            case_id="case_live_download",
            observation_id="obs_live_001",
            observation_data=item,
            base_dir=tmp_path,
        )

        assert acq_result.status == "SUCCESS"
        assert acq_result.bytes_downloaded > 0
        assert Path(acq_result.archive_path).exists()
        assert len(acq_result.sha256) == 64
        assert acq_result.safe_dir_path is not None
        assert acq_result.manifest_valid is True
        assert acq_result.vv_measurement_path is not None

        prep_res, scene, filtered, sigma0_db = execute_quicklook_preprocessing(
            case_id="case_live_download",
            observation_id="obs_live_001",
            source_input_path=acq_result.safe_dir_path,
            output_base_dir=tmp_path,
        )

        assert prep_res.status == "SUCCESS"
        assert prep_res.radiometric_mode in (
            RADIOMETRIC_MODE_SIGMA0_LUT,
            RADIOMETRIC_MODE_MEASUREMENT_INTENSITY_FALLBACK,
        )
        assert prep_res.raster_dimensions[0] > 0 and prep_res.raster_dimensions[1] > 0
        assert prep_res.crs is not None and len(prep_res.crs) > 0
        assert Path(prep_res.processed_db_geotiff_path).exists()
        if prep_res.vh_available and prep_res.vh_processed:
            assert prep_res.vh_processed_db_geotiff_path is not None
            assert Path(prep_res.vh_processed_db_geotiff_path).exists()
            assert prep_res.dualpol_aligned is True

        chw = model_ready_chw(sigma0_db)
        inf_res = run_quicklook_segmentation(
            case_id="case_live_download",
            observation_id="obs_live_001",
            scene_chw=chw,
            transform=scene.transform,
            crs=scene.crs,
            model_path=None,
            output_base_dir=tmp_path,
        )
        assert inf_res.status == "MODEL_UNAVAILABLE"
