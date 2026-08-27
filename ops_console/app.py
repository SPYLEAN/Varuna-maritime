import os
import requests
import streamlit as st

# Configure API URL from environment variable (defaulting to local FastAPI server)
API_URL = os.environ.get("SAMUDRANETRA_API_URL", "http://127.0.0.1:8000").rstrip("/")

st.set_page_config(
    page_title="SAMUDRANETRA — Operations Console",
    page_icon="🌊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🌊 SAMUDRANETRA Operations Console")
st.caption("Maritime Pollution Intelligence System — Internal Operations & Verification Console")

# Helper function to query FastAPI backend
def api_get(endpoint: str, params: dict = None):
    try:
        res = requests.get(f"{API_URL}{endpoint}", params=params, timeout=10)
        return res
    except Exception as err:
        st.error(f"Failed to connect to backend API at `{API_URL}`: {err}")
        return None


def api_post(endpoint: str, json_data: dict = None, files: dict = None, data: dict = None):
    try:
        if files:
            res = requests.post(f"{API_URL}{endpoint}", files=files, data=data, timeout=30)
        else:
            res = requests.post(f"{API_URL}{endpoint}", json=json_data, timeout=30)
        return res
    except Exception as err:
        st.error(f"Failed to connect to backend API at `{API_URL}`: {err}")
        return None


# ----------------------------------------------------
# SIDEBAR NAVIGATION & CASE SELECTION
# ----------------------------------------------------
st.sidebar.header("📁 Case Navigation")

# Fetch all existing cases
cases_res = api_get("/cases")
cases_list = cases_res.json() if cases_res and cases_res.status_code == 200 else []

# Build selection list
case_options = {"➕ Create New Case": None}
for c in cases_list:
    label = f"{c['name']} ({c['case_id']})"
    case_options[label] = c

# Session state handling for selected case
if "selected_case_id" not in st.session_state:
    st.session_state["selected_case_id"] = None

# Determine current selectbox index
selected_label = "➕ Create New Case"
if st.session_state["selected_case_id"]:
    for label, c_data in case_options.items():
        if c_data and c_data.get("case_id") == st.session_state["selected_case_id"]:
            selected_label = label
            break

chosen_option = st.sidebar.selectbox("Select Active Case", list(case_options.keys()), index=list(case_options.keys()).index(selected_label))
selected_case = case_options[chosen_option]

if selected_case:
    st.session_state["selected_case_id"] = selected_case["case_id"]
    st.sidebar.markdown("---")
    st.sidebar.subheader("📌 Selected Case Metadata")
    st.sidebar.markdown(f"**ID:** `{selected_case['case_id']}`")
    st.sidebar.markdown(f"**Name:** {selected_case['name']}")
    
    if selected_case.get("observation_timestamp"):
        st.sidebar.markdown(f"**Observation Time:** `{selected_case['observation_timestamp']}`")
    else:
        st.sidebar.markdown("**Observation Time:** *Not specified*")
        
    st.sidebar.markdown(f"**Created At:** `{selected_case['created_at']}`")
    
    lat = selected_case.get("latitude")
    lon = selected_case.get("longitude")
    if lat is not None and lon is not None:
        st.sidebar.markdown(f"**Location:** `{lat:.4f}, {lon:.4f}`")
    else:
        st.sidebar.markdown("**Location:** *Ungeoreferenced SAR pass*")
        
    # Analysis Status Badges
    st.sidebar.markdown("---")
    st.sidebar.subheader("📊 Analysis Module Statuses")
    status_map = selected_case.get("analysis_status", {})
    for mod in ["oil_detection", "spill_geometry", "hindcast", "ais_correlation", "attribution"]:
        st_val = status_map.get(mod, "not_started")
        color = "🟢" if st_val == "completed" else ("🟡" if st_val == "running" else ("🔴" if st_val == "failed" else ("⚪" if st_val == "not_started" else "🟠")))
        st.sidebar.markdown(f"{color} **{mod.replace('_', ' ').title()}:** `{st_val}`")
