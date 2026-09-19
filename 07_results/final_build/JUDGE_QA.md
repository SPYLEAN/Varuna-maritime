# VARUNA — Benchmark Evaluation & Judge Q&A

This document provides rigorous, scientifically grounded answers to the 10 core operational and methodological questions evaluated by benchmark judges, environmental regulators, and maritime authorities.

---

### 1. Why does VARUNA matter if the spill already happened?

**Answer:**  
In maritime spill incidents, the initial satellite detection is only observation time $T_0$. The critical operational response window is $T_0$ to $T_{+72\text{h}}$:
- **Targeted Containment & Resource Staging:** Responders cannot deploy protective containment booms to hundreds of kilometers of coastline simultaneously. Forward drift simulations project shoreline strike probabilities with hour-by-hour time-to-impact estimates, directing physical boom deployment to vulnerable lagoons, mangroves, and marine parks before the slick arrives.
- **Defensible Accountability & Liability:** Oil slicks disperse, emulsify, and dissolve rapidly under ocean waves. Determining source origin and temporal release window requires immediate backwards trajectory reconstruction. Without automated trajectory reconstruction coupled to AIS candidate analysis, responsible parties often escape liability under maritime insurance dispute periods.
- **Operational Scalability:** Coastal agencies monitor large ocean Exclusive Economic Zones (EEZ) daily. Manual imagery screening takes hours; VARUNA executes radiometric calibration, segmentation, trajectory physics, and vessel correlation in minutes.

---

### 2. How do you distinguish a dark SAR patch from oil?

**Answer:**  
SAR imagery measures radar backscatter roughness ($\sigma^0$). Both mineral oil and natural biogenic lookalikes (e.g., algal blooms, grease ice, low-wind calm water patches, internal solitary waves) dampen short Bragg gravity-capillary waves, appearing as dark patches. VARUNA evaluates candidates through a multi-factor **Evidence Gate**:
1. **Dual-Polarization Damping Ratio:** Mineral oil dampens co-polarized (VV) and cross-polarized (VH) backscatter differently than biogenic slicks. VARUNA's `SmallUNet` operates on calibrated two-channel input ($\text{dB}_{VV} \in [-30, 0]$, $\text{dB}_{VH} \in [-35, -5]$), capturing polarization contrast ratios.
2. **Surface Wind Masking:** Biogenic lookalikes only survive in low-wind regimes ($< 3\text{ m/s}$). Under moderate winds ($3 - 10\text{ m/s}$), natural surfactant films break apart, whereas cohesive oil emulsions remain intact. VARUNA checks wind fields at observation time.
3. **Morphology and Boundary Sharpness:** Natural lookalikes often feature diffuse, feathered edges. Mineral slicks display sharper contrast along the leading edge.
4. **Honest Evidentiary Language:** Candidates are categorized as `PHYSICS_ELIGIBLE`, `REVIEW_REQUIRED`, or `REJECTED_LOOKALIKE`. Passing the evidence gate indicates a **reduced likelihood under the evaluated evidence gate** of being a natural lookalike; it does not claim lookalikes are categorically "ruled out" without in-situ chemical sampling.

---

### 3. Why is a nearby vessel not automatically the culprit?

**Answer:**  
Proximity at observation time is an invalid indicator of culpability:
- **Ocean Dynamic Drift:** An oil slick observed at 08:00 UTC at $(x_1, y_1)$ may have been discharged at 02:00 UTC at $(x_0, y_0)$, 15 nautical miles up-current. A vessel currently closest to the slick at 08:00 UTC may have arrived hours after the discharge.
- **Spatiotemporal Kinematics:** VARUNA requires vessels to intersect the **hindcast release envelope** (both in space and time).
- **Strict Legal Nomenclature:** VARUNA adheres to international maritime legal standards. Outputs are strictly labeled `INVESTIGATIVE_CANDIDATE` with transparent candidate scores (0.0 to 1.0) and spatial miss distances. VARUNA never brands an entity as "guilty" or a "culprit," maintaining evidential neutrality required for maritime judicial proceedings.

---

### 4. What if AIS is missing or turned off?

**Answer:**  
"Dark vessels" (ships intentionally disabling their Class A/B AIS transponders) are a known challenge in illicit bilge dumping:
- **Physics Release Envelope Preserved:** Even with zero AIS reception, VARUNA calculates and outputs the exact spatiotemporal release box: $[t_{\text{start}}, t_{\text{end}}]$ and bounding coordinates $(\text{lat}_{\min}, \text{lat}_{\max}, \text{lon}_{\min}, \text{lon}_{\max})$.
- **Explicit Provenance Declaration:** The system marks the AIS correlation status as `NO_CREDIBLE_CANDIDATE` or `AIS_FEED_UNAVAILABLE` rather than hallucinating or failing silently.
- **Interoperability with Radar/VMS:** The calculated release envelope is formatted as standard GeoJSON / OGC polygons, enabling immediate cross-referencing with Coastal Surveillance Radar, VMS (Vessel Monitoring System for fisheries), or commercial RF satellite passes.

---

### 5. What if the physics model says no vessel fits?

**Answer:**  
If all AIS trajectories through the region fail to intersect the hindcast envelope within tolerance thresholds:
- **Clean Fallback:** The workflow returns `NO_CREDIBLE_CANDIDATE` with an explicit diagnostic explanation:
  - Estimated discharge window: $[t_0, t_1]$
  - Nearest vessel miss distance: $\Delta d > \text{threshold}$
  - Temporal discrepancy: $\Delta t > \text{threshold}$
