# VARUNA — GOVERNMENT DEMO RELEASE HANDOVER DOCUMENTATION

**Product Name:** VARUNA — Maritime Environmental Intelligence Workstation  
**Version:** `v1.0.0-rc1`  
**Release Tag:** `VARUNA-GOV-DEMO-1.0`  
**Status:** `GOVERNMENT-DEMO-READY PROTOTYPE` / `READY FOR AGENCY EVALUATION`

---

## 1. Problem Statement & Solution Mapping

| Challenge Requirement | VARUNA System Component | Verification Status |
| :--- | :--- | :--- |
| **Oil Slick Identification from Satellite Imagery** | Sentinel-1 SAR imagery (`VV`/`VH`), adaptive dark-spot extraction, Task008B ML candidate classifier (`C4053 = 0.5818`) | **PASS (VALIDATED)** |
| **Backward Drift Mapping** | OpenDrift Lagrangian advection engine using ECMWF ERA5 wind, HYCOM 1/12° currents, and CMEMS wave drift | **PASS (VALIDATED)** |
| **Forward Drift Mapping** | OpenDrift forward forecast advection ($T0 \to T+48\text{h}$) | **PASS (LIVE COMPUTE)** |
| **AIS Spatiotemporal Correlation** | MarineCadastre AIS trajectory engine intersecting backtracked source region window | **PASS (LIVE COMPUTE)** |
| **Rank Potential Vessel Leads** | Multi-factor Spatiotemporal Priority scoring (`VESSEL_BETA` = Priority `0.907`) | **PASS (VALIDATED)** |
| **Visual Workstation Interface** | Dual-canvas architecture: Remote sensing SAR canvas (`OBSERVE`/`ANALYZE`) + Geographic GIS satellite map (`RECONSTRUCT`/`VESSEL INTELLIGENCE`) | **PASS (VALIDATED)** |

---

## 2. Scientific System Architecture & Canonical Values

* **Satellite SAR Product**: `S1B_IW_GRDH_1SDV_20200810T013755_20200810T013820_022854_02B625_672D`
* **Scene Acquisition Timestamp**: `2020-08-10T01:38:07.500Z`
* **Primary Candidate Hypothesis**: `C4053` (ML Oil-Like Evidence Score: `0.5818`)
* **Morphological Triage Hierarchy**: `>4,000` raw morphological features $\to$ `45` primary review candidate groups $\to$ `8` physics-eligible source candidate hypotheses.
* **Top AIS Lead**: `VESSEL_BETA` (Investigative Priority Score: `0.907`)

### Historical Validation Interpretation:
> *"The blind best hypothesis (C4053) achieved moderate historical compatibility, localizing the reference source to approximately 24 km at the 24 h horizon under current + wind + Stokes forcing (Scenario C)."*

---

## 3. Execution Provenance & Disclaimers

* **Cache vs Live Execution**:
  * **SAR Detection & Candidate Triage**: `VALIDATED CACHED RESULT`
  * **OpenDrift Hindcast**: `VALIDATED CACHED RESULT`
  * **OpenDrift Forward Forecast**: `LIVE COMPUTE`
  * **AIS Vessel Correlation**: `LIVE COMPUTE`
* **Synthetic AIS Disclosure**:
  * Synthetic regional AIS data is utilized in accordance with challenge guidance. Historical vessel attribution is not legally valid under current synthetic mode.

---

## 4. API Endpoint Reference

* `GET /api/investigations/{id}`: Returns investigation case state and candidate metadata.
* `POST /api/investigations/{id}/detect`: Triggers candidate detection pipeline.
* `POST /api/investigations/{id}/reconstruct`: Executes OpenDrift backward hindcast.
* `POST /api/investigations/{id}/forecast`: Executes OpenDrift forward forecast.
* `POST /api/investigations/{id}/correlate`: Runs AIS spatiotemporal vessel correlation.

---

## 5. Offline Fallback & Reliability

* **Bundled Local Map Engine**: Production-grade `leaflet.js` and `leaflet.css` are bundled locally inside `ops_console/`, ensuring 100% offline map availability and zero `L is not defined` errors.
* **Cached Benchmark Fallback**: Local cached benchmark assets (`R001`) allow complete operational walkthrough even if external metocean APIs are unreachable.
