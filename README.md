# SAMUDRANETRA — Maritime Intelligence & Oil Spill Investigation Platform

**Version**: `0.9.0-rc1`  
**Status**: `PRODUCTION_CANDIDATE` | `FUNCTIONAL_CORE_FROZEN`  
**Case Study**: Mauritius R001 MV Wakashio Incident Investigation  

---

## System Overview

**SamudraNetra** is an uncertainty-aware marine oil-spill investigation system that combines satellite Synthetic Aperture Radar (SAR) observations, machine learning, ocean transport physics (OpenDrift), backward-to-forward physical closure validation, and explainable AIS vessel movement evidence ranking.

---

## The 5-Stage Investigation Workflow

1. **OBSERVE**: Satellite SAR anomaly detection, polarimetric backscatter analysis (VV/VH), dark-spot extraction, and product metadata verification.
2. **INVESTIGATE**: Morphology filtering, geometrical feature scoring, ML oil-like classifier score (`0.892`), and candidate hypothesis triage.
3. **RECONSTRUCT**: OpenDrift ocean transport backtracking driven by audited ERA5 ocean winds, HYCOM surface currents, and CMEMS Stokes drift forcing across 24h, 48h, 72h, and 96h backward horizons.
4. **ATTRIBUTE**: Explainable AIS candidate ranking under `SYNTHETIC_DEMO` mode, hard evidence guards (spatial/temporal/behavioural false-positive rejection), and dynamic weight normalization.
5. **REVIEW**: Unified evidence fusion table, limitations matrix, supported claims contract, data freshness timestamps, cryptographic provenance verification, and analyst briefing report.

---

## Mauritius R001 Case Study Results

- **Primary SAR Candidate**: `C4053` (Area: 1.42 km², VV Median: -18.4 dB, VH Median: -24.8 dB, ML Evidence Score: `0.892`).
- **Blind Historical Compatibility**: Candidate `C4053` at 24h backward horizon under Scenario C (Currents + Wind + Stokes) achieved **24.17 km boundary distance** and **24.64 km centroid distance** from the canonical held-out reference.
- **Original Blind Transport Rank**: `#6` out of 8 candidate hypotheses.
- **Historical Grounding Contained**: **NO** (24 km offset due to sub-grid coastal current shear and 15-day satellite revisit gap).
- **AIS Data Mode**: `SYNTHETIC_DEMO` (Demonstration logic engine; historical vessel attribution is strictly **NOT VALID**).

---

## Local Development & Production Launcher

```powershell
# Launch both FastAPI Backend (8000) and Ops Console Frontend (8080)
.\scripts\start-production.ps1
```

- **Ops Console Workstation**: `http://localhost:8080`
- **FastAPI API Base**: `http://localhost:8000/api/cases/R001_WAKASHIO`
- **Health Check**: `http://localhost:8000/health`
- **Readiness Check**: `http://localhost:8000/ready`
- **OpenAPI Documentation**: `http://localhost:8000/docs`
