# SAMUDRANETRA — Evaluation Panel & Judge Q&A Reference

**Version**: `0.9.0-rc1`

---

### Q1: Why use Synthetic Aperture Radar (SAR) instead of optical imagery?
**A**: SAR C-band radar penetrates cloud cover, operates day and night, and is sensitive to surface roughness attenuation caused by oil slicks, whereas optical sensors are blinded by clouds, darkness, and sunglint.

### Q2: Why is OpenDrift ocean transport backtracking necessary?
**A**: Slicks detected on satellite passes have drifted for hours or days. OpenDrift models ocean currents, wind shear, and wave drift backward in time to reconstruct the candidate release envelope when the spill occurred.

### Q3: How accurate was the blind historical validation on the Mauritius Wakashio benchmark?
**A**: Reconstructed 24h candidate envelope under Scenario C (Currents + Wind + Stokes) achieved **24.17 km boundary distance** from the grounding reference. The offset is due to sub-grid coastal currents and 15-day satellite revisit gap.

### Q4: Is the current AIS vessel data real or synthetic?
**A**: The current AIS dataset is **SYNTHETIC DEMO DATA** designed to validate ranking logic and abstention guards. SamudraNetra strictly displays `SYNTHETIC AIS DEMONSTRATION` badges across all views.

### Q5: How does the system prevent false attribution?
**A**: SamudraNetra implements 7 abstention states (`NO_CREDIBLE_CANDIDATE`, `AMBIGUOUS_ATTRIBUTION`, `INSUFFICIENT_DATA`, etc.) and hard evidence guards. High speed changes or course turns alone cannot trigger high priority without spatial and temporal envelope intersection.

### Q6: Can SamudraNetra declare a vessel legally guilty?
**A**: **No.** SamudraNetra provides explainable *Investigative Priority Scores* for maritime intelligence triage. Legal proof requires physical sampling and official enforcement chain of custody.