- **Operational Value:** This negative result is equally vital: it prevents authorities from mistakenly detaining innocent vessels, saves coast guard reconnaissance fuel, and flags potential sub-surface pipeline leaks, unrecorded natural seeps, or dark vessels.

---

### 6. How accurate is OpenDrift hindcast?

**Answer:**  
OpenDrift is the standard Lagrangian drift modeling framework maintained by the Norwegian Meteorological Institute (MET Norway), used operationally by international coast guards:
- **Coupled Dynamics:** Trajectory calculations combine 10-meter wind vectors (via GFS / ECMWF with standard 3% wind drift factor) and ocean hydrodynamic current vectors (via HYCOM / Copernicus Marine GLORYS).
- **Uncertainty Ellipses:** Trajectories are not single deterministic lines; OpenDrift simulates ensembles of stochastic numerical particles ($N = 250+$) with turbulent horizontal diffusion ($K_{xy} = 1.0\text{ m}^2/\text{s}$). The resulting particle distribution forms a 95% confidence spatiotemporal ellipse around the release origin.
- **Known Limitations:** Accuracy is fundamentally bounded by meteorological forcing resolution ($0.25^\circ$ for ERA5, $0.083^\circ$ for GLORYS). Complex sub-grid coastal currents, bathymetric reefs, and nearshore wave setups can introduce trajectory offsets.

---

### 7. What is real vs synthetic in this demo?

**Answer:**  
VARUNA maintains complete scientific transparency regarding data provenance:
- **Real Components:**
  - **Calibrated SAR Preprocessing Chain:** Real Sentinel-1 C-band calibration routines in `sar_quicklook.py` using ESA calibration LUTs and Lee speckle filtering.
  - **Segmentation Neural Model:** Real PyTorch `SmallUNet` trained on simulated dual-pol physical backscatter distributions, outputting `OIL_EVIDENCE_SCORE`.
  - **Native OpenDrift Infrastructure:** Real OpenDrift framework integration (`opendrift_hindcast_engine.py`, `opendrift_forecast_engine.py`).
  - **API Architecture & Ops Console:** 100% real FastAPI backend, SQLite/JSON case store, and interactive WebGL/Leaflet frontend.
- **Synthetic / Demo Components:**
  - **CDSE Live Connection:** Marked `REAL_PROVIDER_VALIDATION=BLOCKED` due to absence of credentials in the evaluation environment.
  - **OilSeg V1 Dataset:** Provenance is `VARUNA_OILSEG_V1_SYNTHETIC_BENCHMARK`. Metrics are `SYNTHETIC_BENCHMARK_METRICS`. `REAL_WORLD_GENERALIZATION_NOT_YET_VALIDATED`.
  - **Demo Trajectories:** When case-specific NetCDF forcing is absent, uses `DEMO_TRAJECTORY_APPROXIMATION` tagged `SYNTHETIC_DEMO`.
  - **Demo AIS:** Uses simulated vessel tracks labeled `ais_data_mode=SYNTHETIC_DEMO`.

---

### 8. What happens if the segmentation model is unavailable?

**Answer:**  
System resilience is built into the architecture:
- **Graceful Degradation:** If PyTorch dependencies are missing or model weights are unmounted, `oilseg_v1_adapter.py` returns `status="MODEL_UNAVAILABLE"` rather than throwing an unhandled exception or crashing.
- **Fallback Pathways:** The operator can fall back to adaptive CFAR / Otsu thresholding on calibrated backscatter or upload manual operator annotations.
- **Audit Logging:** The case metadata explicitly records `segmentation_method: "FALLBACK_CFAR"` or `status: "MODEL_UNAVAILABLE"`, preserving complete evidentiary honesty.

---

### 9. How does this reduce real-world environmental damage?

**Answer:**  
1. **Response Time Compression:** Traditional spill workflows involve manual satellite tasking, manual image analysis, disparate drift runs, and disconnected AIS tracking—taking 12 to 24 hours. VARUNA compresses the decision-support chain to minutes.
2. **Targeted Booming:** Shoreline forecasting predicts specific bays and mangroves at risk with time-stamped probabilities, allowing response teams to place protective booms at high-value nurseries before oil enters shallow lagoons.
3. **Optimized Dispersant Application:** Identifies fresh, unemulsified slick core locations where chemical or mechanical recovery remains effective before water-in-oil emulsification occurs.

---

### 10. What makes VARUNA different from just viewing satellite images?

**Answer:**  
Viewing a satellite image merely shows a dark patch at a single frozen moment in time. VARUNA transforms raw imagery into an **actionable intelligence chain**:
1. **Raw Pixel to Calibrated Evidence:** Converts raw digital numbers into calibrated decibel backscatter, eliminating illumination falloff and antenna gain patterns.
2. **Automated Vector Extraction:** Extracts georeferenced boundary polygons with confidence attribution.
3. **Four-Dimensional Dynamics (3D Space + Time):** Bridges the gap between where the anomaly is observed and where it originated (hindcast), plus where it will strike (forecast).
4. **Attribution Engine:** Directly integrates ocean physics with maritime vessel tracking to identify candidate ships.
5. **Audit Provenance:** Every step records software versions, execution modes (`REAL` vs `SYNTHETIC_DEMO`), and SHA-256 hashes, creating an unbroken chain of custody for maritime authorities.
