# VARUNA — Maritime Environmental Intelligence

**Version**: `2.4.0-final` (Build: `hackathon/response-intelligence-ui`)  
**Status**: `OPERATIONAL_EVALUATION_READY` | `ALL_TESTS_PASSING`  
**Automated Tests**: **298 passed, 2 deselected** across `backend/tests` and `ml/tests`.

---

## 1. What VARUNA Is

**VARUNA** is an enterprise maritime pollution response workstation and intelligence engine. It bridges the gap between raw spaceborne Synthetic Aperture Radar (SAR) observations, physical transport modeling, and operational coastal protection.

Unlike basic satellite viewers that display dark patches as arbitrary polygons or leap to premature culpability claims, VARUNA implements a rigorous 11-stage operational chain that maintains end-to-end truthfulness contracts (`REAL`, `SYNTHETIC_DEMO`, `BLOCKED`):

```
INCIDENT REGISTRATION (REAL)
  └── OBSERVATION SEARCH & ATTACH (Copernicus CDSE STAC, REAL)
        └── CDSE PRODUCT ACQUISITION (REAL / BLOCKED)
              └── VV / VH CALIBRATION (Sigma0 Decibels, REAL / SYNTHETIC_DEMO)
                    └── OIL-LIKE SLICK EVIDENCE (SmallUNet Dual-Channel, REAL)
                          └── SLICK VECTOR GEOMETRY (GeoJSON extraction, REAL)
                                └── HINDCAST & FORECAST (OpenDrift Lagrangian / DEMO_APPROXIMATION)
                                      └── RESPONSE PRIORITIZATION (Marine Receptors & Arrival Windows, REAL)
                                            └── AIS CANDIDATE PRIORITIZATION (INVESTIGATIVE_CANDIDATE, SYNTHETIC_DEMO)
                                                  └── UNCERTAINTY & SHA-256 PROVENANCE (REAL)
                                                        └── INCIDENT DOSSIER EXPORT & DECISION SUPPORT (REAL)
```

---

## 2. Key Technical Innovations & Truthful Contracts

- **Radiometrically Truthful SAR Calibration**: Converts Sentinel-1 IW GRD raw digital numbers (DN) to true Sigma0 ($\sigma^0$) backscatter using ESA calibration LUTs. Never confuses uncalibrated rasters with verified radiometric physical units.
- **OilSeg V1 Synthetic Benchmark**: Dual-channel SmallUNet trained on simulated dual-pol (VV/VH) SAR scenes with zero geographic or temporal leakage. Provenance: `VARUNA_OILSEG_V1_SYNTHETIC_BENCHMARK`. Metrics (**0.9690 IoU**, **0.9842 Dice**, **0.0000 False Positive rate**) are strictly **`SYNTHETIC_BENCHMARK_METRICS`** (`REAL_WORLD_GENERALIZATION_NOT_YET_VALIDATED`).
- **Evidence Gate**: Classifies detections as `PHYSICS_ELIGIBLE`, `REVIEW_REQUIRED`, or `REJECTED_LOOKALIKE` using damping ratios and ambient wind masking.
- **Marine Response Prioritization**: Calculates explainable operational threat rankings and time-to-impact arrival horizons for sensitive ecological and economic assets (coral reefs, aquaculture, mangroves, beaches, and fisheries).
- **Strict Maritime Legal Nomenclature**: Prioritizes vessels solely as `INVESTIGATIVE_CANDIDATE` based on spatiotemporal miss distance and trajectory kinematics. The platform strictly forbids prejudicial labels like "culprit" or "guilty". Non-vessel incidents (e.g. offshore platforms) trigger explicit **`ATTRIBUTION ABSTAINED (NON-VESSEL)`**.
- **SHA-256 Integrity Provenance**: Exposes execution modes (`REAL`, `SYNTHETIC_DEMO`, `BLOCKED`) and SHA-256 cryptographic digests for all processed artifacts and model checkpoints.

---

## 3. Quickstart & Verification

Follow these exact commands to launch and verify VARUNA on any host:

### Prerequisites & Environment Setup
```powershell
# Activate virtual environment (Python 3.12)
.\.venv\Scripts\Activate.ps1

# Install dependencies if starting fresh
pip install -r requirements.txt
```

### Run Automated Test Suite
```powershell
# Run the complete test suite (298 passed, 0 failures)
python -m pytest backend/tests ml/tests -q
```

### Start Server
```powershell
# Launch FastAPI backend daemon (serves both API and Ops Console)
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

### Verified Service URLs
- **Operations Console**: `http://localhost:8000/console/` (or `http://127.0.0.1:8000/console/`)
- **API Health Check**: `http://localhost:8000/health` (returns `{"status":"healthy"}`)
- **System Readiness**: `http://localhost:8000/ready` (returns `{"status":"READY"}`)
- **Version Endpoint**: `http://localhost:8000/version` (returns `{"version":"2.0.0-rc1"}`)
- **Interactive OpenAPI Documentation**: `http://localhost:8000/docs`
- **Machine-Readable OpenAPI Schema**: `http://localhost:8000/openapi.json`

