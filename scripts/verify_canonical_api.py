import urllib.request
import json
import sys

cases = [
    'R001_WAKASHIO',
    'R002_GRANDE_AMERICA',
    'R003_PRINCESS_EMPRESS',
    'R004_SANCHI',
    'R005_DEEPWATER_HORIZON'
]

print("=== VERIFYING ALL CANONICAL RESEARCH CASES ON LIVE API ===")

for cid in cases:
    print(f"\n--- Testing Case: {cid} ---")
    
    # 1. Get case
    with urllib.request.urlopen(f"http://127.0.0.1:8000/api/v1/cases/{cid}") as resp:
        c_data = json.loads(resp.read().decode())
        print(f"  Name: {c_data.get('name')}")
        print(f"  Region: {c_data.get('region')}")
        print(f"  Status: {c_data.get('status')}")
        print(f"  Coordinates: {c_data.get('latitude')}, {c_data.get('longitude')}")

    # 2. Get workflow
    with urllib.request.urlopen(f"http://127.0.0.1:8000/api/v1/cases/{cid}/workflow") as resp:
        wf_data = json.loads(resp.read().decode())
        stages = wf_data.get("stages", {})
        print(f"  Workflow Status: {wf_data.get('status')} | Current Stage: {wf_data.get('current_stage')} | Stages: {len(stages)}")

    # 3. Get response priority
    with urllib.request.urlopen(f"http://127.0.0.1:8000/api/v1/cases/{cid}/intelligence/response-priority") as resp:
        prio_data = json.loads(resp.read().decode())
        top_receptor = prio_data.get("receptors", [{}])[0] if prio_data.get("receptors") else {}
        rec_name = top_receptor.get("name") or top_receptor.get("receptor_name")
        prio_level = top_receptor.get("priority") or top_receptor.get("threat_level")
        impact_h = top_receptor.get("time_to_impact_hours") or prio_data.get("response_window_hours")
        print(f"  Response Priority: mode={prio_data.get('engine_execution_mode', prio_data.get('execution_mode'))}")
        print(f"    Top Receptor: {rec_name} (priority: {prio_level}, window: {impact_h}h)")

    # 4. Ask Intelligence
    ask_req = urllib.request.Request(
        f"http://127.0.0.1:8000/api/v1/cases/{cid}/intelligence/ask",
        data=json.dumps({"question": "What are the key receptors at risk and required operational containment actions?"}).encode(),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(ask_req) as resp:
        ask_res = json.loads(resp.read().decode())
        ans = ask_res.get("answer", "")
        print(f"  Intelligence Q&A: mode={ask_res.get('execution_mode')}")
        print(f"    Answer excerpt: {ans[:120]}...")

    # 5. Incident review
    with urllib.request.urlopen(f"http://127.0.0.1:8000/api/v1/cases/{cid}/workflow/incident-review") as resp:
        rev_data = json.loads(resp.read().decode())
        print(f"  Incident Review: {rev_data.get('report_id')} (confidence: {rev_data.get('overall_confidence')})")

print("\nALL 5 CANONICAL CASES VERIFIED SUCCESSFULLY ON LIVE BACKEND!")
