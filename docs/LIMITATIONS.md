# SAMUDRANETRA — Scientific & Operational Limitations

**Version**: `0.9.0-rc1`

---

## 1. Physical & Satellite Sensor Limitations

- **SAR Lookalikes**: Low-wind regions (<3 m/s), biogenic slicks, grease ice, and rain cells create backscatter attenuation mimicking oil slicks.
- **Satellite Revisit Interval**: Sentinel-1 revisit cycles (6–12 days over open oceans) mean slicks observed at $T_0$ may have weathered, dispersed, or drifted 100+ km from initial release.
- **Sub-Grid Coastal Oceanography**: Global 1/12° HYCOM current forcing lacks fine-scale reef and lagoon bathymetry shear, leading to spatial dispersion errors near land masses.
- **Irreversible Weathering**: Backward transport models particle advection but cannot reverse physical oil evaporation, emulsification, or dissolution.

---

## 2. AIS & Attribution Limitations

- **Synthetic AIS Demo Data**: AIS candidate tracks for Mauritius R001 are currently **SYNTHETIC DEMO DATA**. No real historical vessel attribution is made.
- **AIS Spoofing / Dark Fleets**: Transponders disabled, falsified MMSI, or gap events reduce track continuity.
- **Correlation vs Causation**: A vessel occupying a compatible spatiotemporal envelope does not legally prove operational discharge without physical sampling or SAR slick continuity.

---

## 3. Single-Case Historical Validation Result

- **Mauritius R001 Wakashio**: Reconstructed 24h source envelope achieved **24.17 km boundary distance** from the grounding location.
- **Conclusion**: Single-case benchmark demonstrates physical transport feasibility within 25 km, but multi-case validation across diverse oceanographic regimes is required before operational deployment.
