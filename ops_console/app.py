import os
import json
import requests
import streamlit as st

# Configure API URL from environment variable (defaulting to local FastAPI server)
API_URL = (
    os.environ.get("VARUNA_API_URL")
    or os.environ.get("SAMUDRANETRA_API_URL", "http://127.0.0.1:8000")
).rstrip("/")

st.set_page_config(
    page_title="VARUNA — Operations Console",
    page_icon="🌊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🌊 VARUNA Operations Console")
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
    c_name = c.get("name", "Unnamed Case")
    c_id = c.get("case_id", "N/A")
    label = f"{c_name} ({c_id})"
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
    st.session_state["selected_case_id"] = selected_case.get("case_id")
    st.sidebar.markdown("---")
    st.sidebar.subheader("📌 Selected Case Metadata")
    st.sidebar.markdown(f"**ID:** `{selected_case.get('case_id', 'N/A')}`")
    st.sidebar.markdown(f"**Name:** {selected_case.get('name', 'N/A')}")
    
    if selected_case.get("observation_timestamp"):
        st.sidebar.markdown(f"**Observation Time:** `{selected_case.get('observation_timestamp')}`")
    else:
        st.sidebar.markdown("**Observation Time:** *Not specified*")
        
    st.sidebar.markdown(f"**Created At:** `{selected_case.get('created_at', 'N/A')}`")
    
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
    "🤖 Oil Detection",
    "📐 Spill Geometry",
    "🌊 Hindcast Readiness",
    "📜 Provenance Audit",
    "📊 System Status",
    "💬 Analyst Questions",
])


# ----------------------------------------------------
# TAB 1: CREATE CASE
# ----------------------------------------------------
with tabs[0]:
    st.header("Create New Incident Case")
    st.markdown("Register a new maritime pollution incident or benchmark SAR pass in VARUNA.")
    
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
        case_name = selected_case.get("name", "Active Case")
        case_id = selected_case.get("case_id", "N/A")
        st.markdown(f"Attaching evidence file to active case: **{case_name}** (`{case_id}`)")
        
        uploaded_file = st.file_uploader("Select Evidence File (SAR, met-ocean NC/CSV/GeoTIFF, AIS, etc.)", key="ev_upload_file")
        
        col1, col2 = st.columns(2)
        with col1:
            ev_type = st.selectbox("Evidence Type", ["sar_image", "oil_mask", "ocean_current", "wind", "wave", "met_ocean", "ais", "research_note", "other"])
            ev_source = st.text_input("Provider / Source", value=selected_case.get("source") or "Copernicus Marine / ERA5")
            ev_timestamp = st.text_input("Acquisition / Observation Timestamp", value=selected_case.get("observation_timestamp") or "")
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
                res = api_post(f"/cases/{case_id}/evidence", files=files, data=data)
                if res and res.status_code == 201:
                    ev_res = res.json()
                    st.success(f"Evidence Uploaded! Evidence ID: `{ev_res.get('evidence_id')}`")
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
        case_id = selected_case.get("case_id")
        case_res = api_get(f"/cases/{case_id}")
        fresh_case = case_res.json() if case_res and case_res.status_code == 200 else selected_case
        manifest = fresh_case.get("data_manifest", {})
        evidence_items = manifest.get("evidence", [])
        output_masks = manifest.get("oil_masks", [])
        
        st.subheader(f"Uploaded Evidence Records ({len(evidence_items)})")
        if not evidence_items:
            st.info("No evidence uploaded yet for this case.")
        else:
            for ev in evidence_items:
                ev_name = ev.get('original_filename', 'Unnamed')
                ev_type = ev.get('evidence_type', 'other')
                ev_id = ev.get('evidence_id', 'N/A')
                with st.expander(f"📄 {ev_name} ({ev_type}) — ID: {ev_id}"):
                    st.markdown(f"- **Evidence ID:** `{ev_id}`")
                    st.markdown(f"- **Type:** `{ev_type}`")
                    st.markdown(f"- **Size:** `{ev.get('file_size', 0)} bytes`")
                    st.markdown(f"- **SHA256:** `{ev.get('sha256', 'N/A')}`")
                    st.markdown(f"- **Uploaded At:** `{ev.get('uploaded_at', 'N/A')}`")
                    st.markdown(f"- **Stored Path:** `{ev.get('stored_path', 'N/A')}`")
                    
                    if ev_type in ['sar_image', 'oil_mask']:
                        img_url = f"{API_URL}/cases/{case_id}/evidence/{ev_id}/file"
                        st.image(img_url, caption=f"Preview: {ev_name}", use_container_width=True)

        st.markdown("---")
        st.subheader(f"Generated Module Outputs ({len(output_masks)})")
        if not output_masks:
            st.info("No analysis output masks generated yet.")
        else:
            for om in output_masks:
                out_id = om.get("output_id", "N/A")
                an_id = om.get("analysis_id", "N/A")
                bin_hash = om.get("binary_mask_sha256") or om.get("sha256") or "Not available"
                prob_hash = om.get("probability_mask_sha256") or "Not available"
                gen_at = om.get("generated_at", "N/A")
                
                with st.expander(f"🖼️ Generated Output Mask ({out_id}) — Analysis: {an_id}"):
                    st.markdown(f"- **Output ID:** `{out_id}`")
                    st.markdown(f"- **Binary Mask SHA256:** `{bin_hash}`")
                    st.markdown(f"- **Probability Mask SHA256:** `{prob_hash}`")
                    st.markdown(f"- **Generated At:** `{gen_at}`")
                    
                    col_b, col_p = st.columns(2)
                    if om.get("probability_mask_path"):
                        prob_filename = os.path.basename(om["probability_mask_path"])
                        with col_p:
                            st.image(f"{API_URL}/cases/{case_id}/outputs/{prob_filename}", caption="Continuous Probability Mask", use_container_width=True)
                    if om.get("binary_mask_path"):
                        bin_filename = os.path.basename(om["binary_mask_path"])
                        with col_b:
                            st.image(f"{API_URL}/cases/{case_id}/outputs/{bin_filename}", caption="Binary Oil Mask", use_container_width=True)


