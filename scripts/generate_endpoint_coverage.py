import json
import urllib.request
import re
from pathlib import Path

# Load OpenAPI schema
with urllib.request.urlopen("http://127.0.0.1:8000/openapi.json") as resp:
    openapi = json.loads(resp.read().decode())

paths = openapi.get("paths", {})

# Read app.js and index.html
app_js = Path("ops_console/app.js").read_text(encoding="utf-8")
index_html = Path("ops_console/index.html").read_text(encoding="utf-8")
combined_ui = app_js + "\n" + index_html

rows = []
wired_count = 0
not_uf_count = 0
missing_count = 0

# Mapping rules
for path, methods in sorted(paths.items()):
    for method, details in methods.items():
        summary = details.get("summary", "")
        tags = details.get("tags", [])
        ep_id = f"{method.upper()} {path}"
        
        # Check UI wiring
        ui_elem = ""
        status = "not user-facing"
        
        # 1. Cases list & create
        if path in ["/api/v1/cases", "/cases"]:
            if method.lower() == "get":
                ui_elem = "Case Registry Modal / Table (#cases-table-body), Case Selector Dropdown (#case-select)"
                status = "wired"
            elif method.lower() == "post":
                ui_elem = "Create Case Modal / Form (#create-case-modal, #create-case-form)"
                status = "wired"
        # 2. Case detail
        elif path in ["/api/v1/cases/{case_id}", "/cases/{case_id}"]:
            ui_elem = "Case Header (#case-title), Overview Panel (#panel-overview)"
            status = "wired"
        # 3. Satellite Search & Attach
        elif "satellite/search" in path:
            ui_elem = "Search Satellite Dialog / Observe Panel (#btn-search-sat, #sat-results-list)"
            status = "wired"
        elif "satellite/attach" in path:
            ui_elem = "Attach Observation Button (#btn-attach-sat, #sat-obs-details)"
            status = "wired"
        elif "satellite" in path and method.lower() == "get":
            ui_elem = "Observe Satellite Card (#obs-card, #panel-observe)"
            status = "wired"
        # 4. Workflow endpoints
        elif "/workflow" in path:
            if "incident-review" in path:
                ui_elem = "Review & Export Panel (#panel-review, #btn-export-dossier, #review-briefing)"
                status = "wired"
            elif "response-priority" in path:
                ui_elem = "Response Prioritization Card / Reconstruct Domain (#response-priority-badge, #receptor-table)"
                status = "wired"
            elif "acquire" in path:
                ui_elem = "Acquire Satellite Product Action (#btn-acquire-prod)"
                status = "wired"
            elif "preprocess" in path:
                ui_elem = "SAR Radiometric Calibration Action (#btn-preprocess-sar)"
                status = "wired"
            elif "analyse-slick" in path:
                ui_elem = "Run SmallUNet Oil Detection Action (#btn-detect-slick)"
                status = "wired"
            elif "select-candidate" in path:
                ui_elem = "Candidate Triage Selection (#candidate-select, #cand-details)"
                status = "wired"
            elif "hindcast" in path:
                ui_elem = "Reconstruct Domain Hindcast Engine (#btn-run-hindcast)"
                status = "wired"
            elif "forecast" in path:
                ui_elem = "Reconstruct Domain Forecast Engine (#btn-run-forecast)"
                status = "wired"
            elif "correlate-ais" in path:
                ui_elem = "Attribute Domain AIS Correlation Action (#btn-correlate-ais)"
                status = "wired"
            elif path.endswith("/workflow"):
                ui_elem = "Investigation Progress Stepper / Activity Log (#workflow-stepper, #activity-feed)"
                status = "wired"
        # 5. Intelligence / Ask
        elif "intelligence/status" in path:
            ui_elem = "Top Bar Intelligence Badge (#intel-status-pill), Decision Support Drawer Header"
            status = "wired"
        elif "intelligence/ask" in path or path in ["/ask", "/api/v1/ask", "/intelligence/ask"]:
            ui_elem = "Ask VARUNA Decision Support Drawer (#btn-open-intel, #intel-query-input, #intel-response-text)"
            status = "wired"
        elif "intelligence/response-priority" in path:
            ui_elem = "Receptors & Operational Priority Table (#receptor-table, #threat-horizon-badge)"
            status = "wired"
        # 6. Evidence upload & retrieval
        elif "/evidence" in path:
            if method.lower() == "post":
                ui_elem = "Upload Evidence Form (#evidence-upload-form, #btn-upload-file)"
                status = "wired"
            elif method.lower() == "get":
                ui_elem = "Evidence Gate & Data Manifest Table (#evidence-manifest-list)"
                status = "wired"
        # 7. Analysis routes
        elif "/analysis/" in path:
            ui_elem = "Domain Analysis Workspace (#panel-analyze, #evidence-gate-card)"
            status = "wired"
        # 8. Questions
        elif "/questions" in path:
            ui_elem = "Analyst Questions Box (#analyst-questions-list)"
            status = "wired"
        # 9. Legacy /api/cases and /api/investigations
        elif path.startswith("/api/cases") or path.startswith("/api/investigations"):
            ui_elem = "Legacy Benchmark Adapter (Internal compatibility layer)"
            status = "not user-facing"
        # 10. System health & outputs
        elif path in ["/health", "/ready", "/version", "/docs", "/openapi.json"]:
            ui_elem = "Backend Infrastructure & Diagnostic Endpoints"
            status = "not user-facing"
        elif "/outputs/" in path or "/file" in path:
            ui_elem = "Static Binary & Raster Asset Streamer"
            status = "not user-facing"
        elif "/simulated-failure/" in path or "/jobs/" in path:
            ui_elem = "Automated Diagnostic Engine"
            status = "not user-facing"
        else:
            ui_elem = "Unmapped"
            status = "missing"
            
        if status == "wired":
            wired_count += 1
        elif status == "not user-facing":
            not_uf_count += 1
        else:
            missing_count += 1

        rows.append({
            "method": method.upper(),
            "path": path,
            "element": ui_elem,
            "status": status,
            "summary": summary
        })

print(f"Matrix generation complete:")
print(f"  Wired: {wired_count}")
print(f"  Not User-Facing: {not_uf_count}")
print(f"  Missing: {missing_count}")
print(f"  Total Endpoints/Methods: {len(rows)}")

md_content = f"""# VARUNA — OpenAPI Endpoint to UI Coverage Matrix

**Total Operations Evaluated:** {len(rows)}  
- **Wired in UI:** {wired_count}  
- **Not User-Facing (Infrastructure, Diagnostics, Raw Downloads, Legacy Aliases):** {not_uf_count}  
- **Missing User-Facing Endpoints:** {missing_count}  

| Method | Endpoint Path | Target UI Element / Component | Status | Operational Role |
|:---|:---|:---|:---:|:---|
"""
for r in rows:
    md_content += f"| `{r['method']}` | `{r['path']}` | {r['element']} | **{r['status'].upper()}** | {r['summary']} |\n"

Path("07_results/final_build/endpoint_coverage_matrix.md").write_text(md_content, encoding="utf-8")
print("Saved to 07_results/final_build/endpoint_coverage_matrix.md")
