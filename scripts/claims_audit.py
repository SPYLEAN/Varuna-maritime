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

print("=== CLAIMS AUDIT HIT COUNTS ===")
for t in terms:
    print(f"Term '{t}': {len(results[t])} hits")
    for hit in results[t][:5]:
        print(f"   {hit[0]}:{hit[1]} -> {hit[2][:100]}")
    if len(results[t]) > 5:
        print(f"   ... and {len(results[t]) - 5} more hits")