else:
    st.session_state["selected_case_id"] = None


# ----------------------------------------------------
# MAIN CONTENT AREA: TABS
# ----------------------------------------------------
tabs = st.tabs([
    "➕ Create Case",
    "📤 Upload Evidence",
    "🗂️ Evidence List",
    "🤖 Oil Detection Runner",
    "📜 Provenance Audit",
    "📊 System Status",
    "💬 Analyst Questions",
])


# ----------------------------------------------------
# TAB 1: CREATE CASE
# ----------------------------------------------------
with tabs[0]:
    st.header("Create New Incident Case")
    st.markdown("Register a new maritime pollution incident or benchmark SAR pass in SamudraNetra.")
    
    with st.form("create_case_form"):
        c_name = st.text_input("Case Name *", placeholder="e.g. Mumbai Offshore Slick Pass")
        c_desc = st.text_area("Description", placeholder="Optional incident context or satellite pass details...")
        
        col_time, col_lat, col_lon = st.columns(3)
        with col_time:
            c_obs_time = st.text_input("Observation/Acquisition Timestamp", placeholder="ISO string e.g. 2026-08-27T10:00:00Z")
        with col_lat:
            c_lat = st.number_input("Latitude (deg)", value=None, format="%.6f", help="Leave blank if ungeoreferenced benchmark image")
        with col_lon:
            c_lon = st.number_input("Longitude (deg)", value=None, format="%.6f", help="Leave blank if ungeoreferenced benchmark image")
            
        c_src = st.text_input("Source / Satellite Provider", placeholder="e.g. Sentinel-1A GRD / ESA CopHub")
        c_tags_str = st.text_input("Tags (comma separated)", placeholder="mumbai, sar, benchmark")
        
        submit_case = st.form_submit_button("Create Case")
        
    if submit_case:
        if not c_name.strip():
            st.error("Case Name is required.")
        else:
            tags = [t.strip() for t in c_tags_str.split(",") if t.strip()]
            payload = {
                "name": c_name.strip(),
                "description": c_desc.strip() if c_desc.strip() else None,
                "observation_timestamp": c_obs_time.strip() if c_obs_time.strip() else None,
                "latitude": c_lat,
                "longitude": c_lon,
                "source": c_src.strip() if c_src.strip() else None,
                "tags": tags,
            }
            res = api_post("/cases", json_data=payload)
            if res and res.status_code == 201:
                new_case = res.json()
                st.success(f"Case Created Successfully! Generated Case ID: `{new_case['case_id']}`")
                st.session_state["selected_case_id"] = new_case["case_id"]
                st.rerun()
            elif res:
                st.error(f"API Error ({res.status_code}): {res.text}")


# ----------------------------------------------------
# TAB 2: UPLOAD EVIDENCE
# ----------------------------------------------------
with tabs[1]:
    st.header("Upload Evidence")
    if not selected_case:
        st.warning("Please select or create a case from the sidebar first.")
    else:
        st.markdown(f"Attaching evidence file to active case: **{selected_case['name']}** (`{selected_case['case_id']}`)")
        
        uploaded_file = st.file_uploader("Select Evidence File (SAR image, oil mask, AIS, etc.)", key="ev_upload_file")
        
        col1, col2 = st.columns(2)
        with col1:
            ev_type = st.selectbox("Evidence Type", ["sar_image", "oil_mask", "ais", "met_ocean", "research_note", "other"])
            ev_source = st.text_input("Provider / Source", value=selected_case.get("source") or "Sentinel-1A")
            ev_timestamp = st.text_input("Acquisition Timestamp", value=selected_case.get("observation_timestamp") or "")
        with col2:
            is_synth = st.checkbox("Synthetic / Simulated Data", value=False)
            is_verified = st.checkbox("Human Expert Verified", value=False)
            ev_notes = st.text_area("Evidence Notes", placeholder="Context or preprocessing details...")
            
        if st.button("Upload Evidence", type="primary"):
            if not uploaded_file:
                st.error("Please select a file to upload.")
            else:
                files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type or "application/octet-stream")}
                data = {
                    "evidence_type": ev_type,
                    "source": ev_source if ev_source else None,
                    "acquisition_timestamp": ev_timestamp if ev_timestamp else None,
                    "is_synthetic": is_synth,
                    "is_human_verified": is_verified,
                    "notes": ev_notes if ev_notes else None,
                }
                res = api_post(f"/cases/{selected_case['case_id']}/evidence", files=files, data=data)
                if res and res.status_code == 201:
                    ev_res = res.json()
                    st.success(f"Evidence Uploaded! Evidence ID: `{ev_res['evidence_id']}`")
                    st.json(ev_res)
                    st.rerun()
                elif res:
                    st.error(f"Upload Failed ({res.status_code}): {res.text}")


