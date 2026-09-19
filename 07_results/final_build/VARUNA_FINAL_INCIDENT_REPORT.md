# VARUNA — Final Maritime Incident Intelligence Dossier

**Incident Identifier:** `VARUNA-CASE-2024-0410-NS01`  
**Dossier Reference:** `VARUNA-REPORT-FINAL-20260919`  
**Generated UTC:** `2026-09-19T15:45:00Z`  
**Target Incident:** North Sea Offshore Surface Anomaly  
**Operational Status:** `INCIDENT_REVIEW_COMPLETED`  
**Decision Support Classification:** `INVESTIGATIVE_DECISION_SUPPORT_ONLY`

---

## 1. Stage Execution Modes & Provenance Summary

VARUNA enforces strict evidentiary truthfulness across every pipeline stage:

| Pipeline Stage | Execution Mode | Engine / Provider | Truthful Provenance Status |
|---|---|---|---|
| **1. Observation Search & Attach** | `REAL` | Internal Registry | Attached observation record registered in case ledger |
| **2. CDSE Product Acquisition** | `BLOCKED` | Copernicus CDSE OData | Credentials absent in environment; exact archive not cached |
| **3. SAR Preprocessing** | `SYNTHETIC_DEMO` | Varuna Demo Generator | Calibrated dB format; `SOURCE_ARCHIVE_SHA256=NONE` |
| **4. Slick Segmentation** | `REAL` | SmallUNet Dual-Channel | Trained PyTorch model; output: `OIL_EVIDENCE_SCORE` |
| **5. Evidence Gate** | `REAL` | Multi-Factor Rules Engine | Candidate evaluated: `PHYSICS_ELIGIBLE` |
| **6. Hindcast Reconstruction** | `SYNTHETIC_DEMO` | Demo Trajectory Approximation | Kinematic demo envelope; forcing: `NONE` |
| **7. Forward Risk Forecast** | `SYNTHETIC_DEMO` | Demo Trajectory Approximation | Simulated horizon cones; forcing: `NONE` |
| **8. AIS Vessel Correlation** | `SYNTHETIC_DEMO` | AIS Candidate Engine | Simulated traffic; `ais_data_mode=SYNTHETIC_DEMO` |
| **9. Incident Review Export** | `REAL` | Case Dossier Generator | Multi-stage evidence aggregation and audit export |

---

## 2. Response Intelligence Briefing

### What Was Observed?
Dual-polarization SAR backscatter depression displaying approximately 11.2 dB VV damping and 8.7 dB VH damping over a contiguous area of 1.24 km² ($1,242,000\text{ m}^2$). The anomaly exhibits an elongated curvilinear morphology aligned with the regional wind-shear axis.

### Is It Plausibly Oil?
**Yes (`PHYSICS_ELIGIBLE`).**
The candidate slick was evaluated through the Varuna Evidence Gate:
- **Mean Oil Evidence Score:** `0.8842` (Max: `0.9851`)
- **Evidence Gate Decision:** `PHYSICS_ELIGIBLE` (Overall confidence: `0.882`)
- **Lookalike Assessment:** The candidate passed the current evidence gate. There is a **reduced likelihood under the evaluated evidence gate** of low-wind calm water or biogenic surfactant films based on dual-polarization damping contrast and boundary sharpness. Natural lookalikes are not fully ruled out without in-situ chemical sampling.

### Where Is It Moving Next?
Under the demonstration kinematic transport model, the candidate centroid drifts East-Northeast ($068^\circ$) at approximately $0.32\text{ m/s}$. Note: This projection is a `SYNTHETIC_DEMO` kinematic approximation. In an actual operational deployment, full OpenDrift Lagrangian particle physics coupled to live GFS winds and CMEMS currents must be executed.

### What Resources Are Threatened?
Downstream coastal lagoon habitats and offshore fishing grounds are situated within the extended 48-hour projection cone. Immediate nearshore shoreline impact within 24 hours is assessed as **LOW**, providing an operational window for containment boom staging.

