# VARUNA — Phase 3.2: Live Sentinel Pipeline Hardening Report

**Repository**: `SPYLEAN/Varuna-maritime`  
**Branch**: `feature/varuna-live-e2e`  
**Target Observation**: `S1A_IW_GRDH_1SDV_20240914T011113_20240914T011139_055654_06CB9B_D44A_COG`  
**Expected OData UUID**: `80587464-dae0-48af-89f1-0473bcdfd4a1`  
**Evaluation Date**: 2026-09-19  
**Overall Status**: `PARTIAL` *(Codebase Hardening & Unit/Smoke Suites: 100% PASS; Real CDSE Download: SKIPPED due to credentials absent)*

---

## 1. Executive Summary

Phase 3.2 hardens the live Sentinel-1 pipeline to guarantee scientific truthfulness, remove fabricated georeferencing, eliminate heuristic radiometric guessing, add progress observability, enforce a dual-polarization contract, and preserve strict model boundaries.

---

## 2. Real Provider Results

| Check | Expected | Observed | Status |
| :--- | :--- | :--- | :--- |
| **STAC Discovery & Catalog Query** | CDSE STAC API Query (`2024-09-14`) | Correct metadata & footprint resolved | **PASS** |
| **OData UUID Resolution** | `80587464-dae0-48af-89f1-0473bcdfd4a1` | `80587464-dae0-48af-89f1-0473bcdfd4a1` | **PASS** |
| **CDSE Authentication** | Keycloak Bearer Token | `CDSE_USER` / `CDSE_PASS` not set in automated session | **SKIPPED** |
| **Real Archive Download** | ~1.5 GB Streaming ZIP | 0 bytes downloaded | **SKIPPED** |
| **Archive SHA-256** | 64-char Hex Digest | None | **SKIPPED** |
| **SAFE Extraction** | `.SAFE` directory & `manifest.safe` | None | **SKIPPED** |
| **Real VV Preprocessing** | Calibrated Sigma0 / Measurement Fallback | None | **SKIPPED** |
| **Real VH Preprocessing** | Calibrated Sigma0 / Measurement Fallback | None | **SKIPPED** |

> [!NOTE]
> Per specification contract, `test_real_download_and_processing_chain` skips only when credentials are absent. No synthetic data, random noise, or fabricated outputs were injected to simulate real download completion.

---

## 3. Synthetic Unit & Smoke Results

| Suite / Component | Scope | Result | Details |
| :--- | :--- | :--- | :--- |
| **`test_sar_processing_chain.py`** | SAR Preprocessing & Truthfulness | **21 PASSED**, 1 SKIPPED, 0 FAILED | Complete pipeline, speckle, Lee filter, dB conversion |
| **`test_sentinel_catalog.py`** | CDSE STAC Search & Normalization | **11 PASSED**, 0 FAILED | Live STAC query, AOI validation, pagination |
| **`test_phase1_multicase.py`** | Multi-Case Data Isolation | **9 PASSED**, 0 FAILED | Clean room isolation, storage persistence |
| **Full Backend Suite** | All Routers, Services, Physics | **209 PASSED**, 1 SKIPPED, 0 FAILED | Investigation engine, AIS, OpenDrift, forcing |
| **ML Test Suite** | ML Datasets, Transforms, Model | **42 PASSED**, 0 FAILED | Slicksmith sampler, candidate classifier, checkpoints |

---

## 4. Scientific Truthfulness & Contracts

### A. Georeferencing Truthfulness
- **Previous behavior**: `_georef_from_dataarray()` silently returned `(Affine.identity(), CRS.from_epsg(4326))` on error.
- **Hardened behavior**: Silent fallback completely removed. Introduced `GeoreferenceUnavailableError`. If a DataArray lacks genuine CRS or transform, it raises `GeoreferenceUnavailableError` explicitly.
- **Validation**: Verified by `test_georef_failure_never_fabricates_epsg4326`.

### B. Radiometric Truthfulness
- **Previous behavior**: Heuristic magnitude guessing `data**2 if max(data) > 100`.
- **Hardened behavior**: Value guessing completely removed.
- **Modes**:
  - `SIGMA0_LUT_CALIBRATED`: Assigned strictly when calibration LUT calculation succeeds.
  - `MEASUREMENT_INTENSITY_FALLBACK`: Assigned when calibration LUT is unavailable. Never labeled as calibrated Sigma0.
  - `PROVIDER_PRECALIBRATED`: Assigned when metadata or caller explicitly supports it.
  - `UNKNOWN`: Default for uncalibrated generic rasters.
- **Validation**: Verified by `test_generic_raster_defaults_to_unknown_radiometric_mode` and `test_fallback_never_claims_sigma0_calibrated`.

### C. Dual-Polarization Contract
- Processes both VV and VH if present in the SAFE product.
- Produces:
  - `<obs_id>_vv_sigma0_db.tif`
  - `<obs_id>_vh_sigma0_db.tif`
- Enforces `verify_dualpol_alignment()`: checks shape, CRS, and transform before allowing dual-pol ML use.
- Records full provenance tags in GeoTIFF metadata: `POLARISATION`, `RADIOMETRIC_MODE`, `CRS`, `TRANSFORM`, `DIMENSIONS`, `SOURCE_PRODUCT_ID`, `FILTER_METHOD="LEE_SPECKLE_MMSE"`, `FILTER_SIZE`, `TERRAIN_CORRECTION="NONE"`.

### D. Model Boundary Preservation
- Backend segmentation engine: 3-channel 5-class ONNX.
- OilSeg V1: 2-channel VV/VH binary PyTorch checkpoint.
- The two models remain cleanly isolated with `MODEL_UNAVAILABLE` status during SAR quicklook. No silent or fabricated conversions.

---

## 5. Remaining Blockers

1. **CDSE Credentials**: Set `CDSE_USER` and `CDSE_PASS` in `.env` to execute live 1.5GB archive streaming download, extraction, and calibration.
