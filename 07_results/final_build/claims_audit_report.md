# VARUNA — Claims Audit Report

Audited terms: `cryptographic`, `immutable`, `zero hallucination`, `zero leakage`, `culprit`, `guilty`, `proven`, and `real-time`.

## Term: `cryptographic` (22 hits)

- **backend\app\routers\investigation.py:362**: `(95, "STAGE 6: REVIEW & PROVENANCE", "Generating 11-stage incident briefing and cryptographic audit..."),`
- **backend\app\routers\investigation.py:411**: `"PROVENANCE": {"status": "PASS", "details": "Clean-room cryptographic provenance verified"}`
- **backend\app\routers\investigation.py:459**: `"""Returns full cryptographic provenance record."""`
- **backend\app\routers\satellite.py:119**: `Stores cryptographic and provider provenance.`
- **backend\app\services\ais_ranking.py:5**: `abstention classification, human-readable reason code generation, and cryptographic`
- **backend\app\services\investigation_engine.py:69**: `"isolation_note": "Unlocked ONLY after cryptographic pre-truth freezing. NEVER used to tune backward transport or AIS search."`
- **backend\app\services\investigation_engine.py:534**: `12. `GET /api/cases/{case_id}/provenance`: Full cryptographic provenance record.`
- **backend\app\services\sentinel_download.py:137**: `"""Compute cryptographic SHA-256 hash of a local file."""`
- **backend\tests\test_ais_ranking.py:6**: `synthetic-mode labelling, reason code generation, and ranking freeze cryptographic SHA256.`
- **backend\tests\test_investigation_engine.py:61**: `assert "Unlocked ONLY after cryptographic pre-truth freezing" in hv["isolation_note"]`
- **backend\tests\test_phase1_multicase.py:183**: `"""6. Verify genuine generic evidence upload into Case #2 with cryptographic SHA-256 provenance."""`
- **backend\tests\test_sentinel_catalog.py:11**: `7. Observation attachment with cryptographic and provider provenance`
- **docs\DEMO_SCRIPT.md:29**: `> "Finally, in Stage 07 — **REVIEW**, SamudraNetra compiles a complete cryptographic provenance record and supported claims matrix. This provides maritime commanders with explainable, defense-grade intelligence for rapid operational response."`
- **docs\VARUNA_DEMO_FLOW.md:38**: `* **Visual**: Structured 11-stage evidence report, historical validation limitations, and cryptographic SHA256 manifest.`
- **docs\VARUNA_DEMO_FLOW.md:39**: `* **Script**: *"Finally, REVIEW presents a complete 11-stage briefing matrix with explicit cache vs. live compute execution status and cryptographic SHA256 provenance for court and agency audits."*`
- **docs\VARUNA_GOV_DEMO_RELEASE.md:24**: `\| **Cryptographic Provenance** \| Immutable SHA256 audit manifest & execution status tags \| Click `PROVENANCE` \| Audited dataset hashes & pipeline execution lineage \|`
- **ops_console\app.js:990**: `{ num: "10", name: "REVIEW READY", key: "REVIEW READY", engine: "Incident Dossier & Cryptographic Provenance Chain" }`
- **ops_console\index.html:592**: `<p class="text-xs text-on-surface-variant mt-1">Cryptographic Pipeline Activity Log & Operator Audit History</p>`
- **README.md:23**: `└── UNCERTAINTY & CRYPTOGRAPHIC PROVENANCE (REAL)`
- **README.md:36**: `- **Cryptographic Provenance**: Exposes execution modes (`REAL`, `SYNTHETIC_DEMO`, `BLOCKED`) and SHA-256 integrity hashes for all outputs.`
- **07_results\final_build\DEMO_SCRIPT_90_SECONDS.md:16**: `[01:05 - 01:20] UNCERTAINTY PROFILE & CRYPTOGRAPHIC PROVENANCE`
- **07_results\final_build\DEMO_SCRIPT_90_SECONDS.md:54**: `### Phase 5: [01:05 – 01:20] Uncertainty Profile & Cryptographic Provenance`


## Term: `immutable` (5 hits)