# ----------------------------------------------------
# TAB 4: OIL DETECTION RUNNER
# ----------------------------------------------------
with tabs[3]:
    st.header("Oil Detection U-Net Runner")
    if not selected_case:
        st.warning("Please select a case from the sidebar.")
    else:
        case_id = selected_case.get("case_id")
        case_res = api_get(f"/cases/{case_id}")
        fresh_case = case_res.json() if case_res and case_res.status_code == 200 else selected_case
        ev_items = fresh_case.get("data_manifest", {}).get("evidence", [])
        sar_evs = [ev for ev in ev_items if ev.get("evidence_type") == "sar_image"]
        
        st.subheader("Pre-Flight Readiness Check")
        c1, c2 = st.columns(2)
        with c1:
            if sar_evs:
                latest_sar = sar_evs[-1]
                st.success(f"✅ SAR Evidence Found: `{latest_sar.get('original_filename', 'SAR Scene')}` (`{latest_sar.get('evidence_id', 'N/A')}`)")
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
        
        sar_select_options = {f"{ev.get('original_filename', 'SAR')} ({ev.get('evidence_id')})": ev.get('evidence_id') for ev in sar_evs}
        selected_sar_id = None
        if sar_evs:
            chosen_sar_label = st.selectbox("Select Input SAR Image", list(sar_select_options.keys()))
            selected_sar_id = sar_select_options.get(chosen_sar_label)
            
        if st.button("🚀 Run Oil Detection Analysis", type="primary"):
            payload = {
                "checkpoint_path": ckpt_input.strip() if ckpt_input.strip() else None,
                "threshold": thresh_input,
                "sar_evidence_id": selected_sar_id,
            }
            with st.spinner("Executing U-Net oil segmentation inference..."):
                res = api_post(f"/cases/{case_id}/analysis/oil-detection", json_data=payload)
                
            if res and res.status_code == 200:
                an_res = res.json()
                st.session_state["latest_oil_analysis"] = an_res
                st.rerun()
            elif res:
                st.error(f"Analysis Execution Failed ({res.status_code}): {res.text}")
                
        # Render latest analysis output
        latest_an = st.session_state.get("latest_oil_analysis")
        if latest_an and latest_an.get("case_id") == case_id:
            st.markdown("---")
            st.subheader("Analysis Results")
            st.markdown(f"**Analysis ID:** `{latest_an.get('analysis_id', 'N/A')}` | **Status:** `{latest_an.get('status', 'N/A')}`")
            
            an_status = latest_an.get("status")
            if an_status == "insufficient_data":
                st.warning(f"**Insufficient Data:** {latest_an.get('error') or 'Missing required SAR evidence or checkpoint.'}")
                if latest_an.get("warnings"):
                    for w in latest_an["warnings"]:
                        st.info(f"Reason: {w}")
            elif an_status == "completed":
                st.success("Oil Detection Inference Completed!")
                
                # Side-by-side Image Visualization
                res_dict = latest_an.get("result") or {}
                col_img1, col_img2, col_img3 = st.columns(3)
                
                with col_img1:
                    st.markdown("**1. Input SAR Scene**")
                    input_ids = latest_an.get("input_evidence_ids") or []
                    if input_ids:
                        sar_ev_id = input_ids[0]
                        st.image(f"{API_URL}/cases/{case_id}/evidence/{sar_ev_id}/file", use_container_width=True)
                        
                with col_img2:
                    st.markdown("**2. Continuous Probability Mask**")
                    prob_path = res_dict.get("probability_mask_path")
                    if prob_path:
                        p_file = os.path.basename(prob_path)
                        st.image(f"{API_URL}/cases/{case_id}/outputs/{p_file}", use_container_width=True)
                        
                with col_img3:
                    st.markdown("**3. Thresholded Binary Oil Mask**")
                    bin_path = res_dict.get("binary_mask_path")
                    if bin_path:
                        b_file = os.path.basename(bin_path)
                        st.image(f"{API_URL}/cases/{case_id}/outputs/{b_file}", use_container_width=True)
                        
                # Raw Model Output Statistics
                st.markdown("### Raw Model Output Statistics")
                st.caption("Quantitative statistics computed directly from output probability and binary mask arrays.")
                
                m1, m2, m3, m4, m5 = st.columns(5)
                
                oil_f = res_dict.get("oil_fraction")
                m1.metric("Oil Fraction", f"{oil_f:.6f}" if isinstance(oil_f, (int, float)) else "N/A")
                
                mean_p = res_dict.get("mean_probability")
                m2.metric("Mean Probability", f"{mean_p:.6f}" if isinstance(mean_p, (int, float)) else "N/A")
                
                mean_oil_p = res_dict.get("mean_oil_probability")
                m3.metric("Mean Oil Prob", f"{mean_oil_p:.6f}" if isinstance(mean_oil_p, (int, float)) else "N/A")
                
                max_p = res_dict.get("max_probability")
                m4.metric("Max Probability", f"{max_p:.6f}" if isinstance(max_p, (int, float)) else "N/A")
                
                thresh_v = res_dict.get("threshold")
                m5.metric("Threshold", f"{thresh_v:.2f}" if isinstance(thresh_v, (int, float)) else "N/A")
                
                st.warning("⚠️ **Calibrated confidence: Not available for OilSeg V0** (Uncalibrated deep learning model output statistics must not be interpreted as confidence scores).")