---

## 4. AWS Usage

VARUNA transparently identifies all cloud services utilized versus local compute:

| Component | Technology | AWS / Cloud Service | Execution Reality |
| :--- | :--- | :--- | :--- |
| **Intelligence Agent** | AWS Strands Agents SDK (`strands-agents 1.56.0`) | AWS Bedrock / Strands | Invocable when credentials exist; uses **`DETERMINISTIC_GROUNDED_FALLBACK`** if absent. |
| **Foundation LLM** | Claude 3 Haiku (`anthropic.claude-3-haiku-20240307-v1:0`) | Amazon Bedrock Runtime | Queried for operational decision-support summaries; strictly factual prompt grounding. |
| **SAR Segmentation** | PyTorch SmallUNet (Dual-pol VV/VH) | Local Compute / CPU-GPU | Runs locally on tiled GeoTIFF rasters; does not require cloud inference. |
| **Drift Simulation** | OpenDrift Lagrangian Engine | Local Compute | Local trajectory solver coupled to local metocean NetCDF forcing. |
| **Kinematic AIS** | GeoPandas & SciPy KDTree | Local Compute | Local distance minimization and candidate ranking. |

---

## 5. AI Tools Used

In accordance with hackathon guidelines, the following AI tools contributed to the development and hardening of VARUNA:
1. **Google Antigravity**: Primary agentic coding environment used for repository architecture, end-to-end multi-case wiring, automated test authoring, test execution auditing, and truthfulness compliance verification.
2. **Anthropic Claude**: Operational decision-support agent integrated through Amazon Bedrock and AWS Strands for evidence-grounded natural-language briefings.

---

## 6. Known Limitations

- **Copernicus CDSE Live Download**: Returns `BLOCKED` when `CDSE_USER` and `CDSE_PASS` credentials are not present in the host environment. The system never fabricates a satellite download.
- **Drift Forcing Data**: Backward hindcasts and forward forecasts fall back to `SYNTHETIC_DEMO` kinematic approximations when high-resolution hydrodynamic NetCDF files for the specific incident region are unavailable locally.
- **Attribution Abstention**: For fixed offshore installations (such as Deepwater Horizon, Case `R005`), the platform deliberately suppresses vessel correlation and reports `ATTRIBUTION ABSTAINED (NON-VESSEL)`.
- **Bedrock Offline Mode**: When AWS IAM credentials are not configured, `/api/v1/intelligence/status` truthfully reports `DETERMINISTIC_FALLBACK` and serves validated, template-grounded decision summaries.

---

## 7. Factual Project Timeline

All historical timestamps and metrics originate directly from the `git` commit ledger:

- **First Commit**: `cf3cff6` — `Thu Aug 27 19:39:07 2026 +0530` ("Initial commit").
- **Pre-Event Baseline**: `5fdafe4` — `Sun Sep 6 20:24:24 2026 +0530` (Tag: `pre-event-baseline`).
  - *Pre-Event Scope (16 commits)*: Established preliminary SAR calibration scripts, dual-pol SmallUNet ML architecture, initial OpenDrift wrapper, and basic frontend mockups.
- **In-Event Development (Hackathon Tour)**:
  - *Diff from Baseline*: `77 files changed, 16,903 insertions(+), 252 deletions(-)` (`pre-event-baseline..HEAD`).
  - *Deliverables*:
    1. Multi-Case Engine & Canonical Case Registry (`R001` through `R005`).
    2. Real Copernicus STAC catalog search and product metadata parser.
    3. Marine Response Priority Engine with explainable receptor threat horizons.
    4. AWS Strands Agents & Amazon Bedrock Intelligence Integration with deterministic fallback.
    5. Enterprise Operations Console (`ops_console`) mounted at `/console` with real-time domain switching.
    6. Comprehensive 298-test automated verification gauntlet.

---

## 8. Final Build Documentation & Audits

- [Final Build Status](07_results/final_build/FINAL_BUILD_STATUS.md) — Exact test counts, execution logs, and truthfulness matrix.
- [OpenAPI Coverage Matrix](07_results/final_build/endpoint_coverage_matrix.md) — 106 operations mapped to UI elements.
- [Claims Audit Report](07_results/final_build/claims_audit_report.md) — Rigorous terminology and evidentiary verification.
- [90-Second Demo Script](07_results/final_build/DEMO_SCRIPT_90_SECONDS.md) — Operational walkthrough for evaluators.
- [Judge Evaluation Q&A](07_results/final_build/JUDGE_QA.md) — Scientific and legal answers on SAR, physics, and attribution.
- [Final Incident Report (Markdown)](07_results/final_build/VARUNA_FINAL_INCIDENT_REPORT.md) — Decision-support briefing for R001.
