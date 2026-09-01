# SAMUDRANETRA — Architecture Specification

**Version**: `0.9.0-rc1`

---

## Technical Data Flow

```
[Sentinel-1 SAR Product]
       │
       ▼
[SNAP Preprocessing & Dark Spot Extraction]
       │
       ▼
[ML Candidate Classifier & Morphology Triage]
       │
       ▼
[Met-Ocean Forcing (ERA5 / HYCOM / CMEMS)]
       │
       ▼
[OpenDrift Backward Transport Backtracking (24/48/72/96h)]
       │
       ▼
[Forward Physical Closure Validation (Task009C)]
       │
       ▼
[Source Region GeoJSON & Spatiotemporal Windows]
       │
       ▼
[AIS Ingestion & Clean-Room Retrieval Engine]
       │
       ▼
[Explainable AIS Ranking Engine & Abstention Guards]
       │
       ▼
[FastAPI Unified Investigation API (/api/cases/R001_WAKASHIO)]
       │
       ▼
[SamudraNetra Ops Console (FUNCTIONAL_UI_V1)]
```

---

## Engine Subsystems

### 1. Geospatial & ML Subsystem
- **Input**: Sentinel-1B IW GRDH C-band SAR (`2020-08-10T01:38:07Z`).
- **Processing**: Calibration, Speckle Filtering, Threshold Segmentation.
- **ML Classifier**: Gradient-boosted tree evaluating VV/VH backscatter, contrast, aspect ratio, perimeter complexity, and surrounding sea state.

### 2. Physical Transport Subsystem
- **Framework**: `OpenDrift` 1.14.11 (`OceanDrift` physics module).
- **Forcing Sources**:
  - **Wind**: ECMWF ERA5 10m wind vector field.
  - **Ocean Current**: HYCOM global 1/12° surface current.
  - **Wave**: CMEMS Global Ocean Waves (Stokes drift velocity).
- **Physical Scenarios**:
  - **Scenario A**: Currents Only.
  - **Scenario B**: Currents + 3% Wind Drift.
  - **Scenario C**: Currents + 3% Wind + Stokes Drift (Audited Production Baseline).

### 3. Explainable AIS Ranking Subsystem
- **Dynamic Weighting**: 6 components normalized over non-missing evidence dimensions:
  1. Spatial Proximity: `0.30`
  2. Temporal Overlap: `0.25`
  3. Route Alignment: `0.20`
  4. Behavioural Anomaly: `0.10`
  5. AIS Integrity: `0.05`
  6. Physics Support: `0.10`
- **Abstention States**: `NO_CREDIBLE_CANDIDATE`, `AMBIGUOUS_ATTRIBUTION`, `INSUFFICIENT_DATA`, `NON_VESSEL_SOURCE_POSSIBLE`, `PHYSICS_UNCERTAIN`, `NO_VALID_SAR_CANDIDATE`, `DEGRADED_FORCING`.
