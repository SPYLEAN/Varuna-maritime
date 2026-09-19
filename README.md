# VARUNA — Maritime Environmental Intelligence

**Version**: `2.1.0-final` (Build: `final/varuna-24h-build`)  
**Status**: `OPERATIONAL_EVALUATION_READY` | `ALL_TESTS_PASSING`  
**Automated Tests**: **273 passed, 1 skipped, 0 failed** across `backend/tests` and `ml/tests`.

---

## 1. Executive Summary

**VARUNA** is an end-to-end maritime pollution intelligence platform that bridges the gap between raw Synthetic Aperture Radar (SAR) observations and decision-support incident attribution.

Rather than treating dark radar patches as simple thresholded pixels or making premature culpability claims, VARUNA implements a physics-grounded operational chain with transparent execution modes (`REAL`, `SYNTHETIC_DEMO`, `BLOCKED`):
```
INCIDENT
  └── OBSERVATION SEARCH & ATTACH (REAL)
        └── CDSE PRODUCT ACQUISITION (REAL / BLOCKED)
              └── VV / VH CALIBRATION (REAL / SYNTHETIC_DEMO)
                    └── OIL-LIKE SLICK EVIDENCE (SmallUNet Dual-Channel, REAL)
                          └── SLICK VECTOR GEOMETRY (GeoJSON extraction, REAL)
                                └── HINDCAST & FORECAST (OpenDrift / DEMO_APPROXIMATION)
                                      └── AIS CANDIDATE PRIORITIZATION (SYNTHETIC_DEMO)
                                            └── UNCERTAINTY & CRYPTOGRAPHIC PROVENANCE (REAL)
                                                  └── INCIDENT REVIEW & DOSSIER EXPORT (REAL)
```

---

## 2. Key Technical Innovations & Truthful Contracts

- **Radiometrically Truthful SAR Calibration**: Converts Sentinel-1 IW GRD raw digital numbers (DN) to true Sigma0 ($\sigma^0$) backscatter using ESA calibration LUTs. Never confuses generic raster names with verified calibration.
- **OilSeg V1 Synthetic Benchmark**: Dual-channel SmallUNet trained on physically simulated dual-pol (VV/VH) SAR scenes with zero geographic or temporal leakage. Provenance is **`VARUNA_OILSEG_V1_SYNTHETIC_BENCHMARK`** (`data_mode="SYNTHETIC"`). Metrics (**0.9690 IoU**, **0.9842 Dice**, **0.0000 False Positive rate**) are strictly **`SYNTHETIC_BENCHMARK_METRICS`** (`REAL_WORLD_GENERALIZATION_NOT_YET_VALIDATED`).
- **Evidence Gate**: Classifies detections as `PHYSICS_ELIGIBLE`, `REVIEW_REQUIRED`, or `REJECTED_LOOKALIKE` using damping ratios and ambient wind masking. Indicates reduced likelihood of lookalikes under evaluated criteria.
- **Coupled Trajectory Physics**: Supports native OpenDrift Lagrangian particle simulations with NetCDF wind/current forcing. When case-specific forcing is absent, uses `DEMO_TRAJECTORY_APPROXIMATION` explicitly tagged `SYNTHETIC_DEMO`.
- **Strict Maritime Legal Nomenclature**: Prioritizes vessels solely as `INVESTIGATIVE_CANDIDATE` based on spatiotemporal miss distance and trajectory kinematics. Never outputs prejudicial terms like "culprit" or "guilty".
- **Cryptographic Provenance**: Exposes execution modes (`REAL`, `SYNTHETIC_DEMO`, `BLOCKED`) and SHA-256 integrity hashes for all outputs.

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
2. **Acquire Product**: `POST /api/v1/cases/{id}/workflow/acquire` (Truthful check; `BLOCKED` if credentials missing)
3. **Calibrate & Preprocess**: `POST /api/v1/cases/{id}/workflow/preprocess`
4. **Segment Slick Evidence**: `POST /api/v1/cases/{id}/workflow/analyse-slick`
5. **Evidence Gate Selection**: `POST /api/v1/cases/{id}/workflow/select-candidate`
6. **Trajectory Hindcast**: `POST /api/v1/cases/{id}/workflow/hindcast`
7. **Forward Drift Forecast**: `POST /api/v1/cases/{id}/workflow/forecast`
8. **AIS Candidate Correlation**: `POST /api/v1/cases/{id}/workflow/correlate-ais`
9. **Workflow Status**: `GET /api/v1/cases/{id}/workflow`
10. **Export Incident Dossier**: `GET /api/v1/cases/{id}/workflow/incident-review`

---

## 5. Final Build Documentation & Audits

All deliverables and audit manifests are preserved in `07_results/final_build/`:

- [Final Build Status](07_results/final_build/FINAL_BUILD_STATUS.md) — Truthfulness matrix, test counts, model metrics, and commands.
- [90-Second Demo Script](07_results/final_build/DEMO_SCRIPT_90_SECONDS.md) — Operational decision-support walkthrough.
- [Judge Evaluation Q&A](07_results/final_build/JUDGE_QA.md) — 10 rigorous answers on science, physics, lookalikes, and legal neutrality.
- [Final Incident Report (Markdown)](07_results/final_build/VARUNA_FINAL_INCIDENT_REPORT.md) — Decision-support incident briefing.
- [Final Incident Report (JSON)](07_results/final_build/VARUNA_FINAL_INCIDENT_REPORT.json) — Machine-readable incident ledger with stage execution modes.
- [OilSeg Dataset Audit](07_results/final_build/OILSEG_DATASET_AUDIT.md) — Synthetic benchmark isolation and leakage audit.
- [Reuse Audit](07_results/final_build/REUSE_AUDIT.md) — Pre-implementation audit of repository subsystems.
