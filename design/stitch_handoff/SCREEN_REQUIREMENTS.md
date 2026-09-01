# SAMUDRANETRA — WORKSTATION SCREEN REQUIREMENTS

## 1. OPERATIONS HOME
- **Header**: System Title (`SamudraNetra — Maritime Environmental Intelligence`), System Health (`SYSTEM READY`), Quick Action (`+ NEW INVESTIGATION`).
- **Case Dashboard**: Active case cards (`R001_WAKASHIO`, `CUSTOM_CASE`), operational status badges (`DATA_READY`, `ANALYST_REVIEW_REQUIRED`), quick metrics (Observations, Candidates, Leads).
- **Incident Modal**: Benchmark vs Custom mode selector, GeoTIFF upload drag-and-drop zone, MarineCadastre AIS CSV uploader.

## 2. 01 OBSERVE (SAR Imagery)
- **Canvas**: Sentinel-1B SAR scene overlay.
- **Controls**: Band Selector (`VV`, `VH`, `Dual-Pol Ratio`), Opacity slider, Coordinate Probe (Lat, Lon, VV dB, VH dB).
- **Metadata Panel**: Satellite Product ID (`S1B_IW_GRDH_1SDV_20200810...`), Acquisition Timestamp (`2020-08-10T01:38:07.500Z`), Orbit, Polarization (`VV+VH`), Mode (`IW`).
- **Primary Action**: `RUN SLICK DETECTION`.

## 3. 02 ANALYZE (Slick Candidate Triage)
- **Canvas**: SAR raster with dark-spot candidate polygon overlays.
- **Candidate Hierarchy**: Display `8 PHYSICS-ELIGIBLE CANDIDATE HYPOTHESES FROM 45 TRIAGED CANDIDATE GROUPS`.
- **Selected Candidate Card**: Candidate ID (`C4053`), ML Oil-Like Score (`0.5818`), Area (`1.42 km²`), Elongation (`3.18`), Mean VV dB (`-26.4 dB`), Coastal Distance (`1.2 km`).
- **Primary Action**: `RUN RECONSTRUCTION`.

## 4. 03 RECONSTRUCT (Hindcast & Forecast Physics)
- **Tabs**: `HINDCAST (T0 → T-96h)` | `FORECAST (T0 → T+48h)`.
- **Hindcast Panel**: Scenario Selector (`Scenario A: Currents`, `Scenario B: Wind`, `Scenario C: Wind+Stokes`), Timestep Scrubber ($T-24\text{h}, T-48\text{h}, T-72\text{h}, T-96\text{h}$), Particle Count (`500`), Source Envelope Area (`24.8 km²`).
- **Forecast Panel**: Horizon Selector ($T+6\text{h}, T+12\text{h}, T+24\text{h}, T+48\text{h}$), Dispersion Radius (`2.85 km`), Forcing Support (`FULL FORCING SUPPORT`), Last Valid Forcing TS (`2020-08-12T03:00Z`), Metocean Forcing (`ERA5 / HYCOM / CMEMS`).
- **Primary Action**: `RUN VESSEL CORRELATION`.

## 5. 04 VESSEL INTELLIGENCE (AIS Lead Ranking)
- **Canvas**: Source region envelope polygon intersected with vessel track polylines.
- **AIS Mode Indicator**: `SYNTHETIC DEMONSTRATION AIS` (with disclaimer: `Synthetic regional AIS is used when real historical AIS is unavailable`).
- **Ranked Vessel List**:
  - `VESSEL_BETA` — Priority `0.907` (`PRIMARY LEAD`), Distance `0.85 km`, Gap `None`.
  - `VESSEL_ALPHA` — Priority `0.584` (`SECONDARY LEAD`), Distance `4.12 km`, Speed `11.2 kts`.
  - `VESSEL_GAMMA` — Priority `0.312` (`LOW PRIORITY`), Distance `12.4 km`, Speed `18.5 kts`.
- **Primary Action**: `GENERATE REVIEW BRIEFING`.

## 6. 05 REVIEW (11-Stage Briefing Matrix & Provenance)
- **11-Stage Briefing Table**: Summary of Observation, Detection, Characterization, Hindcast, Forecast, Source Region, AIS, Ranking, Uncertainty, Limitations, Provenance.
- **Uncertainty & Limitation Matrix**: Physical shear sensitivity, model assumptions, AIS gap risk.
- **Cryptographic Provenance**: SHA256 hashes of input rasters, forcing files, model adapters, and execution manifests.