# ----------------------------------------------------
# TAB 5: SPILL GEOMETRY RUNNER
# ----------------------------------------------------
with tabs[4]:
    st.header("Spill Geometry & Characterisation Engine")
    if not selected_case:
        st.warning("Please select a case from the sidebar.")
    else:
        case_id = selected_case.get("case_id")
        case_res = api_get(f"/cases/{case_id}")
        fresh_case = case_res.json() if case_res and case_res.status_code == 200 else selected_case
        gen_results = fresh_case.get("data_manifest", {}).get("generated_analysis_results", [])
        
        # Check prerequisite completed oil_detection runs
        completed_oil_ans = [r for r in gen_results if r.get("module") == "oil_detection" and r.get("status") == "completed"]
        
        st.subheader("Prerequisite Check")
        if completed_oil_ans:
            latest_oil = completed_oil_ans[-1]
            st.success(f"✅ Completed Oil Detection Output Available (`{latest_oil.get('analysis_id')}`)")
        else:
            st.warning("⚠️ No completed Oil Detection analysis found for this case. Run Oil Detection first.")

        st.markdown("---")
        st.subheader("Geometry Extraction Settings")
        min_size_input = st.number_input("Minimum Component Size (pixels)", min_value=1, value=1, help="Filter out micro-components smaller than this size")
        
        if st.button("🚀 Run Spill Geometry Analysis", type="primary"):
            payload = {
                "min_component_size_pixels": min_size_input,
            }
            with st.spinner("Extracting slick components and computing morphological geometry..."):
                res = api_post(f"/cases/{case_id}/analysis/spill-geometry", json_data=payload)
                
            if res and res.status_code == 200:
                geom_res = res.json()
                st.session_state["latest_geom_analysis"] = geom_res
                st.rerun()
            elif res:
                st.error(f"Spill Geometry Execution Failed ({res.status_code}): {res.text}")

        # Render latest geometry analysis output
        latest_geom = st.session_state.get("latest_geom_analysis")
        if latest_geom and latest_geom.get("case_id") == case_id:
            st.markdown("---")
            st.subheader("SPILL CHARACTERISATION RESULTS")
            st.markdown(f"**Analysis ID:** `{latest_geom.get('analysis_id', 'N/A')}` | **Status:** `{latest_geom.get('status', 'N/A')}`")
            
            geom_status = latest_geom.get("status")
            if geom_status == "insufficient_data":
                st.warning(f"**Insufficient Data:** {latest_geom.get('error') or 'Missing required Oil Detection mask.'}")
                if latest_geom.get("warnings"):
                    for w in latest_geom["warnings"]:
                        st.info(f"Reason: {w}")
            elif geom_status == "completed":
                st.success("Spill Geometry Characterisation Completed!")
                res_d = latest_geom.get("result") or {}
                scene_stats = res_d.get("scene_level_statistics") or {}
                georef = res_d.get("georeferenced", False)

                # Spatial Mode Display
                st.markdown("### Spatial Scale Mode")
                if not georef:
                    st.info("ℹ️ **Pixel-space analysis only — geographic scale unavailable.** (Source imagery lacks CRS transform metadata).")
                else:
                    analysis_crs = res_d.get("analysis_crs") or res_d.get("source_crs")
                    st.success(f"🌐 **Georeferenced Mode Active** | Source CRS: `{res_d.get('source_crs')}` | Analysis CRS: `{analysis_crs}`")
                    g1, g2, g3 = st.columns(3)
                    area_m2_val = res_d.get("total_area_m2")
                    area_km2_val = res_d.get("total_area_km2")
                    g1.metric("Total Area (m²)", f"{area_m2_val:,.2f}" if isinstance(area_m2_val, (int, float)) else "N/A")
                    g2.metric("Total Area (km²)", f"{area_km2_val:,.6f}" if isinstance(area_km2_val, (int, float)) else "N/A")
                    geo_c = res_d.get("geographic_centroid")
                    g3.metric("Geographic Centroid", f"{geo_c[0]:.4f}, {geo_c[1]:.4f}" if geo_c else "N/A")
                    st.caption(f"Area Calculation Method: `{res_d.get('area_calculation_method')}`")

                # Scene Morphological Metrics
                st.markdown("### Scene-Level Morphological Summary")
                s1, s2, s3, s4, s5, s6 = st.columns(6)
                s1.metric("Slick Components", f"{scene_stats.get('num_components', 0)}")
                s2.metric("Total Oil Pixels", f"{scene_stats.get('total_oil_pixels', 0):,}")
                
                oil_frac = scene_stats.get("total_oil_fraction")
                s3.metric("Total Oil Fraction", f"{oil_frac:.6f}" if isinstance(oil_frac, (int, float)) else "N/A")
                
                largest_frac = scene_stats.get("largest_component_fraction")
                s4.metric("Largest Slick Fraction", f"{largest_frac:.4f}" if isinstance(largest_frac, (int, float)) else "N/A")
                
                frag_idx = scene_stats.get("fragmentation_index_per_pixel")
                s5.metric("Fragmentation / Pixel", f"{frag_idx:.6f}" if isinstance(frag_idx, (int, float)) else "N/A")
                
                comps_10k = scene_stats.get("components_per_10000_oil_pixels")
                s6.metric("Components / 10k Pixels", f"{comps_10k:.2f}" if isinstance(comps_10k, (int, float)) else "N/A")
                
                st.caption("Note: Fragmentation descriptors are normalized image-space metrics dependent on pixel resolution, binarization threshold, and minimum component size filter settings.")

                # Contour Overlay Renderer
                overlay_path = res_d.get("contour_overlay_path")
                if overlay_path:
                    over_filename = os.path.basename(overlay_path)
                    st.markdown("### Slick Boundary Contour Overlay")
                    st.image(f"{API_URL}/cases/{case_id}/outputs/{over_filename}", caption="Slick Contours (Green) & Centroids (Red)", use_container_width=True)

                # Component Detail Table
                components_list = res_d.get("components") or []
                if components_list:
                    st.markdown(f"### Detected Slick Components ({len(components_list)})")
                    with st.expander("Show Component Morphological Metrics Table"):
                        st.json(components_list)

                # GeoJSON Output Viewer / Download
                if res_d.get("geojson_path"):
                    geojson_file = os.path.basename(res_d["geojson_path"])
                    st.markdown("### GeoJSON Export")
                    st.markdown(f"- **GeoJSON Artifact:** `{res_d['geojson_path']}`")
                    st.markdown(f"- **GeoJSON SHA256:** `{res_d.get('geojson_sha256')}`")


