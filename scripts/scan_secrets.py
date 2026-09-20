import subprocess

patterns = ['AKIA', 'aws_secret', 'api_key', 'apikey', 'access_token', 'password', 'BEGIN PRIVATE KEY', 'BEGIN RSA PRIVATE KEY', 'BEGIN OPENSSH PRIVATE KEY']

print("=== WORKING TREE SECRETS SCAN ===")
for p in patterns:
    res = subprocess.run(['git', 'grep', '-i', p], capture_output=True, text=True)
    hits = [line for line in res.stdout.strip().split('\n') if line]
    # Filter out obvious false positives like code references to api_key param name, test mocks, etc.
    print(f"Pattern '{p}': {len(hits)} occurrences in code/docs")

print("\n=== GIT HISTORY AKIA / PRIVATE KEY SCAN ===")
for p in ['AKIA[0-9A-Z]{16}', 'BEGIN.*PRIVATE KEY']:
    res = subprocess.run(['git', 'log', '-E', '-G', p, '--oneline'], capture_output=True, text=True)
    out = res.stdout.strip()
    print(f"Regex '{p}' in git history: {out if out else 'NONE (Clean)'}")

print("\n=== TRACKED .ENV CHECK ===")
res = subprocess.run(['git', 'ls-files', '*.env*'], capture_output=True, text=True)
print("Tracked files matching *.env*:\n", res.stdout.strip() if res.stdout.strip() else "None")