# ----------------------------------------------------
# TAB 3: EVIDENCE LIST
# ----------------------------------------------------
with tabs[2]:
    st.header("Attached Case Evidence")
    if not selected_case:
        st.warning("Please select a case from the sidebar.")
    else:
        # Refetch fresh case data
        case_res = api_get(f"/cases/{selected_case['case_id']}")
        fresh_case = case_res.json() if case_res and case_res.status_code == 200 else selected_case
        manifest = fresh_case.get("data_manifest", {})
        evidence_items = manifest.get("evidence", [])
        output_masks = manifest.get("oil_masks", [])
        
        st.subheader(f"Uploaded Original Evidence ({len(evidence_items)})")
        if not evidence_items:
            st.info("No evidence uploaded yet for this case.")
        else:
            for ev in evidence_items:
                with st.expander(f"📄 {ev['original_filename']} ({ev['evidence_type']}) — ID: {ev['evidence_id']}"):
                    st.markdown(f"- **Evidence ID:** `{ev['evidence_id']}`")
                    st.markdown(f"- **Type:** `{ev['evidence_type']}`")
                    st.markdown(f"- **Size:** `{ev['file_size']} bytes`")
                    st.markdown(f"- **SHA256:** `{ev['sha256']}`")
                    st.markdown(f"- **Uploaded At:** `{ev['uploaded_at']}`")
                    st.markdown(f"- **Stored Path:** `{ev['stored_path']}`")
                    
                    # Preview image if it's a SAR image or oil mask
                    if ev['evidence_type'] in ['sar_image', 'oil_mask']:
                        img_url = f"{API_URL}/cases/{selected_case['case_id']}/evidence/{ev['evidence_id']}/file"
                        st.image(img_url, caption=f"Preview: {ev['original_filename']}", use_container_width=True)

        st.markdown("---")
        st.subheader(f"Generated Module Outputs ({len(output_masks)})")
        if not output_masks:
            st.info("No analysis output masks generated yet.")
        else:
            for om in output_masks:
                with st.expander(f"🖼️ Generated Output Mask ({om['output_id']}) — Analysis: {om['analysis_id']}"):
                    st.markdown(f"- **Output ID:** `{om['output_id']}`")
                    st.markdown(f"- **Binary Mask SHA256:** `{om['sha256']}`")
                    st.markdown(f"- **Generated At:** `{om['generated_at']}`")
                    
                    col_b, col_p = st.columns(2)
                    if om.get("probability_mask_path"):
                        prob_filename = os.path.basename(om["probability_mask_path"])
                        with col_p:
                            st.image(f"{API_URL}/cases/{selected_case['case_id']}/outputs/{prob_filename}", caption="Continuous Probability Mask", use_container_width=True)
                    if om.get("binary_mask_path"):
                        bin_filename = os.path.basename(om["binary_mask_path"])
                        with col_b:
                            st.image(f"{API_URL}/cases/{selected_case['case_id']}/outputs/{bin_filename}", caption="Binary Oil Mask", use_container_width=True)