# ----------------------------------------------------
# TAB 6: HINDCAST READINESS RUNNER
# ----------------------------------------------------
with tabs[5]:
    st.header("Met-Ocean Environmental & Hindcast Readiness Engine")
    st.caption("Pre-flight scientific validator ensuring environmental forcing data covers the spill region and requested time window.")
    
    if not selected_case:
        st.warning("Please select a case from the sidebar.")
    else:
        case_id = selected_case.get("case_id")
        case_res = api_get(f"/cases/{case_id}")
        fresh_case = case_res.json() if case_res and case_res.status_code == 200 else selected_case
        
        st.markdown("---")
        st.subheader("Hindcast Validation Settings")
        c_h1, c_h2 = st.columns(2)
        with c_h1:
            req_hours = st.number_input("Requested Hindcast Duration (hours)", min_value=1.0, max_value=168.0, value=12.0, step=1.0)
        with c_h2:
            req_waves = st.checkbox("Require Wave / Stokes Drift Forcing", value=False)

        if st.button("🚀 Check Hindcast Readiness", type="primary"):
            payload = {
                "hindcast_hours": req_hours,
                "require_waves": req_waves,
            }
            with st.spinner("Validating environmental spatial/temporal data coverage..."):
                res = api_post(f"/cases/{case_id}/analysis/hindcast-readiness", json_data=payload)
                
            if res and res.status_code == 200:
                read_res = res.json()
                st.session_state["latest_readiness_analysis"] = read_res
                st.rerun()
            elif res:
                st.error(f"Readiness Check Failed ({res.status_code}): {res.text}")

        # Render latest readiness analysis output
        latest_read = st.session_state.get("latest_readiness_analysis")
        if latest_read and latest_read.get("case_id") == case_id:
            st.markdown("---")
            st.subheader("ENVIRONMENTAL READINESS RESULTS")
            st.markdown(f"**Analysis ID:** `{latest_read.get('analysis_id', 'N/A')}` | **Status:** `{latest_read.get('status', 'N/A')}`")
            
            res_d = latest_read.get("result") or {}
            ready_bool = res_d.get("ready_for_hindcast", False)
            reasons_list = res_d.get("reasons") or []
            warnings_list = latest_read.get("warnings") or []

            # Overall Readiness Banner
            if ready_bool:
                st.success("✅ **READY FOR HINDCAST:** Case contains georeferenced geometry and complete met-ocean forcing coverage!")
            else:
                st.warning("⚠️ **INSUFFICIENT DATA FOR HINDCAST:** Environmental observations do not satisfy pre-flight requirements.")

            # Summary Cards
            st.markdown("### Pre-Flight Requirement Summary")
            k1, k2, k3, k4, k5 = st.columns(5)
            
            is_georef = res_d.get("spill_georeferenced", False)
            k1.metric("Spill Georeferenced", "YES 🟢" if is_georef else "NO 🔴")
            
            obs_t = res_d.get("observation_time_utc")
            k2.metric("Observation Time", obs_t[:16].replace("T", " ") if obs_t else "MISSING 🔴")

            cov_dict = res_d.get("environmental_coverage") or {}
            curr_info = cov_dict.get("ocean_current") or {}
            wind_info = cov_dict.get("wind") or {}
            wave_info = cov_dict.get("wave") or {}

            k3.metric("Ocean Current", "PASS 🟢" if curr_info.get("spatial_coverage") and curr_info.get("temporal_coverage") else ("FAIL 🔴" if curr_info.get("present") else "MISSING 🔴"))
            k4.metric("Wind Data", "PASS 🟢" if wind_info.get("spatial_coverage") and wind_info.get("temporal_coverage") else ("FAIL 🔴" if wind_info.get("present") else "MISSING 🔴"))
            k5.metric("Wave Data", "PASS 🟢" if wave_info.get("spatial_coverage") and wave_info.get("temporal_coverage") else ("OPTIONAL ⚪" if not req_waves else "MISSING 🔴"))

            # Detailed Failure / Warning Reasons
            if warnings_list or reasons_list:
                st.markdown("### Missing Data & Coverage Warnings")
                for w in warnings_list:
                    st.error(f"• {w}")


