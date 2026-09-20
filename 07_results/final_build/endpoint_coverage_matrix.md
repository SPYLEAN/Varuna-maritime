# VARUNA — OpenAPI Endpoint to UI Coverage Matrix

**Total Operations Evaluated:** 106  
- **Wired in UI:** 58  
- **Not User-Facing (Infrastructure, Diagnostics, Raw Downloads, Legacy Aliases):** 48  
- **Missing User-Facing Endpoints:** 0  

| Method | Endpoint Path | Target UI Element / Component | Status | Operational Role |
|:---|:---|:---|:---:|:---|
| `GET` | `/api/cases` | Legacy Benchmark Adapter (Internal compatibility layer) | **NOT USER-FACING** | List Cases |
| `POST` | `/api/cases` | Legacy Benchmark Adapter (Internal compatibility layer) | **NOT USER-FACING** | Create Investigation |
| `GET` | `/api/cases/{case_id}` | Legacy Benchmark Adapter (Internal compatibility layer) | **NOT USER-FACING** | Get Unified Case |
| `GET` | `/api/cases/{case_id}/ais` | Legacy Benchmark Adapter (Internal compatibility layer) | **NOT USER-FACING** | Get Ais Summary |
| `POST` | `/api/cases/{case_id}/ais` | Legacy Benchmark Adapter (Internal compatibility layer) | **NOT USER-FACING** | Ingest Ais Data |
| `GET` | `/api/cases/{case_id}/attribution` | Legacy Benchmark Adapter (Internal compatibility layer) | **NOT USER-FACING** | Get Attribution State |
| `POST` | `/api/cases/{case_id}/automate` | Legacy Benchmark Adapter (Internal compatibility layer) | **NOT USER-FACING** | Trigger Automated Investigation |
| `GET` | `/api/cases/{case_id}/candidates` | Legacy Benchmark Adapter (Internal compatibility layer) | **NOT USER-FACING** | Get Candidates Summary |
| `POST` | `/api/cases/{case_id}/correlate` | Legacy Benchmark Adapter (Internal compatibility layer) | **NOT USER-FACING** | Trigger Vessel Correlation |
| `POST` | `/api/cases/{case_id}/detect` | Legacy Benchmark Adapter (Internal compatibility layer) | **NOT USER-FACING** | Trigger Slick Detection |
| `GET` | `/api/cases/{case_id}/evidence` | Evidence Gate & Data Manifest Table (#evidence-manifest-list) | **WIRED** | Get Evidence Fusion Table |
| `POST` | `/api/cases/{case_id}/forecast` | Legacy Benchmark Adapter (Internal compatibility layer) | **NOT USER-FACING** | Trigger Forward Forecast |
| `GET` | `/api/cases/{case_id}/forward-validation` | Legacy Benchmark Adapter (Internal compatibility layer) | **NOT USER-FACING** | Get Forward Validation |
| `GET` | `/api/cases/{case_id}/hindcast` | Legacy Benchmark Adapter (Internal compatibility layer) | **NOT USER-FACING** | Get Hindcast Physics |
| `GET` | `/api/cases/{case_id}/provenance` | Legacy Benchmark Adapter (Internal compatibility layer) | **NOT USER-FACING** | Get Provenance |
| `POST` | `/api/cases/{case_id}/reconstruct` | Legacy Benchmark Adapter (Internal compatibility layer) | **NOT USER-FACING** | Trigger Hindcast Reconstruction |
| `GET` | `/api/cases/{case_id}/review` | Legacy Benchmark Adapter (Internal compatibility layer) | **NOT USER-FACING** | Get Investigation Review |
| `GET` | `/api/cases/{case_id}/sar` | Legacy Benchmark Adapter (Internal compatibility layer) | **NOT USER-FACING** | Get Sar Evidence |
| `GET` | `/api/cases/{case_id}/simulated-failure/{failure_code}` | Legacy Benchmark Adapter (Internal compatibility layer) | **NOT USER-FACING** | Get Simulated Failure Fixture |
| `GET` | `/api/cases/{case_id}/source-regions` | Legacy Benchmark Adapter (Internal compatibility layer) | **NOT USER-FACING** | Get Source Regions Geojson |
| `GET` | `/api/cases/{case_id}/timeline` | Legacy Benchmark Adapter (Internal compatibility layer) | **NOT USER-FACING** | Get Timeline |
| `GET` | `/api/cases/{case_id}/vessels` | Legacy Benchmark Adapter (Internal compatibility layer) | **NOT USER-FACING** | Get Vessels |
| `GET` | `/api/investigations` | Legacy Benchmark Adapter (Internal compatibility layer) | **NOT USER-FACING** | List Cases |
| `POST` | `/api/investigations` | Legacy Benchmark Adapter (Internal compatibility layer) | **NOT USER-FACING** | Create Investigation |
| `GET` | `/api/investigations/{case_id}` | Legacy Benchmark Adapter (Internal compatibility layer) | **NOT USER-FACING** | Get Unified Case |
| `GET` | `/api/investigations/{case_id}/ais` | Legacy Benchmark Adapter (Internal compatibility layer) | **NOT USER-FACING** | Get Ais Summary |
| `POST` | `/api/investigations/{case_id}/ais` | Legacy Benchmark Adapter (Internal compatibility layer) | **NOT USER-FACING** | Ingest Ais Data |
| `GET` | `/api/investigations/{case_id}/attribution` | Legacy Benchmark Adapter (Internal compatibility layer) | **NOT USER-FACING** | Get Attribution State |
| `POST` | `/api/investigations/{case_id}/automate` | Legacy Benchmark Adapter (Internal compatibility layer) | **NOT USER-FACING** | Trigger Automated Investigation |
| `GET` | `/api/investigations/{case_id}/candidates` | Legacy Benchmark Adapter (Internal compatibility layer) | **NOT USER-FACING** | Get Candidates Summary |
| `POST` | `/api/investigations/{case_id}/correlate` | Legacy Benchmark Adapter (Internal compatibility layer) | **NOT USER-FACING** | Trigger Vessel Correlation |
| `POST` | `/api/investigations/{case_id}/detect` | Legacy Benchmark Adapter (Internal compatibility layer) | **NOT USER-FACING** | Trigger Slick Detection |
| `GET` | `/api/investigations/{case_id}/evidence` | Evidence Gate & Data Manifest Table (#evidence-manifest-list) | **WIRED** | Get Evidence Fusion Table |
| `POST` | `/api/investigations/{case_id}/forecast` | Legacy Benchmark Adapter (Internal compatibility layer) | **NOT USER-FACING** | Trigger Forward Forecast |
| `GET` | `/api/investigations/{case_id}/forward-validation` | Legacy Benchmark Adapter (Internal compatibility layer) | **NOT USER-FACING** | Get Forward Validation |
| `GET` | `/api/investigations/{case_id}/hindcast` | Legacy Benchmark Adapter (Internal compatibility layer) | **NOT USER-FACING** | Get Hindcast Physics |
| `GET` | `/api/investigations/{case_id}/provenance` | Legacy Benchmark Adapter (Internal compatibility layer) | **NOT USER-FACING** | Get Provenance |
| `POST` | `/api/investigations/{case_id}/reconstruct` | Legacy Benchmark Adapter (Internal compatibility layer) | **NOT USER-FACING** | Trigger Hindcast Reconstruction |
| `GET` | `/api/investigations/{case_id}/review` | Legacy Benchmark Adapter (Internal compatibility layer) | **NOT USER-FACING** | Get Investigation Review |
| `GET` | `/api/investigations/{case_id}/sar` | Legacy Benchmark Adapter (Internal compatibility layer) | **NOT USER-FACING** | Get Sar Evidence |
| `GET` | `/api/investigations/{case_id}/simulated-failure/{failure_code}` | Legacy Benchmark Adapter (Internal compatibility layer) | **NOT USER-FACING** | Get Simulated Failure Fixture |
| `GET` | `/api/investigations/{case_id}/source-regions` | Legacy Benchmark Adapter (Internal compatibility layer) | **NOT USER-FACING** | Get Source Regions Geojson |
| `GET` | `/api/investigations/{case_id}/timeline` | Legacy Benchmark Adapter (Internal compatibility layer) | **NOT USER-FACING** | Get Timeline |
| `GET` | `/api/investigations/{case_id}/vessels` | Legacy Benchmark Adapter (Internal compatibility layer) | **NOT USER-FACING** | Get Vessels |
| `GET` | `/api/jobs/{job_id}` | Automated Diagnostic Engine | **NOT USER-FACING** | Get Job Status |
| `POST` | `/api/v1/ask` | Ask VARUNA Decision Support Drawer (#btn-open-intel, #intel-query-input, #intel-response-text) | **WIRED** | Ask VARUNA Intelligence an operational question (direct /ask endpoint) |
| `GET` | `/api/v1/cases` | Case Registry Modal / Table (#cases-table-body), Case Selector Dropdown (#case-select) | **WIRED** | List Cases |
| `POST` | `/api/v1/cases` | Create Case Modal / Form (#create-case-modal, #create-case-form) | **WIRED** | Create Case |
| `GET` | `/api/v1/cases/{case_id}` | Case Header (#case-title), Overview Panel (#panel-overview) | **WIRED** | Get Case |
| `POST` | `/api/v1/cases/{case_id}/analysis/hindcast-readiness` | Domain Analysis Workspace (#panel-analyze, #evidence-gate-card) | **WIRED** | Run Hindcast Readiness Analysis |
| `POST` | `/api/v1/cases/{case_id}/analysis/oil-detection` | Domain Analysis Workspace (#panel-analyze, #evidence-gate-card) | **WIRED** | Run Oil Detection Analysis |
| `POST` | `/api/v1/cases/{case_id}/analysis/spill-geometry` | Domain Analysis Workspace (#panel-analyze, #evidence-gate-card) | **WIRED** | Run Spill Geometry Analysis |
| `POST` | `/api/v1/cases/{case_id}/evidence` | Upload Evidence Form (#evidence-upload-form, #btn-upload-file) | **WIRED** | Upload Evidence |
| `GET` | `/api/v1/cases/{case_id}/evidence` | Evidence Gate & Data Manifest Table (#evidence-manifest-list) | **WIRED** | List Evidence |
| `GET` | `/api/v1/cases/{case_id}/evidence/{evidence_id}/file` | Evidence Gate & Data Manifest Table (#evidence-manifest-list) | **WIRED** | Get Evidence File |
| `POST` | `/api/v1/cases/{case_id}/intelligence/ask` | Ask VARUNA Decision Support Drawer (#btn-open-intel, #intel-query-input, #intel-response-text) | **WIRED** | Ask VARUNA Intelligence an operational question about an incident |
| `GET` | `/api/v1/cases/{case_id}/intelligence/response-priority` | Receptors & Operational Priority Table (#receptor-table, #threat-horizon-badge) | **WIRED** | Get explainable marine response priority analysis for an incident |
| `GET` | `/api/v1/cases/{case_id}/outputs/{filename}` | Static Binary & Raster Asset Streamer | **NOT USER-FACING** | Get Output File |
| `POST` | `/api/v1/cases/{case_id}/questions` | Analyst Questions Box (#analyst-questions-list) | **WIRED** | Add Analyst Question |
| `GET` | `/api/v1/cases/{case_id}/satellite` | Observe Satellite Card (#obs-card, #panel-observe) | **WIRED** | Get Case Satellite Observations |
| `POST` | `/api/v1/cases/{case_id}/satellite/attach` | Attach Observation Button (#btn-attach-sat, #sat-obs-details) | **WIRED** | Attach Satellite Observation |
| `POST` | `/api/v1/cases/{case_id}/satellite/search` | Search Satellite Dialog / Observe Panel (#btn-search-sat, #sat-results-list) | **WIRED** | Search Satellite Observations |
| `GET` | `/api/v1/cases/{case_id}/workflow` | Investigation Progress Stepper / Activity Log (#workflow-stepper, #activity-feed) | **WIRED** | Get Case Workflow Status |
| `POST` | `/api/v1/cases/{case_id}/workflow/acquire` | Acquire Satellite Product Action (#btn-acquire-prod) | **WIRED** | Acquire Satellite Product |
| `POST` | `/api/v1/cases/{case_id}/workflow/analyse-slick` | Run SmallUNet Oil Detection Action (#btn-detect-slick) | **WIRED** | Analyse Slick Segmentation |
| `POST` | `/api/v1/cases/{case_id}/workflow/correlate-ais` | Attribute Domain AIS Correlation Action (#btn-correlate-ais) | **WIRED** | Correlate Vessel Tracks |
| `POST` | `/api/v1/cases/{case_id}/workflow/forecast` | Reconstruct Domain Forecast Engine (#btn-run-forecast) | **WIRED** | Execute Case Forecast |
| `POST` | `/api/v1/cases/{case_id}/workflow/hindcast` | Reconstruct Domain Hindcast Engine (#btn-run-hindcast) | **WIRED** | Execute Case Hindcast |
| `GET` | `/api/v1/cases/{case_id}/workflow/incident-review` | Review & Export Panel (#panel-review, #btn-export-dossier, #review-briefing) | **WIRED** | Generate Incident Review |
| `POST` | `/api/v1/cases/{case_id}/workflow/preprocess` | SAR Radiometric Calibration Action (#btn-preprocess-sar) | **WIRED** | Preprocess Sar Observation |
| `POST` | `/api/v1/cases/{case_id}/workflow/response-priority` | Response Prioritization Card / Reconstruct Domain (#response-priority-badge, #receptor-table) | **WIRED** | Evaluate Response Priority |
| `POST` | `/api/v1/cases/{case_id}/workflow/select-candidate` | Candidate Triage Selection (#candidate-select, #cand-details) | **WIRED** | Select Candidate With Evidence Gate |
| `POST` | `/api/v1/intelligence/ask` | Ask VARUNA Decision Support Drawer (#btn-open-intel, #intel-query-input, #intel-response-text) | **WIRED** | Ask VARUNA Intelligence an operational question (direct /intelligence/ask endpoint) |
| `GET` | `/api/v1/intelligence/status` | Top Bar Intelligence Badge (#intel-status-pill), Decision Support Drawer Header | **WIRED** | Get VARUNA Intelligence agent status |
| `POST` | `/ask` | Ask VARUNA Decision Support Drawer (#btn-open-intel, #intel-query-input, #intel-response-text) | **WIRED** | Ask VARUNA Intelligence an operational question (direct /ask endpoint) |
| `GET` | `/cases` | Case Registry Modal / Table (#cases-table-body), Case Selector Dropdown (#case-select) | **WIRED** | List Cases |
| `POST` | `/cases` | Create Case Modal / Form (#create-case-modal, #create-case-form) | **WIRED** | Create Case |
| `GET` | `/cases/{case_id}` | Case Header (#case-title), Overview Panel (#panel-overview) | **WIRED** | Get Case |
| `POST` | `/cases/{case_id}/analysis/hindcast-readiness` | Domain Analysis Workspace (#panel-analyze, #evidence-gate-card) | **WIRED** | Run Hindcast Readiness Analysis |
| `POST` | `/cases/{case_id}/analysis/oil-detection` | Domain Analysis Workspace (#panel-analyze, #evidence-gate-card) | **WIRED** | Run Oil Detection Analysis |
| `POST` | `/cases/{case_id}/analysis/spill-geometry` | Domain Analysis Workspace (#panel-analyze, #evidence-gate-card) | **WIRED** | Run Spill Geometry Analysis |
| `POST` | `/cases/{case_id}/evidence` | Upload Evidence Form (#evidence-upload-form, #btn-upload-file) | **WIRED** | Upload Evidence |
| `GET` | `/cases/{case_id}/evidence` | Evidence Gate & Data Manifest Table (#evidence-manifest-list) | **WIRED** | List Evidence |
| `GET` | `/cases/{case_id}/evidence/{evidence_id}/file` | Evidence Gate & Data Manifest Table (#evidence-manifest-list) | **WIRED** | Get Evidence File |
| `POST` | `/cases/{case_id}/intelligence/ask` | Ask VARUNA Decision Support Drawer (#btn-open-intel, #intel-query-input, #intel-response-text) | **WIRED** | Ask VARUNA Intelligence an operational question about an incident |
| `GET` | `/cases/{case_id}/intelligence/response-priority` | Receptors & Operational Priority Table (#receptor-table, #threat-horizon-badge) | **WIRED** | Get explainable marine response priority analysis for an incident |
| `GET` | `/cases/{case_id}/outputs/{filename}` | Static Binary & Raster Asset Streamer | **NOT USER-FACING** | Get Output File |
| `POST` | `/cases/{case_id}/questions` | Analyst Questions Box (#analyst-questions-list) | **WIRED** | Add Analyst Question |
| `GET` | `/cases/{case_id}/satellite` | Observe Satellite Card (#obs-card, #panel-observe) | **WIRED** | Get Case Satellite Observations |
| `POST` | `/cases/{case_id}/satellite/attach` | Attach Observation Button (#btn-attach-sat, #sat-obs-details) | **WIRED** | Attach Satellite Observation |
| `POST` | `/cases/{case_id}/satellite/search` | Search Satellite Dialog / Observe Panel (#btn-search-sat, #sat-results-list) | **WIRED** | Search Satellite Observations |
| `GET` | `/cases/{case_id}/workflow` | Investigation Progress Stepper / Activity Log (#workflow-stepper, #activity-feed) | **WIRED** | Get Case Workflow Status |
| `POST` | `/cases/{case_id}/workflow/acquire` | Acquire Satellite Product Action (#btn-acquire-prod) | **WIRED** | Acquire Satellite Product |
| `POST` | `/cases/{case_id}/workflow/analyse-slick` | Run SmallUNet Oil Detection Action (#btn-detect-slick) | **WIRED** | Analyse Slick Segmentation |
| `POST` | `/cases/{case_id}/workflow/correlate-ais` | Attribute Domain AIS Correlation Action (#btn-correlate-ais) | **WIRED** | Correlate Vessel Tracks |
| `POST` | `/cases/{case_id}/workflow/forecast` | Reconstruct Domain Forecast Engine (#btn-run-forecast) | **WIRED** | Execute Case Forecast |
| `POST` | `/cases/{case_id}/workflow/hindcast` | Reconstruct Domain Hindcast Engine (#btn-run-hindcast) | **WIRED** | Execute Case Hindcast |
| `GET` | `/cases/{case_id}/workflow/incident-review` | Review & Export Panel (#panel-review, #btn-export-dossier, #review-briefing) | **WIRED** | Generate Incident Review |
| `POST` | `/cases/{case_id}/workflow/preprocess` | SAR Radiometric Calibration Action (#btn-preprocess-sar) | **WIRED** | Preprocess Sar Observation |
| `POST` | `/cases/{case_id}/workflow/response-priority` | Response Prioritization Card / Reconstruct Domain (#response-priority-badge, #receptor-table) | **WIRED** | Evaluate Response Priority |
| `POST` | `/cases/{case_id}/workflow/select-candidate` | Candidate Triage Selection (#candidate-select, #cand-details) | **WIRED** | Select Candidate With Evidence Gate |
| `GET` | `/health` | Backend Infrastructure & Diagnostic Endpoints | **NOT USER-FACING** | Health |
| `POST` | `/intelligence/ask` | Ask VARUNA Decision Support Drawer (#btn-open-intel, #intel-query-input, #intel-response-text) | **WIRED** | Ask VARUNA Intelligence an operational question (direct /intelligence/ask endpoint) |
| `GET` | `/intelligence/status` | Top Bar Intelligence Badge (#intel-status-pill), Decision Support Drawer Header | **WIRED** | Get VARUNA Intelligence agent status |
| `GET` | `/ready` | Backend Infrastructure & Diagnostic Endpoints | **NOT USER-FACING** | Ready |
| `GET` | `/version` | Backend Infrastructure & Diagnostic Endpoints | **NOT USER-FACING** | Get Version |