# ----------------------------------------------------
# TAB 4: OIL DETECTION RUNNER
# ----------------------------------------------------
with tabs[3]:
    st.header("Oil Detection U-Net Runner")
    if not selected_case:
        st.warning("Please select a case from the sidebar.")
    else:
        # Pre-flight readiness check
        case_res = api_get(f"/cases/{selected_case['case_id']}")
        fresh_case = case_res.json() if case_res and case_res.status_code == 200 else selected_case
        ev_items = fresh_case.get("data_manifest", {}).get("evidence", [])
        sar_evs = [ev for ev in ev_items if ev.get("evidence_type") == "sar_image"]
        
        st.subheader("Pre-Flight Readiness Check")
        c1, c2 = st.columns(2)
        with c1:
            if sar_evs:
                st.success(f"✅ SAR Evidence Found: `{sar_evs[-1]['original_filename']}` (`{sar_evs[-1]['evidence_id']}`)")
            else:
                st.warning("⚠️ No SAR Image Evidence uploaded yet. Please upload a SAR image first.")
                
        default_ckpt_str = "models/oil_detection/samudranetra_oilseg_v0.pt"
        if not os.path.exists(default_ckpt_str) and os.path.exists("models/oiltrace_unet.pt"):
            default_ckpt_str = "models/oiltrace_unet.pt"
            
        with c2:
            if os.path.exists(default_ckpt_str):
                st.success(f"✅ Checkpoint Found: `{default_ckpt_str}`")
            else:
                st.warning(f"⚠️ Checkpoint missing at: `{default_ckpt_str}`. Module will return `insufficient_data`.")

        st.markdown("---")
        st.subheader("Inference Settings")
        ckpt_input = st.text_input("Model Checkpoint Path", value=default_ckpt_str)
        thresh_input = st.slider("Probability Decision Threshold", min_value=0.05, max_value=0.95, value=0.50, step=0.05)
        
        sar_select_options = {f"{ev['original_filename']} ({ev['evidence_id']})": ev['evidence_id'] for ev in sar_evs}
        selected_sar_id = None
        if sar_evs:
            chosen_sar_label = st.selectbox("Select Input SAR Image", list(sar_select_options.keys()))
            selected_sar_id = sar_select_options[chosen_sar_label]
            
        if st.button("🚀 Run Oil Detection Analysis", type="primary"):
            payload = {
                "checkpoint_path": ckpt_input.strip() if ckpt_input.strip() else None,
                "threshold": thresh_input,
                "sar_evidence_id": selected_sar_id,
            }
            with st.spinner("Executing U-Net oil segmentation inference..."):
                res = api_post(f"/cases/{selected_case['case_id']}/analysis/oil-detection", json_data=payload)
                
            if res and res.status_code == 200:
                an_res = res.json()
                st.session_state["latest_analysis_result"] = an_res
                st.rerun()
            elif res:
                st.error(f"Analysis Execution Failed ({res.status_code}): {res.text}")
                
        # Render latest analysis output
        latest_an = st.session_state.get("latest_analysis_result")
        if latest_an and latest_an.get("case_id") == selected_case["case_id"]:
            st.markdown("---")
            st.subheader("Analysis Results")
            st.markdown(f"**Analysis ID:** `{latest_an['analysis_id']}` | **Status:** `{latest_an['status']}`")
            
            if latest_an["status"] == "insufficient_data":
                st.warning(f"**Insufficient Data:** {latest_an.get('error') or 'Missing required SAR evidence or checkpoint.'}")
                if latest_an.get("warnings"):
                    for w in latest_an["warnings"]:
                        st.info(f"Reason: {w}")
            elif latest_an["status"] == "completed":
                st.success("Oil Detection Inference Completed!")
                
                # Side-by-side Image Visualization
                res_dict = latest_an.get("result", {})
                col_img1, col_img2, col_img3 = st.columns(3)
                
                with col_img1:
                    st.markdown("**1. Input SAR Scene**")
                    if latest_an.get("input_evidence_ids"):
                        sar_ev_id = latest_an["input_evidence_ids"][0]
                        st.image(f"{API_URL}/cases/{selected_case['case_id']}/evidence/{sar_ev_id}/file", use_container_width=True)
                        
                with col_img2:
                    st.markdown("**2. Continuous Probability Mask**")
                    if res_dict.get("probability_mask_path"):
                        p_file = os.path.basename(res_dict["probability_mask_path"])
                        st.image(f"{API_URL}/cases/{selected_case['case_id']}/outputs/{p_file}", use_container_width=True)
                        
                with col_img3:
                    st.markdown("**3. Thresholded Binary Oil Mask**")
                    if res_dict.get("binary_mask_path"):
                        b_file = os.path.basename(res_dict["binary_mask_path"])
                        st.image(f"{API_URL}/cases/{selected_case['case_id']}/outputs/{b_file}", use_container_width=True)
                        
                # Raw Model Output Statistics
                st.markdown("### Raw Model Output Statistics")
                st.caption("Quantitative statistics computed directly from output probability and binary mask arrays.")
                
                m1, m2, m3, m4, m5 = st.columns(5)
                m1.metric("Oil Fraction", f"{res_dict.get('oil_fraction', 0.0):.6f}")
                m2.metric("Mean Probability", f"{res_dict.get('mean_probability', 0.0):.6f}")
                
                mean_oil_p = res_dict.get("mean_oil_probability")
                m3.metric("Mean Oil Prob", f"{mean_oil_p:.6f}" if mean_oil_p is not None else "N/A")
                
                m4.metric("Max Probability", f"{res_dict.get('max_probability', 0.0):.6f}")
                m5.metric("Threshold", f"{res_dict.get('threshold', 0.5):.2f}")
                
                st.warning("⚠️ **Calibrated confidence: Not available for OilSeg V0** (Uncalibrated deep learning model output statistics must not be interpreted as confidence scores).")