- **backend\app\services\segmentation_engine.py:73**: `"""Immutable record of quicklook SAR inference and vectorisation provenance."""`
- **backend\app\services\sentinel_download.py:89**: `"""Immutable record of satellite product acquisition provenance."""`
- **backend\app\services\varuna_intelligence.py:1052**: `# Invariant: Prompt injection protection. The system prompt is static and immutable.`
- **docs\VARUNA_GOV_DEMO_RELEASE.md:24**: `\| **Cryptographic Provenance** \| Immutable SHA256 audit manifest & execution status tags \| Click `PROVENANCE` \| Audited dataset hashes & pipeline execution lineage \|`
- **docs\VARUNA_INTELLIGENCE.md:57**: `- The system prompt is static, immutable, and strictly isolates instructions from user turns.`


## Term: `zero hallucination` (0 hits)

No occurrences found.

## Term: `zero leakage` (2 hits)

- **backend\app\routers\workflow.py:17**: `Guarantees full per-case state persistence and zero leakage with R001 benchmark.`
- **backend\tests\test_sentinel_catalog.py:305**: `case_id = _create_test_case(name="Arabian Sea Zero Leakage Test")`


## Term: `culprit` (22 hits)

- **backend\app\services\ais_engine.py:607**: `DOES NOT calculate guilt probability or culprit attribution.`
- **backend\app\services\varuna_intelligence.py:132**: `forbidden_terms = ["culprit", "guilty vessel", "guilty", "responsible vessel"]`
- **backend\app\services\varuna_intelligence.py:435**: `"Candidate designation is INVESTIGATIVE_CANDIDATE. Forbidden terms: culprit, guilty, responsible vessel.",`
- **backend\app\services\varuna_intelligence.py:478**: `"Candidate designation is INVESTIGATIVE_CANDIDATE. Forbidden terms: culprit, guilty, responsible vessel.",`
- **backend\app\services\varuna_intelligence.py:625**: `4. "Investigative candidate" must NEVER become "culprit", "guilty vessel", or "responsible vessel". Correlation is spatiotemporal compatibility, not legal proof of discharge.`
- **backend\app\services\varuna_intelligence.py:843**: `f"Under VARUNA operational protocols, candidates are designated as INVESTIGATIVE_CANDIDATE. Terms such as 'culprit', "`
- **backend\tests\test_e2e_gauntlet.py:139**: `forbidden_terms = ["culprit", "guilty", "proven source", "ai confidence", "probability of guilt", "100% accurate"]`
- **backend\tests\test_final_case_workflow.py:129**: `assert "culprit" not in cand["candidate_designation"].lower()`
- **backend\tests\test_frontend_integration.py:52**: `"""Verifies that unscientific terms ('confidence', 'guilt', 'culprit', 'true source') do not appear in API responses."""`
- **backend\tests\test_frontend_integration.py:59**: `forbidden_terms = ["confidence", "guilt", "culprit", "true source"]`
- **backend\tests\test_truthful_execution_contracts.py:194**: `assert "culprit" not in candidate["candidate_designation"].lower()`
- **backend\tests\test_ui_integrity.py:66**: `forbidden_terms = ["culprit", "guilty", "proven source", "ai confidence", "probability of guilt", "100% accurate"]`
- **backend\tests\test_varuna_intelligence.py:152**: `for forbidden in ["culprit", "guilty", "responsible vessel"]:`
- **docs\VARUNA_INTELLIGENCE.md:112**: `2. **"Investigative candidate" $\neq$ "Guilty / Culprit"**: Vessel track correlation establishes spatiotemporal compatibility only. The agent is programmatically forbidden from using terms like "culprit" or "guilty vessel".`
- **README.md:35**: `- **Strict Maritime Legal Nomenclature**: Prioritizes vessels solely as `INVESTIGATIVE_CANDIDATE` based on spatiotemporal miss distance and trajectory kinematics. Never outputs prejudicial terms like "culprit" or "guilty".`
- **07_results\final_build\DEMO_SCRIPT_90_SECONDS.md:50**: `> *"Next, we search for candidate sources. VARUNA correlates AIS vessel trajectory feeds across the hindcast window. We never declare an unverified 'culprit'—instead, our kinematics engine ranks vessels strictly as `INVESTIGATIVE_CANDIDATE`. In this demo case, tanker PACIFIC EXPLORER crossed the release envelope during the estimated window and is assigned top investigative priority, while other regional traffic is systematically filtered."*`
- **07_results\final_build\JUDGE_QA.md:28**: `### 3. Why is a nearby vessel not automatically the culprit?`
- **07_results\final_build\JUDGE_QA.md:34**: `- **Strict Legal Nomenclature:** VARUNA adheres to international maritime legal standards. Outputs are strictly labeled `INVESTIGATIVE_CANDIDATE` with transparent candidate scores (0.0 to 1.0) and spatial miss distances. VARUNA never brands an entity as "guilty" or a "culprit," maintaining evidential neutrality required for maritime judicial proceedings.`
- **07_results\final_build\REUSE_AUDIT.md:35**: `\| 15 \| **AIS Ingestion & Ranking** \| `backend/app/services/ais_service.py`<br>`backend/app/routers/investigation.py` \| Spatiotemporal AIS track search, distance-to-release scoring, vessel trajectory intersection, flag/type/MMSI lookup. \| Strict terminology enforcement: produces `INVESTIGATIVE_CANDIDATE` (never "culprit" or "guilty"). Explicitly flags `REAL AIS`, `SYNTHETIC_DEMO AIS`, or `MISSING AIS`. Supports `NO_CREDIBLE_CANDIDATE`. \| Spire / AISHub / open AIS schema. \|`
- **07_results\final_build\VARUNA_FINAL_INCIDENT_REPORT.md:58**: `Candidate vessels are strictly categorized using neutral maritime investigative terminology: **`INVESTIGATIVE_CANDIDATE`**. No entity is declared "guilty" or branded a "culprit."`
- **07_results\final_qa\R001_FINAL_CLAIM_AUDIT.json:5**: `"CULPRIT": 0,`
- **07_results\final_qa\R001_FINAL_QA_SUMMARY.md:20**: `4. **Claim Guard Wording Audit**: `0` instances of forbidden deterministic/guilt language (`AI CONFIDENCE`, `CULPRIT`, `GUILTY`, `TRUE SOURCE`, `CONFIRMED VESSEL`).`


