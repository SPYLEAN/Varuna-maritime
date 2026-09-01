# VARUNA — 90-SECOND EXECUTIVE JUDGE DEMO SCRIPT

**Application Name:** VARUNA — Maritime Environmental Intelligence Workstation  
**Version:** `v1.0.0-rc1` (Release Tag: `VARUNA-GOV-DEMO-1.0`)  
**Target Audience:** Government agencies, Coast Guard, environmental emergency operators, challenge evaluation panel.

---

## Timed Walkthrough (90 Seconds)

### 00:00 – 00:10 | HOME & PROBLEM STATEMENT
* **Action**: Open VARUNA Operations Home (`http://localhost:8080`).
* **Visual**: Clean, neutral dark graphite desktop UI (`#0D1117`). Active case registry showing incident `R001 — Mauritius`.
* **Script**: *"VARUNA is a government-demo-ready maritime environmental intelligence workstation. It turns satellite SAR radar observations and metocean physics models into actionable investigative leads for oil spill tracking."*

### 00:10 – 00:25 | 01 OBSERVE & 02 ANALYZE
* **Action**: Click `01 OBSERVE`. Toggle between `VV` and `VH` bands. Click `⚡ RUN SLICK DETECTION`.
* **Visual**: Crisp Sentinel-1B SAR radar image displayed against dark canvas. Candidate dark-spot polygons appear. Navigate to `02 ANALYZE` and select candidate `C4053`.
* **Script**: *"In OBSERVE mode, we analyze Sentinel-1B SAR imagery acquired on August 10, 2020. Clicking slick detection extracts dark spots. Select candidate C4053—our ML model assigns a validated oil-like score of 0.5818."*

### 00:25 – 00:45 | 03 RECONSTRUCT (HINDCAST)
* **Action**: Click `⚡ RUN RECONSTRUCTION` to launch OpenDrift backward advection ($T0 \to T-96\text{h}$).
* **Visual**: Switches to `03 RECONSTRUCT` with realistic Esri satellite ocean basemap. 500 OpenDrift particles backtrack across the ocean to reveal the origin source envelope.
* **Script**: *"We trigger OpenDrift backward hindcast under Scenario C—combining ERA5 10m wind, HYCOM currents, and CMEMS Stokes drift. 500 Lagrangian particles reconstruct the backtracked source region at T-96h under model assumptions."*

### 00:45 – 00:55 | 03 RECONSTRUCT (FORECAST)
* **Action**: Click `FORECAST (T0 → T+48h)` subtab.
* **Visual**: Forward particles ($T0 \to T+48\text{h}$) advect northeast toward coastlines, showing forward dispersion envelope.
* **Script**: *"Switching to forward forecast projects oil dispersion through T+48h, powered by continuous metocean forcing to guide coastal containment teams."*

### 00:55 – 01:10 | 04 VESSEL INTELLIGENCE
* **Action**: Navigate to `04 VESSELS`. Click `⚡ USE SYNTHETIC DEMO` then `⚡ RUN VESSEL CORRELATION`.
* **Visual**: AIS vessel track polylines display on satellite map intersecting the source region envelope. `VESSEL_BETA` is highlighted at rank #1.
* **Script**: *"In Vessel Intelligence, we correlate AIS vessel trajectories against the reconstructed source region. VARUNA ranks VESSEL_BETA as the top investigative lead with a priority score of 0.907."*

### 01:10 – 01:25 | 05 REVIEW MATRIX & PROVENANCE
* **Action**: Click `05 REVIEW` to open the Incident Briefing Matrix.
* **Visual**: Structured 11-stage evidence report, historical validation limitations, and cryptographic SHA256 manifest.
* **Script**: *"Finally, REVIEW presents a complete 11-stage briefing matrix with explicit cache vs. live compute execution status and cryptographic SHA256 provenance for court and agency audits."*

### 01:25 – 01:30 | CLOSING VALUE STATEMENT
* **Script**: *"VARUNA bridges raw space assets, ocean physics, and AIS data into a sober, field-ready maritime intelligence workstation."*
