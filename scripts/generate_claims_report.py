import os
import re

terms = [
    "cryptographic",
    "immutable",
    "zero hallucination",
    "zero leakage",
    "culprit",
    "guilty",
    "proven",
    "real-time"
]

target_dirs = ["backend", "docs", "ops_console", "README.md", "07_results"]

results = {t: [] for t in terms}

for root_item in target_dirs:
    if os.path.isfile(root_item):
        files_to_check = [root_item]
    else:
        files_to_check = []
        for r, _, f_list in os.walk(root_item):
            for f in f_list:
                if f.endswith((".py", ".md", ".html", ".js", ".css", ".json", ".txt")):
                    files_to_check.append(os.path.join(r, f))

    for fpath in files_to_check:
        try:
            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                for line_no, line in enumerate(f, 1):
                    for t in terms:
                        if re.search(r"\b" + re.escape(t) + r"\b", line, re.IGNORECASE):
                            results[t].append((fpath, line_no, line.strip()))
        except Exception:
            pass

out = []
out.append("# VARUNA — Claims Audit Report\n")
out.append("Audited terms: `cryptographic`, `immutable`, `zero hallucination`, `zero leakage`, `culprit`, `guilty`, `proven`, and `real-time`.\n")

for t in terms:
    hits = results[t]
    out.append(f"## Term: `{t}` ({len(hits)} hits)\n")
    if not hits:
        out.append("No occurrences found.\n")
        continue
    for fpath, line_no, line in hits:
        # Sanitize markdown formatting
        clean_line = line.replace("|", "\\|")
        out.append(f"- **{fpath}:{line_no}**: `{clean_line}`")
    out.append("\n")

with open("07_results/final_build/claims_audit_report.md", "w", encoding="utf-8") as f:
    f.write("\n".join(out))

print("Claims audit saved to 07_results/final_build/claims_audit_report.md")
