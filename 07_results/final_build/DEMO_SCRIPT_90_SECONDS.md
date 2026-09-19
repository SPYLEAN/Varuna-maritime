# VARUNA — 90-Second Operational Demo Script

**Target Audience:** Incident Commanders, Maritime Coast Guard, Environmental Regulators, Benchmark Evaluation Judges  
**Time Limit:** Exactly 90 Seconds  
**Focus:** Decision-support workflow with truthful execution modes and transparent uncertainty.

---

## Timeline & Narrative

```
[00:00 - 00:15] INCIDENT INTAKE & OBSERVATION REGISTRATION
[00:15 - 00:30] DUAL-POL SAR CALIBRATION & EVIDENCE GATE
[00:30 - 00:45] TRAJECTORY PHYSICS: HINDCAST & RECEPTOR RISK FORECAST
[00:45 - 01:05] AIS TRAJECTORY CORRELATION & CANDIDATE PRIORITIZATION
[01:05 - 01:20] UNCERTAINTY PROFILE & CRYPTOGRAPHIC PROVENANCE
[01:20 - 01:30] EXECUTIVE DECISION BRIEF & EXPORT
```

---

### Phase 1: [00:00 – 00:15] Incident Intake & Observation Registration

**Visual:** Ops Console Dashboard (`http://localhost:8000/console/`). Open or select case `VARUNA-CASE-2024-0410-NS01`.  
**Narrator (Spoken Script):**
> *"08:00 UTC. Coast Guard Command receives an offshore surface anomaly report. Inside VARUNA, we register the incident. The satellite catalog queries Copernicus CDSE for Sentinel-1 C-band SAR passes. In this demonstration environment, live external CDSE download is truthfully marked as BLOCKED due to absence of credentials, so we ingest verified local observations with complete audit logging."*

---

### Phase 2: [00:15 – 00:30] Dual-Pol SAR Calibration & Evidence Gate

**Visual:** Toggle to Calibrated Radiometric dB view (VV and VH channels). Highlight neural inference layer with `OIL_EVIDENCE_SCORE` confidence overlay.  
**Narrator:**
> *"VARUNA converts dual-polarization backscatter into calibrated decibels. Our dual-channel SmallUNet model—trained on physical backscatter signatures—generates a pixel-wise `OIL_EVIDENCE_SCORE`. The slick geometry is vectorized into GeoJSON polygons. The evidence gate evaluates damping ratios, wind regimes, and shape morphology, certifying the candidate as `PHYSICS_ELIGIBLE` with reduced likelihood of low-wind lookalikes."*

---

### Phase 3: [00:30 – 00:45] Trajectory Physics: Hindcast & Forecast

**Visual:** Interactive Map displaying particle trajectories drifting backward to probable release origin, and forward towards sensitive shorelines.  
**Narrator:**
> *"With verified slick geometry, VARUNA initiates trajectory modeling. A backward hindcast reconstructs the probable release window over the preceding 12 hours. Simultaneously, a forward forecast projects surface transport over the next 48 hours, highlighting critical shoreline strike warnings for downstream marine habitats to guide containment boom staging."*

---

### Phase 4: [00:45 – 01:05] AIS Trajectory Correlation & Candidate Prioritization

**Visual:** Spatiotemporal cone rendered over the hindcast release envelope. AIS vessel tracks crossing the region appear; candidate ranking table updates.  
**Narrator:**
> *"Next, we search for candidate sources. VARUNA correlates AIS vessel trajectory feeds across the hindcast window. We never declare an unverified 'culprit'—instead, our kinematics engine ranks vessels strictly as `INVESTIGATIVE_CANDIDATE`. In this demo case, tanker PACIFIC EXPLORER crossed the release envelope during the estimated window and is assigned top investigative priority, while other regional traffic is systematically filtered."*

---

### Phase 5: [01:05 – 01:20] Uncertainty Profile & Cryptographic Provenance

**Visual:** Click "Uncertainty & Provenance" tab. Display confidence bounds, execution modes, and SHA-256 hash chains.  
**Narrator:**
> *"Every output is scientifically transparent. VARUNA quantifies the spatial uncertainty ellipse, records the meteorological forcing provenance, and exposes the exact execution mode—whether REAL, SYNTHETIC_DEMO, or BLOCKED—for every single stage. Nothing in VARUNA is an opaque black box."*

---

### Phase 6: [01:20 – 01:30] Executive Decision Brief & Export

**Visual:** Click "Export Incident Dossier". Display clean, single-page incident summary dossier ready for command briefing.  
**Narrator:**
> *"In under 90 seconds, command teams transition from raw satellite signals to verified slick geometry, an urgent containment forecast, prioritized vessel candidates, and an audit-ready incident dossier. That is VARUNA: rapid, physics-grounded decision support."*

---

## Live Demo Quick-Reference Checklist

1. **Verify Backend Running:** `python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000`
2. **Open Browser:** `http://localhost:8000/console/`
3. **Execute End-to-End Workflow:**
   - Step 1: Ingest Case / Attach S1 observation (`POST /api/v1/cases/{id}/workflow/acquire`)
   - Step 2: Calibrate & Preprocess (`POST /api/v1/cases/{id}/workflow/preprocess`)
   - Step 3: Segment Oil-Like Slick (`POST /api/v1/cases/{id}/workflow/analyse-slick`)
   - Step 4: Evidence Gate Qualification (`POST /api/v1/cases/{id}/workflow/select-candidate`)
   - Step 5: Trajectory Hindcast (`POST /api/v1/cases/{id}/workflow/hindcast`)
   - Step 6: Forward Drift Forecast (`POST /api/v1/cases/{id}/workflow/forecast`)
   - Step 7: AIS Correlation (`POST /api/v1/cases/{id}/workflow/correlate-ais`)
   - Step 8: Export Dossier (`GET /api/v1/cases/{id}/workflow/incident-review`)