# ----------------------------------------------------
# TAB 7: PROVENANCE AUDIT
# ----------------------------------------------------
with tabs[6]:
    st.header("Provenance & Audit Trail")
    if not selected_case:
        st.warning("Please select a case from the sidebar.")
    else:
        case_id = selected_case.get("case_id")
        case_name = selected_case.get("name", "Active Case")
        case_res = api_get(f"/cases/{case_id}")
        fresh_case = case_res.json() if case_res and case_res.status_code == 200 else selected_case
        gen_results = fresh_case.get("data_manifest", {}).get("generated_analysis_results", [])
        
        st.markdown(f"Provenance records for case **{case_name}** (`{case_id}`)")
        
        if not gen_results:
            st.info("No analysis provenance records recorded yet.")
        else:
            for idx, res_item in enumerate(reversed(gen_results)):
                an_id = res_item.get("analysis_id", "N/A")
                mod = res_item.get("module", "N/A")
                st_val = res_item.get("status", "N/A")
                
                with st.expander(f"🔍 Analysis Run `{an_id}` ({mod}) — {st_val}"):
                    st.markdown("#### Input Evidence Provenance")
                    st.markdown(f"- **Input Evidence IDs:** `{res_item.get('input_evidence_ids', [])}`")
                    st.markdown(f"- **Input SAR SHA256:** `{res_item.get('input_hashes', [])}`")
                    
                    st.markdown("#### Model & Module Provenance")
                    cfg = res_item.get("configuration") or {}
                    st.markdown(f"- **Module Name:** `{mod}` (v`{res_item.get('module_version', '1.0.0')}`)")
                    if mod == "oil_detection":
                        st.markdown(f"- **Checkpoint Path:** `{cfg.get('checkpoint_path', 'N/A')}`")
                        st.markdown(f"- **Checkpoint SHA256:** `{cfg.get('checkpoint_sha256') or 'Not available'}`")
                        st.markdown(f"- **Decision Threshold:** `{cfg.get('threshold', 'N/A')}`")
                    elif mod == "spill_geometry":
                        st.markdown(f"- **Source Oil Detection Analysis ID:** `{cfg.get('source_oil_detection_analysis_id')}`")
                        st.markdown(f"- **Source Binary Mask SHA256:** `{cfg.get('source_binary_mask_sha256')}`")
                        st.markdown(f"- **Min Component Size (pixels):** `{cfg.get('min_component_size_pixels')}`")
                    elif mod == "hindcast_readiness":
                        st.markdown(f"- **Requested Duration (hours):** `{cfg.get('hindcast_hours')}`")
                        st.markdown(f"- **Require Waves:** `{cfg.get('require_waves')}`")
                    
                    st.markdown("#### Execution Timestamps")
                    st.markdown(f"- **Started At:** `{res_item.get('started_at', 'N/A')}`")
                    st.markdown(f"- **Completed At:** `{res_item.get('completed_at', 'N/A')}`")
                    
                    res_d = res_item.get("result") or {}
                    if res_d:
                        st.markdown("#### Generated Results Payload")
                        st.json(res_d)


