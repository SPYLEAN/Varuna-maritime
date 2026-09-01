# SAMUDRANETRA — 3-Minute Technical Presentation Demo Script

**Target Time**: 3:30  
**Presenter Flow**:

---

### [0:00 - 0:30] 1. The Challenge
> "Every year, thousands of marine oil spills occur in international waters without clear attribution due to cloud cover, delayed satellite revisits, and complex ocean currents. Today we present **SAMUDRANETRA**, an uncertainty-aware maritime intelligence system designed to reconstruct slick origin using physics and AI."

---

### [0:30 - 1:15] 2. SAR Observation & Machine Learning
> "We begin in Stage 01 — **OBSERVE**. Here we load a real Sentinel-1B SAR scene acquired over Mauritius on 10 August 2020. Our morphology classifier extracts 8 dark-spot candidates. Candidate C4053 shows strong VV/VH backscatter contrast with an ML oil-like evidence score of 0.892."

---

### [1:15 - 2:00] 3. OpenDrift Transport Backtracking
> "Moving to Stage 03 — **RECONSTRUCT**. SamudraNetra runs OpenDrift transport physics using audited ERA5 wind, HYCOM current, and CMEMS wave vectors across 24, 48, 72, and 96-hour backward horizons. Notice how particle dispersion expands spatial uncertainty over time."

---

### [2:00 - 2:45] 4. Explainable AIS Ranking & Abstention
> "In Stage 06 — **ATTRIBUTE**, our evidence engine cross-references candidate source envelopes against vessel traffic. Because we strictly enforce clean-room protocols, our system displays **SYNTHETIC AIS DEMONSTRATION**. Notice how our hard evidence guards reject false positives and abstain if evidence is ambiguous."

---

### [2:45 - 3:30] 5. Operational Briefing & Government Vision
> "Finally, in Stage 07 — **REVIEW**, SamudraNetra compiles a complete cryptographic provenance record and supported claims matrix. This provides maritime commanders with explainable, defense-grade intelligence for rapid operational response."