## Term: `guilty` (22 hits)

- **backend\app\services\historical_validation.py:342**: `- ❌ *"AI identified the guilty vessel."* (Vessel attribution is not performed by candidate triage or OpenDrift physical transport alone).`
- **backend\app\services\investigation_engine.py:502**: `- ❌ "AI identified the guilty vessel."`
- **backend\app\services\varuna_intelligence.py:132**: `forbidden_terms = ["culprit", "guilty vessel", "guilty", "responsible vessel"]`
- **backend\app\services\varuna_intelligence.py:435**: `"Candidate designation is INVESTIGATIVE_CANDIDATE. Forbidden terms: culprit, guilty, responsible vessel.",`
- **backend\app\services\varuna_intelligence.py:478**: `"Candidate designation is INVESTIGATIVE_CANDIDATE. Forbidden terms: culprit, guilty, responsible vessel.",`
- **backend\app\services\varuna_intelligence.py:625**: `4. "Investigative candidate" must NEVER become "culprit", "guilty vessel", or "responsible vessel". Correlation is spatiotemporal compatibility, not legal proof of discharge.`
- **backend\app\services\varuna_intelligence.py:844**: `f"'guilty', or 'responsible vessel' are forbidden. Independent physical or observational evidence may be required before legal or regulatory attribution can be made."`
- **backend\tests\test_e2e_gauntlet.py:139**: `forbidden_terms = ["culprit", "guilty", "proven source", "ai confidence", "probability of guilt", "100% accurate"]`
- **backend\tests\test_final_case_workflow.py:130**: `assert "guilty" not in cand["candidate_designation"].lower()`
- **backend\tests\test_investigation_engine.py:69**: `forbidden_terms = ["CULPRIT_CONFIRMED", "GUILTY", "CAUSE_PROVEN", "99% RESPONSIBLE"]`
- **backend\tests\test_truthful_execution_contracts.py:195**: `assert "guilty" not in candidate["candidate_designation"].lower()`
- **backend\tests\test_ui_integrity.py:66**: `forbidden_terms = ["culprit", "guilty", "proven source", "ai confidence", "probability of guilt", "100% accurate"]`
- **backend\tests\test_varuna_intelligence.py:152**: `for forbidden in ["culprit", "guilty", "responsible vessel"]:`
- **docs\JUDGE_QA.md:22**: `### Q6: Can SamudraNetra declare a vessel legally guilty?`
- **docs\PRESENTATION_CLAIMS.md:25**: `- ❌ "We identified the guilty vessel."`
- **docs\VARUNA_INTELLIGENCE.md:112**: `2. **"Investigative candidate" $\neq$ "Guilty / Culprit"**: Vessel track correlation establishes spatiotemporal compatibility only. The agent is programmatically forbidden from using terms like "culprit" or "guilty vessel".`
- **README.md:35**: `- **Strict Maritime Legal Nomenclature**: Prioritizes vessels solely as `INVESTIGATIVE_CANDIDATE` based on spatiotemporal miss distance and trajectory kinematics. Never outputs prejudicial terms like "culprit" or "guilty".`
- **07_results\final_build\JUDGE_QA.md:34**: `- **Strict Legal Nomenclature:** VARUNA adheres to international maritime legal standards. Outputs are strictly labeled `INVESTIGATIVE_CANDIDATE` with transparent candidate scores (0.0 to 1.0) and spatial miss distances. VARUNA never brands an entity as "guilty" or a "culprit," maintaining evidential neutrality required for maritime judicial proceedings.`
- **07_results\final_build\REUSE_AUDIT.md:35**: `\| 15 \| **AIS Ingestion & Ranking** \| `backend/app/services/ais_service.py`<br>`backend/app/routers/investigation.py` \| Spatiotemporal AIS track search, distance-to-release scoring, vessel trajectory intersection, flag/type/MMSI lookup. \| Strict terminology enforcement: produces `INVESTIGATIVE_CANDIDATE` (never "culprit" or "guilty"). Explicitly flags `REAL AIS`, `SYNTHETIC_DEMO AIS`, or `MISSING AIS`. Supports `NO_CREDIBLE_CANDIDATE`. \| Spire / AISHub / open AIS schema. \|`
- **07_results\final_build\VARUNA_FINAL_INCIDENT_REPORT.md:58**: `Candidate vessels are strictly categorized using neutral maritime investigative terminology: **`INVESTIGATIVE_CANDIDATE`**. No entity is declared "guilty" or branded a "culprit."`
- **07_results\final_qa\R001_FINAL_CLAIM_AUDIT.json:6**: `"GUILTY": 0,`
- **07_results\final_qa\R001_FINAL_QA_SUMMARY.md:20**: `4. **Claim Guard Wording Audit**: `0` instances of forbidden deterministic/guilt language (`AI CONFIDENCE`, `CULPRIT`, `GUILTY`, `TRUE SOURCE`, `CONFIRMED VESSEL`).`


## Term: `proven` (3 hits)

- **backend\app\services\varuna_intelligence.py:402**: `Never asserts guilt, culpability, or proven discharge responsibility.`
- **backend\tests\test_e2e_gauntlet.py:139**: `forbidden_terms = ["culprit", "guilty", "proven source", "ai confidence", "probability of guilt", "100% accurate"]`
- **backend\tests\test_ui_integrity.py:66**: `forbidden_terms = ["culprit", "guilty", "proven source", "ai confidence", "probability of guilt", "100% accurate"]`


## Term: `real-time` (3 hits)

- **backend\app\routers\investigation.py:470**: `"""Polls real-time job execution status, step label, progress percentage, logs, and result."""`
- **docs\PRESENTATION_CLAIMS.md:28**: `- ❌ "Continuous real-time live SAR satellite video feed."`
- **docs\SATELLITE_CATALOGUE_ARCHITECTURE.md:48**: `> **Scientific Integrity Rule**: At this stage, VARUNA knows only that an acquisition exists and intersects the case AOI. Catalogue discovery must never be labeled "oil detection", "live SAR analysis", or "real-time satellite feed".`

