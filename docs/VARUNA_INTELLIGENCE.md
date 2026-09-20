# VARUNA Intelligence — Operational Interpretation & Decision Support Layer

## 1. Purpose

**VARUNA Intelligence** is an operational interpretation layer designed for maritime pollution response commanders, coast guard watchstanders, and environmental protection authorities. It enables non-scientific personnel to ask natural-language questions about complex satellite radar observations, metocean drift projections, and vessel traffic correlations without requiring deep expertise in radar physics or Lagrangian particle modeling.

> [!IMPORTANT]
> **This is NOT a generic chatbot.** It is a constrained, evidence-grounded interpretation system that queries verified VARUNA case data exclusively through approved, read-only internal tools.

---

## 2. Architecture

```
                 Operator (Watchstander / Commander)
                                 │
                                 ▼
                     Ask VARUNA Natural Query
                                 │
                                 ▼
                    VARUNA Intelligence Agent
              Strands Agents SDK + Amazon Bedrock
          (Or Deterministic Grounded Fallback if Offline)
                                 │
                                 ▼
                    Approved Read-Only Tools
        ┌────────────────────────┼────────────────────────┐
        ▼                        ▼                        ▼
get_case_summary       get_observation_evidence  get_response_intelligence
get_trajectory_intel   get_vessel_intelligence   get_case_provenance
        └────────────────────────┬────────────────────────┘
                                 │
                                 ▼
                     VARUNA Case Intelligence
        (FastAPI Backend / Internal Storage / Scientific Pipeline)
                                 │
                                 ▼
                 Evidence / Modes / Limitations
          (Real vs Synthetic Provenance Contracts)
```

---

## 3. Security Boundary & Least Privilege Design

The intelligence layer adheres to strict zero-trust operational security boundaries:

1. **Read-Only Access**:
   - The agent has **ZERO mutation capabilities**.
   - It cannot create, modify, or delete cases.
   - It cannot trigger downloads, satellite acquisitions, or modify model weights.
2. **No Shell / No File System / No Web**:
   - Only the minimal `strands-agents` package is installed.
   - Community tools such as `bash`, `shell`, `file_editor`, and `web_fetch` are **strictly omitted**.
   - No arbitrary file-read tools or unrestricted network access are provided.
3. **Prompt Injection Resistance**:
   - The system prompt is static, immutable, and strictly isolates instructions from user turns.
   - User input is passed solely as the user message and is **never** concatenated into the system prompt.
   - Attempts to alter tool permissions or execute commands fail because no writing or shell tools exist in the runtime registry.
4. **Secret Sanitization**:
   - All tool outputs pass through recursive redaction (`sanitize_tool_output`).
   - Environment variables, AWS secret keys, CDSE credentials, and local file paths are scrubbed prior to reaching the model or the operator.

---

## 4. Approved Read-Only Toolset

| Tool Name | Scope & Output |
| :--- | :--- |
| `get_case_summary` | Case ID, incident type, region, observation timestamp, geographic coordinates, and current stage. |
| `get_observation_evidence` | Sensor info, VV/VH polarimetric backscatter depression metrics, SmallUNet evidence score, and Evidence Gate qualification. |
| `get_response_intelligence` | Dynamic response window, ranked receptors, arrival estimates, deterministic decision reasons, and execution/evidence modes. |
| `get_trajectory_intelligence` | Lagrangian hindcast probable release window/envelope, forward forecast drift corridor, horizons, and dispersion uncertainty. |
| `get_vessel_intelligence` | AIS candidate tracks, CPA distance, time deltas, and spatiotemporal compatibility factors. |
| `get_case_provenance` | Complete stage execution modes (REAL vs SYNTHETIC_DEMO), model checkpoints, product IDs, and blocked dependencies. |
| `get_operational_brief` | High-level deterministic structured aggregation across all incident dimensions. |

---

## 5. Amazon Bedrock Integration & Configuration

The service interfaces with Amazon Bedrock via the Strands Agents SDK `BedrockModel`:

- **Credentials**: Standard AWS credential chain (IAM roles, AWS profiles, or environment variables `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`). **Credentials are never hard-coded.**
- **Environment Variables**:
  - `VARUNA_AGENT_ENABLED`: Boolean toggle (default: `true`).
  - `AWS_REGION`: AWS deployment region (default: `us-east-1`).
  - `VARUNA_BEDROCK_MODEL_ID`: Configurable Bedrock Foundation Model ID (default: `anthropic.claude-3-haiku-20240307-v1:0`).

---

## 6. Deterministic Grounded Fallback (Hackathon Reliability)

If Amazon Bedrock credentials are not configured, access is throttled, or an outage occurs, VARUNA Intelligence **does not crash or become disabled**. Instead, it seamlessly routes the query to a deterministic, rule-grounded responder:

- Evaluates case data directly from structured database tables.
- Accurately answers the five core operational questions and reliability inquiries.
- Explicitly flags output with:
  ```json
  {
    "model_provider": "UNAVAILABLE",
    "response_mode": "DETERMINISTIC_GROUNDED_FALLBACK"
  }
  ```
- Guaranteed to never hallucinate or invent data.

---

## 7. Truthfulness & Scientific Integrity Guarantees

1. **"Oil-like evidence" $\neq$ "Confirmed oil spill"**: Radar backscatter depressions represent capillary wave dampening. The agent never claims a spill is chemically confirmed without physical ground-truth evidence.
2. **"Investigative candidate" $\neq$ "Guilty / Culprit"**: Vessel track correlation establishes spatiotemporal compatibility only. The agent is programmatically forbidden from using terms like "culprit" or "guilty vessel".
3. **Response Score is NOT a Probability**: The response priority score is an operational ranking and decision-support metric; probability terminology is strictly disclaimed.
4. **Separation of Execution Mode and Evidence Mode**: Algorithmic execution (`REAL`) is distinguished from synthetic demonstration input (`SYNTHETIC_DEMO`). If any input is synthetic, `effective_evidence_mode` is truthfully declared `SYNTHETIC_DEMO`.

---

## 8. Future Extensibility (Platform Adaptability)

The `VarunaToolRegistry` provides a clean extension interface for commercial production deployments:

- **Live AIS Streaming**: Integration of Spire or exactEarth satellite AIS feeds.
- **Port Asset Databases**: Cross-referencing local port booms, skimmers, and tugs.
- **Insurer Exposure Layers**: Vessel P&I club coverage and coastal infrastructure valuation.
- **Commercial Optical Satellite Tasking**: High-resolution Planet / WorldView verification.
- **Automated Webhooks**: Immediate alert dispatches to national response centers.