### Probable Origin Window
- **Engine:** `DEMO_TRAJECTORY_APPROXIMATION` (`SYNTHETIC_DEMO`)
- **Estimated Release Window:** `2024-04-09T12:23:14Z` to `2024-04-10T00:23:14Z` (12-hour duration)
- **Probable Release Envelope Centroid:** `[2.42°E, 53.44°N]`
- **Uncertainty Radius:** $\pm 4.8\text{ km}$

---

## 3. AIS Candidate Prioritization

Candidate vessels are strictly categorized using neutral maritime investigative terminology: **`INVESTIGATIVE_CANDIDATE`**. No entity is declared "guilty" or branded a "culprit."

> [!WARNING]
> **Data Mode Notice:** All AIS vessel tracks in this case are `SYNTHETIC_DEMO` simulated tracks. Proximity to a modeled release envelope indicates spatiotemporal compatibility only, and does not constitute proof of illicit discharge.

| Designation | Vessel Name | IMO / MMSI | Vessel Type | AIS Mode | Priority Score | Spatiotemporal Compatibility |
|---|---|---|---|---|:---:|---|
| `INVESTIGATIVE_CANDIDATE` | **PACIFIC EXPLORER** | `9412345` / `563082000` | Crude Oil Tanker | `SYNTHETIC_DEMO` | **0.84** | Closest approach: 1.2 km from release envelope; speed drop from 14.2 kn to 7.8 kn |
| `INVESTIGATIVE_CANDIDATE` | **NORDIC TRADER** | `9678901` / `219001452` | Bulk Carrier | `SYNTHETIC_DEMO` | **0.52** | Passed 4.8 km south of release envelope 2.5 hours prior |

---

## 4. Model Architecture & Synthetic Benchmark Evaluation

- **Architecture:** Dual-channel `SmallUNet` (VV and VH calibrated dB input)
- **Model Checkpoint:** `models/oil_detection/varuna_oilseg_v1_smallunet.pt`
- **Checkpoint SHA-256:** `dda8fac84e6ceedcef76889acc78f8c6eb07d2d586ff00bf4dfbbf656da46e0b`
- **Dataset Provenance:** `VARUNA_OILSEG_V1_SYNTHETIC_BENCHMARK` (`data_mode="SYNTHETIC"`)
- **Validation Scope:** `SYNTHETIC_BENCHMARK_METRICS` (`REAL_WORLD_GENERALIZATION_NOT_YET_VALIDATED`)

| Metric | Synthetic Benchmark Score | Evaluation Scope |
|---|---|---|
| **Synthetic Test IoU** | **0.9690** | Held-out synthetic test scenes |
| **Synthetic Test Dice** | **0.9842** | Held-out synthetic test scenes |
| **Synthetic Precision** | **0.9801** | Held-out synthetic test scenes |
| **Synthetic Recall** | **0.9885** | Held-out synthetic test scenes |
| **Lookalike FP Scene Rate** | **0.0000** | Simulated low-wind attenuation scenes |
| **No-Oil FP Scene Rate** | **0.0000** | Simulated clean sea scenes |

---

## 5. Scientific Limitations & Evidentiary Boundaries

1. **Neural Model Uncertainty:** Outputs an uncalibrated empirical `OIL_EVIDENCE_SCORE`. While trained on physical backscatter signatures, **real-world generalization has not yet been validated** on emergency in-situ satellite passes.
2. **Atmospheric & Oceanographic Uncertainty:** The demonstration trajectory engine utilizes kinematic spatial offsets (`DEMO_TRAJECTORY_APPROXIMATION`). Real-world attribution requires validated NetCDF metocean forcing (ERA5/HYCOM).
3. **AIS Correlation Limitations:** Vessel correlation establishes spatiotemporal compatibility only. True evidential attribution requires aerial surveillance, multispectral satellite verification, or physical water sampling.