# ----------------------------------------------------
# TAB 5: PROVENANCE AUDIT
# ----------------------------------------------------
with tabs[4]:
    st.header("Provenance & Audit Trail")
    if not selected_case:
        st.warning("Please select a case from the sidebar.")
    else:
        case_res = api_get(f"/cases/{selected_case['case_id']}")
        fresh_case = case_res.json() if case_res and case_res.status_code == 200 else selected_case
        gen_results = fresh_case.get("data_manifest", {}).get("generated_analysis_results", [])
        
        st.markdown(f"Provenance records for case **{selected_case['name']}** (`{selected_case['case_id']}`)")
        
        if not gen_results:
            st.info("No analysis provenance records recorded yet.")
        else:
            for idx, res_item in enumerate(reversed(gen_results)):
                with st.expander(f"🔍 Analysis Run `{res_item['analysis_id']}` ({res_item['module']}) — {res_item['status']}"):
                    st.markdown("#### Input Evidence Provenance")
                    st.markdown(f"- **Input Evidence IDs:** `{res_item.get('input_evidence_ids')}`")
                    st.markdown(f"- **Input SAR SHA256:** `{res_item.get('input_hashes')}`")
                    
                    st.markdown("#### Model Provenance")
                    cfg = res_item.get("configuration", {})
                    st.markdown(f"- **Module Name:** `{res_item.get('module')}` (v`{res_item.get('module_version')}`)")
                    st.markdown(f"- **Checkpoint Path:** `{cfg.get('checkpoint_path')}`")
                    st.markdown(f"- **Checkpoint SHA256:** `{cfg.get('checkpoint_sha256') or 'N/A'}`")
                    st.markdown(f"- **Decision Threshold:** `{cfg.get('threshold')}`")
                    
                    st.markdown("#### Execution Timestamps")
                    st.markdown(f"- **Started At:** `{res_item.get('started_at')}`")
                    st.markdown(f"- **Completed At:** `{res_item.get('completed_at')}`")
                    
                    if res_item.get("result"):
                        res_d = res_item["result"]
                        st.markdown("#### Generated Output Hashes")
                        st.markdown(f"- **Binary Mask Path:** `{res_d.get('binary_mask_path')}`")
                        st.markdown(f"- **Binary Mask SHA256:** `{res_d.get('binary_mask_sha256')}`")
                        st.markdown(f"- **Probability Mask Path:** `{res_d.get('probability_mask_path')}`")
                        st.markdown(f"- **Probability Mask SHA256:** `{res_d.get('probability_mask_sha256') or 'N/A'}`")


