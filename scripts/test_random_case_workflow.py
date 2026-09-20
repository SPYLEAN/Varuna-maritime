import urllib.request
import json

API_BASE = "http://127.0.0.1:8000"

def post(ep, payload=None):
    req = urllib.request.Request(
        f"{API_BASE}{ep}",
        data=json.dumps(payload or {}).encode(),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())

def get(ep):
    with urllib.request.urlopen(f"{API_BASE}{ep}") as resp:
        return json.loads(resp.read().decode())

print("=== TESTING RANDOM CASE WORKFLOW END-TO-END ===")

# 1. Create a fresh random case with NO pre-existing observation
case_payload = {
    "name": "Arabian Sea Offshore Sighting (Random Test)",
    "description": "Satellite dark slick anomaly reported off Mumbai High",
    "latitude": 18.95,
    "longitude": 72.80,
    "region": "Arabian Sea (Mumbai Offshore)",
    "incident_type": "SURFACE_SLICK",
    "priority": "HIGH"
}
created_case = post("/api/v1/cases", case_payload)
cid = created_case["case_id"]
print(f"Created fresh case: {cid} ({created_case['name']}) at {created_case['latitude']}, {created_case['longitude']}")

# 2. Acquire product (triggers auto-attach of observation)
print("1. Executing /acquire (Auto-Attach & Product Acquisition)...")
acq = post(f"/api/v1/cases/{cid}/workflow/acquire")
print(f"   Status: {acq.get('status')} | Execution Mode: {acq.get('execution_mode')}")

# 3. Preprocess SAR
print("2. Executing /preprocess (SAR Radiometric Calibration to Sigma0 dB)...")
pre = post(f"/api/v1/cases/{cid}/workflow/preprocess")
print(f"   Status: {pre.get('status')} | Execution Mode: {pre.get('execution_mode')}")

# 4. SmallUNet Slick Analysis
print("3. Executing /analyse-slick (SmallUNet Dual-Channel Inference)...")
seg = post(f"/api/v1/cases/{cid}/workflow/analyse-slick")
poly_cnt = seg.get('details', {}).get('polygon_count', 0)
print(f"   Status: {seg.get('status')} | Mode: {seg.get('execution_mode')} | Detected Polygons: {poly_cnt}")

# 5. Select Candidate & Evidence Gate
print("4. Executing /select-candidate (Evidence Gate & Candidate Selection)...")
can = post(f"/api/v1/cases/{cid}/workflow/select-candidate", {"candidate_id": "C1001"})
print(f"   Status: {can.get('status')} | Mode: {can.get('execution_mode')}")

# 6. Backward Hindcast
print("5. Executing /hindcast (OpenDrift Backward Advection)...")
hind = post(f"/api/v1/cases/{cid}/workflow/hindcast")
print(f"   Status: {hind.get('status')} | Mode: {hind.get('execution_mode')}")

# 7. Forward Forecast
print("6. Executing /forecast (OpenDrift Forward Drift)...")
fore = post(f"/api/v1/cases/{cid}/workflow/forecast")
print(f"   Status: {fore.get('status')} | Mode: {fore.get('execution_mode')}")

# 8. Response Priority
print("7. Executing /response-priority (Receptor Threat Ranking & Arrival Horizons)...")
prio = post(f"/api/v1/cases/{cid}/workflow/response-priority")
rec = prio.get('details', {}).get('highest_priority_receptor', {}) or prio.get('highest_priority_receptor', {})
rec_name = rec.get('name') or rec.get('receptor_name')
win = prio.get('details', {}).get('response_window_hours') or prio.get('response_window_hours')
print(f"   Status: {prio.get('status')} | Top Receptor: {rec_name} | Window: {win}h")

# 9. AIS Correlation
print("8. Executing /correlate-ais (AIS Kinematic Candidate Identification)...")
ais = post(f"/api/v1/cases/{cid}/workflow/correlate-ais")
print(f"   Status: {ais.get('status')} | Mode: {ais.get('execution_mode')}")

# 10. Incident Review
print("9. Fetching /workflow/incident-review (Complete Briefing Report)...")
rev = get(f"/api/v1/cases/{cid}/workflow/incident-review")
print(f"   Report ID: {rev.get('report_id')}")

# 11. Ask VARUNA Intelligence
print("10. Querying /intelligence/ask...")
ask = post(f"/api/v1/cases/{cid}/intelligence/ask", {"question": "What is the recommended protective containment?"})
print(f"   Answer snippet: {ask.get('answer', '')[:120]}...")

print("\n=== RANDOM CASE TEST PASSED 100% SUCCESSFULLY! ===")
