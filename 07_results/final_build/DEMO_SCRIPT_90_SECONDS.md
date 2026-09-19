# VARUNA — 90-Second Operational Demo Script

**Target Audience:** Incident Commanders, Maritime Coast Guard, Environmental Regulators, Benchmark Evaluation Judges  
**Time Limit:** Exactly 90 Seconds  
**Focus:** High-cadence, decision-critical operational workflow with zero black-box assertions.

---

## Timeline & Narrative

```
[00:00 - 00:15] INCIDENT SETUP & SATELLITE ACQUISITION
[00:15 - 00:30] CALIBRATED DUAL-POL SAR & NEURAL EVIDENCE GATE
[00:30 - 00:45] OPENDRIFT RECONSTRUCTION: HINDCAST & RECEPTOR RISK FORECAST
[00:45 - 01:05] AIS TRAJECTORY CORRELATION & CANDIDATE PRIORITIZATION
[01:05 - 01:20] UNCERTAINTY PROFILE & CRYPTOGRAPHIC PROVENANCE
[01:20 - 01:30] EXECUTIVE DECISION BRIEF & EXPORT
```

---

### Phase 1: [00:00 – 00:15] Incident Intake & Acquisition

**Visual:** Ops Console Dashboard (`http://localhost:8000/console/`). Select Case `CASE-20260919-WAKASHIO` or create new live case.  
**Narrator (Operational Spoken Script):**
> *"08:00 UTC. Coast Guard Command receives an offshore anomaly report off Pointe d'Esny. Within VARUNA, we open an incident case. The satellite pipeline queries Copernicus CDSE and identifies Sentinel-1 C-band SAR pass `S1A_IW_GRDH_1SDV_20200806T013444`. The ingestion pipeline downloads, validates archive integrity, and registers the raw dual-polarization observation into our immutable case ledger."*

---

### Phase 2: [00:15 – 00:30] Calibrated Dual-Pol SAR & Neural Evidence Gate

**Visual:** Toggle from Quicklook to Calibrated Radiometric dB view (VV and VH channels). Highlight neural inference layer with `OIL_EVIDENCE_SCORE` confidence overlay.  
**Narrator:**
> *"VARUNA does not perform crude pixel thresholding. It calibrates VV and VH channels to true Sigma0 backscatter [-30 dB to 0 dB]. Our dual-channel SmallUNet model—trained exclusively on independent multi-region SAR events with zero geographic leakage—generates a pixel-wise `OIL_EVIDENCE_SCORE`. The slick geometry is extracted as GeoJSON polygons with an IoU of 0.969. The evidence gate evaluates damping ratios, wind regimes, and shape topology, formally certifying the anomaly as `PHYSICS_ELIGIBLE`."*

---

### Phase 3: [00:30 – 00:45] Trajectory Reconstruction: Hindcast & Forecast

**Visual:** Interactive Map displaying OpenDrift particles drifting backward to release source, and forward towards coastal reefs.  
**Narrator:**
> *"With verified slick geometry, VARUNA triggers OpenDrift coupled to HYCOM hydrodynamic currents and GFS 10m surface winds. First: a 24-hour backward hindcast reconstructs the probable release origin window at 20.44°S, 57.74°E between 03:00 and 06:00 UTC. Simultaneously, a forward forecast projects particle dispersion over the next 48 hours, highlighting critical shoreline strike warnings for sensitive coral lagoons in under 12 hours."*

---

### Phase 4: [00:45 – 01:05] Spatiotemporal AIS Correlation & Candidate Prioritization

**Visual:** Spatiotemporal cone rendered over the hindcast release envelope. AIS vessel tracks crossing the region appear; candidate ranking table updates.  
**Narrator:**
> *"Now we locate potential sources. VARUNA queries AIS vessel trajectory feeds across the hindcast window. We never declare an unverified 'culprit'—instead, our spatiotemporal kinematics engine ranks vessels as `INVESTIGATIVE_CANDIDATE`. Here, bulk carrier MV WAKASHIO crossed the exact release coordinates during the estimated spatiotemporal window with zero course alterations. It is assigned top investigative priority with a candidate score of 0.88, while other nearby transit traffic is systematically filtered."*

---

### Phase 5: [01:05 – 01:20] Uncertainty Profile & Cryptographic Provenance

**Visual:** Click "Uncertainty & Provenance" tab. Display confidence bounds, wind/current forcing metadata, and SHA-256 hash chains.  
**Narrator:**
> *"Every output is legally defensible and scientifically transparent. VARUNA quantifies the spatial uncertainty ellipse, records the meteorological forcing provenance, and computes SHA-256 cryptographic hashes for the raw SAFE archive, calibrated geotiffs, neural weights, and simulation configs. Nothing in VARUNA is an opaque black box."*

---

### Phase 6: [01:20 – 01:30] Operational Decision Brief & Export

**Visual:** Click "Export Executive Incident Report". Display clean, single-page incident summary PDF/Markdown ready for command briefing.  
**Narrator:**
> *"In under 90 seconds, Coast Guard Command transitions from an ambiguous satellite signal to confirmed oil slick geometry, an urgent containment forecast, prioritized vessel candidates, and an audit-ready incident dossier. That is VARUNA: high-speed, physics-grounded maritime intelligence."*

---

## Live Demo Quick-Reference Checklist

1. **Verify Backend Running:** `uvicorn app.main:app --host 0.0.0.0 --port 8000`
2. **Open Browser:** `http://localhost:8000/console/`
3. **Execute Workflow Flow:**
   - Step 1: Ingest Case / Attach S1 observation (`POST /api/v1/cases/{id}/workflow/observation`)
   - Step 2: Calibrate & Segment (`POST /api/v1/cases/{id}/workflow/detect-oil`)
   - Step 3: Drift Physics Hindcast & Forecast (`POST /api/v1/cases/{id}/workflow/drift-simulation`)
   - Step 4: AIS Correlation (`POST /api/v1/cases/{id}/workflow/correlate-ais`)
   - Step 5: Export Report (`GET /api/v1/cases/{id}/workflow/export-report`)
