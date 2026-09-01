# SAMUDRANETRA — DESIGN CONTEXT & ARCHITECTURAL INTENT

## System Mission
SamudraNetra is a production-grade maritime oil-spill investigation platform designed for government maritime authority operators, environmental intelligence analysts, and coast guard investigators.

It integrates:
- Sentinel-1 SAR satellite observations (dual-pol VV/VH)
- ML oil-like slick candidate classification
- OpenDrift Eulerian-Lagrangian ocean particle transport backtracking & forecasting
- Audited metocean forcing (ERA5 wind, HYCOM currents, CMEMS Stokes drift)
- MarineCadastre AIS vessel track correlation & explainable priority ranking
- 11-stage explainable evidence fusion, uncertainty propagation, and cryptographic provenance

## Key Visual Archetypes
- **ESA SNAP / Sentinel Application Platform**: Technical precision, raster band controls, coordinate inspectors.
- **National Maritime Command Centers**: Live situation awareness, incident management, clear status indicators.
- **Geospatial Intelligence Workstations**: GIS map dominance, dark-mode contrast, responsive sidebars.

## Design Constraints
1. **Never hide scientific uncertainty**: Abstention states, physical model limitations, and AIS synthetic demonstration notices must be clear and explicit.
2. **No decorative fake metrics**: Avoid arbitrary "99% AI confidence" badges. Use exact ML Oil-Like Evidence scores (`0.5818` canonical for primary target C4053).
3. **Immutability of science**: The UI presents choices and parameters, but backend physics and validated benchmarks remain canonical.
