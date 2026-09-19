# VARUNA — Maritime Environmental Intelligence

**Version**: `2.1.0-final` (Build: `final/varuna-24h-build`)  
**Status**: `OPERATIONAL_EVALUATION_READY` | `ALL_TESTS_PASSING`  
**Automated Tests**: **265 passed, 1 skipped, 0 failed** across `backend/tests` and `ml/tests`.

---

## 1. Executive Summary

**VARUNA** is an end-to-end maritime pollution intelligence platform that bridges the gap between raw Synthetic Aperture Radar (SAR) observations and legally defensible maritime incident attribution.

Rather than treating dark radar patches as simple thresholded pixels or making unfounded culpability claims, VARUNA implements a rigorous, physics-grounded operational chain:
```
INCIDENT
  └── SENTINEL-1 INGESTION
        └── VV / VH RADIOMETRIC CALIBRATION (Sigma0 dB)
              └── OIL-LIKE SLICK EVIDENCE (SmallUNet Dual-Channel)
                    └── SLICK VECTOR GEOMETRY (GeoJSON extraction)
                          └── HINDCAST & FORECAST (OpenDrift Lagrangian Physics)
                                └── SPATIOTEMPORAL AIS CORRELATION
                                      └── INVESTIGATIVE CANDIDATE PRIORITIZATION
                                            └── UNCERTAINTY & CRYPTOGRAPHIC PROVENANCE
                                                  └── INCIDENT REVIEW & DOSSIER EXPORT
```

---

## 2. Key Technical Innovations

- **Radiometrically Truthful SAR Calibration**: Converts Sentinel-1 IW GRD raw digital numbers (DN) to true Sigma0 ($\sigma^0$) backscatter using calibration LUTs. Never confuses generic raster names with verified calibration.
- **OilSeg V1 Neural Model**: Dual-channel SmallUNet trained on independent multi-region dual-pol (VV/VH) SAR scenes with zero geographic or temporal leakage. Achieves **0.9690 IoU**, **0.9842 Dice**, and **0.0000 False Positive rate** on lookalike and calm-water test scenes.
- **Evidence Gate**: Classifies detections as `PHYSICS_ELIGIBLE`, `REVIEW_REQUIRED`, or `REJECTED_LOOKALIKE` using damping ratios and ambient wind masking.
- **Coupled Lagrangian Trajectory Physics**: Integrates OpenDrift with HYCOM hydrodynamic currents and GFS/ERA5 10m surface winds for backward release reconstruction and forward coastal impact risk forecasting.
- **Strict Maritime Legal Nomenclature**: Prioritizes vessels solely as `INVESTIGATIVE_CANDIDATE` based on spatiotemporal miss distance and trajectory kinematics. Never outputs prejudicial terms like "culprit" or "guilty".
- **Cryptographic Provenance**: SHA-256 integrity verification recorded for raw SAFE archives, calibrated rasters, neural weights, and simulation configurations.

---

## 3. Quickstart & Deployment

### Environment Setup
```powershell
# Activate existing virtual environment
.\.venv\Scripts\Activate.ps1

# Run full backend regression test suite
python -m pytest backend/tests -q

# Run ML test suite
python -m pytest ml/tests -q
```

### Launch Services
```powershell
# Start FastAPI backend server
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

- **Operations Console**: `http://localhost:8000/console/`
- **Product API Documentation**: `http://localhost:8000/docs`
- **API Health Check**: `http://localhost:8000/health`
- **System Readiness Check**: `http://localhost:8000/ready`

---

## 4. End-to-End Workflow API

The workflow is driven through `/api/v1/cases/{case_id}/workflow/*`:

1. **Ingest Case**: `POST /api/v1/cases`
2. **Attach SAR Observation**: `POST /api/v1/cases/{id}/workflow/observation`
3. **Calibrate & Segment**: `POST /api/v1/cases/{id}/workflow/detect-oil`
4. **Trajectory Physics**: `POST /api/v1/cases/{id}/workflow/drift-simulation`
5. **AIS Candidate Correlation**: `POST /api/v1/cases/{id}/workflow/correlate-ais`
6. **Workflow Status**: `GET /api/v1/cases/{id}/workflow/status`
7. **Export Incident Dossier**: `GET /api/v1/cases/{id}/workflow/export-report`

---

## 5. Final Build Documentation & Audits

All deliverables and audit manifests are preserved in `07_results/final_build/`:

- [Final Build Status](07_results/final_build/FINAL_BUILD_STATUS.md) — Test counts, real vs synthetic matrix, model metrics, and CDSE status.
- [90-Second Demo Script](07_results/final_build/DEMO_SCRIPT_90_SECONDS.md) — Exact minute-by-minute operational walkthrough.
- [Judge Evaluation Q&A](07_results/final_build/JUDGE_QA.md) — 10 rigorous answers on science, physics, false positives, and legal neutrality.
- [Final Incident Report (Markdown)](07_results/final_build/VARUNA_FINAL_INCIDENT_REPORT.md) — Comprehensive incident case briefing.
- [Final Incident Report (JSON)](07_results/final_build/VARUNA_FINAL_INCIDENT_REPORT.json) — Machine-readable incident ledger.
- [OilSeg Dataset Audit](07_results/final_build/OILSEG_DATASET_AUDIT.md) — Split isolation and leakage prevention audit.
- [Reuse Audit](07_results/final_build/REUSE_AUDIT.md) — Pre-implementation audit of all 18 repository subsystems.