# ----------------------------------------------------
# TAB 6: SYSTEM MODULE STATUS TRACKER
# ----------------------------------------------------
with tabs[5]:
    st.header("SamudraNetra Module Status Tracker")
    if not selected_case:
        st.warning("Please select a case from the sidebar.")
    else:
        case_res = api_get(f"/cases/{selected_case['case_id']}")
        fresh_case = case_res.json() if case_res and case_res.status_code == 200 else selected_case
        status_dict = fresh_case.get("analysis_status", {})
        
        st.markdown(f"Module pipeline tracking for active case: **{selected_case['name']}** (`{selected_case['case_id']}`)")
        
        modules_info = [
            ("Oil Detection", "oil_detection", "U-Net SAR oil spill segmentation engine"),
            ("Spill Geometry", "spill_geometry", "Geospatial contouring & area polygon calculation"),
            ("Hindcast", "hindcast", "Met-ocean wind/current drift backtracking"),
            ("AIS Correlation", "ais_correlation", "Historical vessel trajectory matching"),
            ("Attribution", "attribution", "Explainable vessel spill attribution score"),
        ]
        
        for name, key, desc in modules_info:
            curr_st = status_dict.get(key, "not_started")
            col_m1, col_m2, col_m3 = st.columns([2, 2, 4])
            with col_m1:
                st.subheader(name)
            with col_m2:
                if curr_st == "completed":
                    st.success("Status: completed")
                elif curr_st == "running":
                    st.warning("Status: running")
                elif curr_st == "insufficient_data":
                    st.info("Status: insufficient_data")
                elif curr_st == "failed":
                    st.error("Status: failed")
                else:
                    st.caption("Status: not_started")
            with col_m3:
                st.caption(desc)
            st.markdown("---")


# ----------------------------------------------------
# TAB 7: ANALYST QUESTIONS
# ----------------------------------------------------
with tabs[6]:
    st.header("Analyst Notes & Questions")
    if not selected_case:
        st.warning("Please select a case from the sidebar.")
    else:
        case_res = api_get(f"/cases/{selected_case['case_id']}")
        fresh_case = case_res.json() if case_res and case_res.status_code == 200 else selected_case
        questions_list = fresh_case.get("data_manifest", {}).get("analyst_questions", [])
        
        with st.form("add_question_form"):
            q_text = st.text_area("Analyst Question / Investigation Note *", placeholder="e.g., Is this low-backscatter feature a organic slick or wind look-alike?")
            q_author = st.text_input("Asked By", value="Analyst 1")
            submit_q = st.form_submit_button("Add Question")
            
        if submit_q:
            if not q_text.strip():
                st.error("Question text is required.")
            else:
                q_payload = {"question": q_text.strip(), "asked_by": q_author.strip() if q_author.strip() else None}
                res = api_post(f"/cases/{selected_case['case_id']}/questions", json_data=q_payload)
                if res and res.status_code == 201:
                    st.success("Question recorded!")
                    st.rerun()
                elif res:
                    st.error(f"Failed to record question: {res.text}")
                    
        st.markdown("---")
        st.subheader(f"Recorded Questions ({len(questions_list)})")
        if not questions_list:
            st.info("No questions recorded for this case.")
        else:
            for q in reversed(questions_list):
                st.markdown(f"**Q:** {q['question']}")
                st.caption(f"Asked by: `{q.get('asked_by') or 'Anonymous'}` | Timestamp: `{q['created_at']}` | ID: `{q['question_id']}`")
                st.markdown("---")
