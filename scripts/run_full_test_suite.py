import subprocess
import re
import datetime

print("Running full pytest suite across backend/tests and ml/tests...")
start_time = datetime.datetime.now(datetime.timezone.utc)

# 1. Run collect-only to get per-file counts
proc_collect = subprocess.run(
    [".venv/Scripts/python.exe", "-m", "pytest", "--collect-only", "-q", "backend/tests", "ml/tests"],
    capture_output=True, text=True
)

file_counts = {}
for line in proc_collect.stdout.splitlines():
    line = line.strip()
    if "::" in line:
        file_path = line.split("::")[0]
        file_counts[file_path] = file_counts.get(file_path, 0) + 1

print("\n--- PER-FILE COLLECTED TEST COUNTS ---")
for f, cnt in sorted(file_counts.items()):
    print(f"{f}: {cnt}")

total_collected = sum(file_counts.values())
print(f"\nTotal test files: {len(file_counts)}")
print(f"Total collected test cases: {total_collected}")

# 2. Run execution
proc_run = subprocess.run(
    [".venv/Scripts/python.exe", "-m", "pytest", "backend/tests", "ml/tests", "-q"],
    capture_output=True, text=True
)
end_time = datetime.datetime.now(datetime.timezone.utc)

print("\n--- PYTEST EXECUTION SUMMARY ---")
out_lines = [l for l in proc_run.stdout.splitlines() if l.strip()]
summary_line = out_lines[-1] if out_lines else "NO OUTPUT"
print("STDOUT SUMMARY LINE:", summary_line)
if proc_run.stderr:
    print("STDERR:", proc_run.stderr[:500])

print(f"Start Time (UTC): {start_time.isoformat()}")
print(f"End Time (UTC): {end_time.isoformat()}")
print(f"Exit Code: {proc_run.returncode}")

with open("07_results/final_build/pytest_full_run.log", "w", encoding="utf-8") as f:
    f.write(f"Start: {start_time.isoformat()}\n")
    f.write(f"End: {end_time.isoformat()}\n")
    f.write(f"Exit Code: {proc_run.returncode}\n")
    f.write(f"Summary Line: {summary_line}\n\n")
    f.write("Per-File Counts:\n")
    for fp, c in sorted(file_counts.items()):
        f.write(f"  {fp}: {c}\n")
    f.write("\nFull Output:\n")
    f.write(proc_run.stdout)
