# SAMUDRANETRA — SCIENTIFIC TERMINOLOGY & CLAIM SAFETY DICTIONARY

## MANDATORY APPROVED TERMS

| Approved Term | Scientific Definition | Permitted Usage |
| :--- | :--- | :--- |
| **ML OIL-LIKE EVIDENCE** | Probability output of Task008B Candidate Classifier model `v1.0.0` (`v1_fixed_vv_db_clip_30_0`). | Used for candidate scoring (`0.5818` for C4053). |
| **BACKTRACKED SOURCE REGION** | Spatial envelope reconstructed by backward particle advection under specified metocean forcing assumptions. | Used for OpenDrift hindcast source regions. |
| **INVESTIGATIVE PRIORITY** | Multi-attribute explainable heuristic rank computed from spatiotemporal proximity, speed, and gap features. | Used for vessel lead ranking. |
| **SYNTHETIC AIS DEMONSTRATION** | Simulated regional vessel trajectory dataset created for platform evaluation when historical AIS is unavailable. | Mandatory label when synthetic AIS is active. |
| **VALIDATED CACHED RESULT** | Benchmark data generated and cryptographically frozen during pre-truth R001 evaluation. | Mandatory badge on cached R001 outputs. |
| **LIVE COMPUTE** | Pipeline computation executed on-demand during the current user session. | Mandatory badge on live forecast & AIS jobs. |
| **POST-FREEZE HISTORICAL VALIDATION** | Blind reference distance evaluation unlocked ONLY after cryptographic pre-truth freezing. | Used for post-freeze validation benchmarks. |

---

## STRICTLY FORBIDDEN UNACCURATE TERMS

> [!CAUTION]
> The following terms are **STRICTLY PROHIBITED** across all UI text, code comments, notifications, tooltips, and documentation:
>
> - ❌ `AI CONFIDENCE`
> - ❌ `CULPRIT`
> - ❌ `GUILTY`
> - ❌ `CONFIRMED VESSEL`
> - ❌ `TRUE SOURCE`
> - ❌ `EXACT SOURCE`
> - ❌ `100% ACCURACY`
>
> Using any of these terms compromises scientific integrity and violates claim safety rules.

---

## PERMITTED SYSTEM STATES

- `SUPPORTED`: High-confidence physical forcing or validated candidate coverage.
- `UNCERTAIN`: High scenario sensitivity or ocean current shear divergence.
- `AMBIGUOUS`: Multiple candidate vessels share equal investigative priority.
- `INSUFFICIENT DATA`: Input rasters or forcing files missing/corrupt.
- `NO CREDIBLE CANDIDATE`: All vessel candidates fall below spatial/temporal proximity thresholds.
- `NON-VESSEL SOURCE POSSIBLE`: Natural seepage or biogenic lookalike feature suspected.
