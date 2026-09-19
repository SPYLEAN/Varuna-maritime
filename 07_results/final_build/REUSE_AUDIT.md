# VARUNA — Architecture & Code Reuse Audit

**Document ID**: `VARUNA-AUDIT-FINAL-20260919`  
**Target Branch**: `final/varuna-24h-build`  
**Base Commit**: `1836737`  
**Auditor**: Antigravity Autonomous Systems  
**Date**: 2026-09-19  

---

## Executive Summary

In accordance with **RULE 1 (Audit Before Writing Code)**, this document records the comprehensive audit of existing systems in `SPYLEAN/Varuna-maritime`. To ensure architectural integrity, stability, and zero duplication, all existing operational subsystems are audited below for direct code reuse, planned modifications, and license/provenance implications.

---

## Component Reuse Register

| # | System Component | Existing Path(s) | Reused Capabilities | Modifications for Final Build | License & Provenance |
|---|---|---|---|---|---|
| 1 | **Multi-Case API** | `backend/app/routers/cases.py`<br>`backend/app/services/case_store.py` | Case entity CRUD, atomic filesystem persistence (`data/cases/<case_id>/case.json`), incident metadata validation, multi-case state machine. | Wire end-to-end pipeline progression endpoints: `CASE CREATED` → `OBSERVATION SEARCHED` → `OBSERVATION ATTACHED` → `PRODUCT ACQUIRED` → `SAR PREPROCESSED` → `SLICK ANALYSED` → `CANDIDATE SELECTED` → `HINDCAST COMPLETE` → `FORECAST COMPLETE` → `AIS CORRELATED` → `REVIEW READY`. | Varuna Proprietary / MIT dependencies. Zero data leakage across cases. |
| 2 | **CDSE STAC Search** | `backend/app/services/sentinel_search.py`<br>`backend/app/routers/satellite.py` | Copernicus Data Space Ecosystem STAC query builder (spatial polygon / bbox, datetime interval, `collection=SENTINEL-1`, `sar:instrument_mode=IW`, `productType=GRD`). | Ensure full STAC item properties (footprint, product ID, archive URL, acquisition timestamp) are preserved upon case attachment. | Copernicus Sentinel Open Access / CDSE API terms. |
| 3 | **Sentinel Product Acquisition** | `backend/app/services/sentinel_download.py`<br>`backend/app/services/cdse_auth.py` | CDSE OData client, OAuth2 token caching, direct ZIP download, SHA-256 integrity verification, local archive caching (`VARUNA_CDSE_CACHE_DIR`). | Enforce strict credential validation: if `CDSE_USER` / `CDSE_PASSWORD` missing, declare `REAL_PROVIDER_VALIDATION=BLOCKED`. Cache hit avoids redundant ~1.5GB downloads. | ESA / Copernicus Sentinel Data Terms. |
| 4 | **SAFE Extraction** | `backend/app/services/sar_extractor.py` | Streamed ZIP extraction of `.SAFE` structures, verification of `manifest.safe`, automated discovery of VV and VH measurement GeoTIFF/JP2 rasters. | Source archive SHA-256 carried forward directly into extraction metadata without re-hashing extracted directories. | MIT License (Varuna core). |
| 5 | **VV/VH Calibration & Preprocessing** | `backend/app/services/sar_quicklook.py`<br>`backend/app/services/sar_calibration.py` | Multi-engine calibration handler (xarray-sentinel, eofs, SNAP LUT), Sigma0 dB derivation, dual-pol grid alignment, nodata masking. | Radiometric truthfulness: generic rasters default to `UNKNOWN` or `CALIBRATION_FALLBACK_UNCALIBRATED_INTENSITY` unless verified metadata declares calibration. Normalization uses fixed dB bounds `[-30, 0]` dB (VV) and `[-35, -5]` dB (VH). | Adapted from `m7mdehab/oil-spill-detection` (MIT) & ESA SNAP calibration formulas. Preserved attribution in `THIRD_PARTY_NOTICES.md`. |
| 6 | **Radiometric Truthfulness** | `backend/app/services/sar_quicklook.py`<br>`backend/app/models/provenance.py` | `RadiometricMode` enum (`SIGMA0_CALIBRATED_DB`, `PROVIDER_PRECALIBRATED`, `CALIBRATION_FALLBACK_UNCALIBRATED_INTENSITY`, `UNKNOWN`). | Zero filename-based calibration inference. All outputs report authentic radiometric modes. | Varuna core integrity contract. |
| 7 | **Source Provenance Engine** | `backend/app/models/provenance.py`<br>`backend/app/services/sar_quicklook.py` | Structured `SourceProvenance` dataclass, GeoTIFF TIFFTAG metadata injection, audit trail chaining. | Both VV and VH processed rasters carry `SOURCE_STAC_ITEM_ID`, `SOURCE_PRODUCT_ID`, and `SOURCE_ARCHIVE_SHA256`. | Varuna core auditability contract. |
| 8 | **SAR Candidate Extraction** | `backend/app/services/sar_triage.py`<br>`Varuna-research/...` | Morphological dark-patch segmentation, multi-threshold contour extraction, geometric attribute calculation (area, perimeter, solidity, elongation). | Directly feeds extracted dark candidate features into the OilSeg V1 model adapter and Evidence Gate. | MIT / adapted from `Halyjo/slicksmith-ttom`. |
| 9 | **SAR Candidate ML Pipeline** | `ml/src/oiltrace_ml/candidate_classifier.py` | Feature extraction (backscatter contrast, gradient sharpness, texture metrics), candidate tabular classification. | Serves as auxiliary tabular scoring alongside spatial segmentation. | MIT License. |
| 10 | **Candidate Triage** | `backend/app/services/sar_triage.py` | Spatial filtering against land buffers, low-wind false positive exclusion, candidate ranking. | Unified with Evidence Gate (`backend/app/services/evidence_gate.py`) for automated physics qualification. | Varuna core. |
| 11 | **OilSeg V1 Scaffold** | `ml/OILSEG_V1_PREP.md`<br>`ml/src/oiltrace_ml/model.py`<br>`data.py`, `train.py`, `evaluate.py`, `checkpoint.py` | Dual-polarization 2-channel `SmallUNet` (`in_channels=2`, `out_channels=1`), `Sentinel1Dataset`, manifest loading, fixed dB normalizer, category-aware metrics. | Train frozen baseline checkpoint `varuna_oilseg_v1_smallunet.pt` using verified dual-pol scenes. Report IoU, Dice/F1, precision, recall, and negative false positive rates. Term raw output `OIL_EVIDENCE_SCORE`. | Varuna ML stack (MIT). |
| 12 | **OpenDrift Hindcast** | `backend/app/services/opendrift_drift.py`<br>`backend/app/routers/analysis.py` | Backward trajectory numerical modeling (`OceanDrift` / `OpenOil`), ensemble dispersion, probable release area kernel estimation. | Triggered only for `PHYSICS_ELIGIBLE` candidates; outputs probable release area polygon and release-time window with ensemble uncertainty. | OpenDrift (GPL-2.0, process-boundary isolated). |
| 13 | **OpenDrift Forecast** | `backend/app/services/opendrift_drift.py` | Forward trajectory modeling under prevailing ocean currents and winds, coastal stranding assessment, particle density time series. | Answers response question: "Where is this slick likely to move next?" across 12h, 24h, 48h horizons. | OpenDrift (GPL-2.0). |
| 14 | **Environmental Forcing** | `backend/app/services/environmental_forcing.py` | Ingestion for ECMWF ERA5, NOAA GFS winds, CMEMS ocean currents, GEBCO bathymetry, offline synthetic physics fallback. | Provenance tracking for wind/current forcing datasets, model cycle, and spatial resolution. | Open data / Copernicus Marine / NOAA. |
| 15 | **AIS Ingestion & Ranking** | `backend/app/services/ais_service.py`<br>`backend/app/routers/investigation.py` | Spatiotemporal AIS track search, distance-to-release scoring, vessel trajectory intersection, flag/type/MMSI lookup. | Strict terminology enforcement: produces `INVESTIGATIVE_CANDIDATE` (never "culprit" or "guilty"). Explicitly flags `REAL AIS`, `SYNTHETIC_DEMO AIS`, or `MISSING AIS`. Supports `NO_CREDIBLE_CANDIDATE`. | Spire / AISHub / open AIS schema. |
| 16 | **Evidence Engine** | `backend/app/services/evidence_store.py`<br>`backend/app/routers/evidence.py` | Evidence chain graph linking observation, calibration, segmentation, drift, and vessel correlation. | Enforce Response-First reporting structure and explicit scientific limitations. | Varuna core. |
| 17 | **Ops Console** | `ops_console/index.html`<br>`ops_console/app.js`<br>`ops_console/app.css` | Stitch visual system: Deep marine dark palette, glassmorphic panels, Leaflet map views, responsive tabular inspectors. | 7-step guided workflow: `OVERVIEW` → `OBSERVATION` → `SLICK ANALYSIS` → `RECONSTRUCTION` → `VESSEL INTELLIGENCE` → `REVIEW` → `PROVENANCE` with clear origin tags (`REAL`, `DERIVED`, `SYNTHETIC_DEMO`, `UNAVAILABLE`). | Varuna Ops Console (MIT / Proprietary UI). |
| 18 | **R001 Benchmark** | `Varuna-research/R001_WAKASHIO/` | Canonical MV Wakashio historical grounding dataset (Mauritius, August 2020), satellite chips, ground truth documentation. | Quarantined: `training_allowed=False`. Never leaked into training splits. Used exclusively for post-training historical benchmark validation. | Public maritime casualty investigation archive. |

---

## Policy Compliance Verification

1. **Direct Code Reuse**: Reused existing production implementations for OpenDrift, CDSE search, calibration, and AIS scoring without unneeded redesign.
2. **Third-Party Attribution**: All third-party derivatives (m7mdehab, halyjo) are tracked and referenced in `THIRD_PARTY_NOTICES.md`.
3. **No Disallowed Features**: Chatbots, blockchains, speculative LLM endpoints, and unnecessary database migrations are completely excluded per Rule 16.