# ----------------------------------------------------
# TAB 8: SYSTEM MODULE STATUS TRACKER
# ----------------------------------------------------
with tabs[7]:
    st.header("VARUNA Module Status Tracker")
    if not selected_case:
        st.warning("Please select a case from the sidebar.")
    else:
        case_id = selected_case.get("case_id")
        case_name = selected_case.get("name", "Active Case")
        case_res = api_get(f"/cases/{case_id}")
        fresh_case = case_res.json() if case_res and case_res.status_code == 200 else selected_case
        status_dict = fresh_case.get("analysis_status", {})
        
        st.markdown(f"Module pipeline tracking for active case: **{case_name}** (`{case_id}`)")
        
        modules_info = [
            ("Oil Detection", "oil_detection", "U-Net SAR oil spill segmentation engine"),
            ("Spill Geometry", "spill_geometry", "Geospatial contouring & area polygon calculation"),
            ("Hindcast Readiness", "hindcast", "Environmental forcing coverage validator"),
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
# TAB 9: ANALYST QUESTIONS
# ----------------------------------------------------
with tabs[8]:
    st.header("Analyst Notes & Questions")
    if not selected_case:
        st.warning("Please select a case from the sidebar.")
    else:
        case_id = selected_case.get("case_id")
        case_res = api_get(f"/cases/{case_id}")
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
                res = api_post(f"/cases/{case_id}/questions", json_data=q_payload)
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
                q_text_val = q.get("question", "")
                q_author_val = q.get("asked_by") or "Anonymous"
                q_time = q.get("created_at", "N/A")
                q_id = q.get("question_id", "N/A")
                st.markdown(f"**Q:** {q_text_val}")
                st.caption(f"Asked by: `{q_author_val}` | Timestamp: `{q_time}` | ID: `{q_id}`")
                st.markdown("---")
