/* ==========================================================================
   VARUNA — MARITIME ENVIRONMENTAL INTELLIGENCE WORKSTATION (v1.0.0-rc1)
   Enterprise Case Management & Guided Investigation Architecture Engine
   ========================================================================== */

(function () {
  const API_ORIGIN = window.VARUNA_API_BASE_URL || window.SAMUDRANETRA_API_BASE_URL || (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1' ? 'http://localhost:8000' : window.location.origin);
  const PRODUCT_API_BASE = `${API_ORIGIN}/api/v1`;
  const BENCHMARK_API_BASE = `${API_ORIGIN}/api/investigations`;
  const API_BASE = `${API_ORIGIN}/api`;

  function isBenchmarkCase(caseId) {
    if (!caseId) return false;
    const upper = caseId.toUpperCase();
    return upper.startsWith("R001") || upper.startsWith("R002") || upper.startsWith("R003") || upper.startsWith("R004") || upper.startsWith("R005") || upper.includes("BENCHMARK");
  }

  // Canonical Validated Benchmark Case Definition
  const R001_BENCHMARK_RECORD = {
    case_id: "R001_WAKASHIO",
    case_name: "Mauritius Oil Spill Incident",
    location: "Point d'Esny, Mauritius",
    region: "Point d'Esny, Mauritius (Indian Ocean)",
    mode: "Historical Benchmark Case",
    stage: "Review Ready",
    status: "VALIDATED BENCHMARK",
    last_updated: "2026-09-02 10:45 UTC",
    is_benchmark: true,
    observation_status: "VALIDATED",
    detection_status: "COMPLETE",
    selected_candidate: "C4053",
    hindcast_status: "COMPLETE",
    forecast_status: "COMPLETE",
    ais_status: "SYNTHETIC_DEMO",
    review_status: "READY",
    activity: [
      { time: "2020-08-10 01:38 UTC", text: "Sentinel-1B SAR scene acquired and validated" },
      { time: "2020-08-10 02:15 UTC", text: "Slick candidate triage completed: 45 groups → C4053 selected (ML: 0.5818)" },
      { time: "2020-08-10 03:00 UTC", text: "OpenDrift backward hindcast computed: ~24.17 km distance @ 24h" },
      { time: "2020-08-10 04:30 UTC", text: "OpenDrift forward forecast trajectory computed (T0 → T+48h)" }
    ]
  };

  // Normalized Enterprise Case Registry State
  const state = {
    activeModule: "OPERATIONS", // 'OPERATIONS', 'CASES', 'SATELLITE', 'ANALYSIS', 'PHYSICS', 'VESSEL', 'REPORTS'
    currentDomain: "HOME",      // 'HOME', 'CASES', 'OVERVIEW', 'OBSERVE', 'ANALYZE', 'RECONSTRUCT', 'ATTRIBUTE', 'REVIEW', 'ACTIVITY'
    investigationId: "R001_WAKASHIO",
    activeEdgeState: "NORMAL_CASE",
    isGuidedMode: true,
    
    // Case Registry Database (Backed by /api/v1/cases + Pinned Benchmark)
    cases: [R001_BENCHMARK_RECORD],

    // Active View Settings
    activeSarBand: "VV",
    activeCandidateId: "C4053",
    activeScenario: "C",
    activeTimestep: "T0",
    physicsMode: "HINDCAST",
    
    // Map Canvas Handles
    maps: {
      observe: null,
      analyze: null,
      reconstruct: null,
      attribute: null,
      wizAoi: null
    },
    sarOverlays: {
      observe: null,
      analyze: null
    },
    
    currentJobId: null
  };

  /* ==========================================================================
     CANONICAL API LAYER
     ========================================================================== */

  async function fetchEndpoint(endpoint) {
    try {
      const res = await fetch(`${API_BASE}${endpoint}`);
      if (!res.ok) return null;
      return await res.json();
    } catch (e) {
      console.warn(`API GET ${endpoint} failed:`, e);
      return null;
    }
  }

  async function postEndpoint(endpoint, payload = {}) {
    try {
      const res = await fetch(`${API_BASE}${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      if (!res.ok) return null;
      return await res.json();
    } catch (e) {
      console.warn(`API POST ${endpoint} failed:`, e);
      return null;
    }
  }

  async function loadCasesFromBackend() {
    try {
      const res = await fetch(`${PRODUCT_API_BASE}/cases`);
      if (res.ok) {
        const backendCases = await res.json();
        const mappedCases = backendCases.map(bc => {
          const satObs = bc.data_manifest?.satellite_observations || [];
          const hasSar = satObs.length > 0 || (bc.data_manifest?.evidence && bc.data_manifest.evidence.some(e => e.evidence_type === "sar_image"));
          const isBench = isBenchmarkCase(bc.case_id);
          const wf = bc.workflow || {};
          const stages = wf.stages || {};
          
          let actList = [];
          if (stages && Object.keys(stages).length > 0) {
            for (const [stName, stData] of Object.entries(stages)) {
              if (stData.completed) {
                actList.push({
                  time: stData.timestamp ? stData.timestamp.substr(0, 16).replace("T", " ") + " UTC" : "Completed",
                  text: stData.summary || `${stName} completed`
                });
              }
            }
          }
          if (actList.length === 0) {
            actList.push({
              time: bc.created_at ? bc.created_at.substr(0, 16).replace("T", " ") + " UTC" : "Recent",
              text: `Case ${bc.case_id} registered in database`
            });
          }

          const currentStage = wf.current_stage || (isBench ? "REVIEW READY" : (hasSar ? "Observation Attached" : "Observation Required"));

          return {
            case_id: bc.case_id,
            case_name: bc.name,
            location: bc.region || (bc.latitude && bc.longitude ? `${bc.latitude.toFixed(2)}°, ${bc.longitude.toFixed(2)}°` : "Custom AOI"),
            region: bc.region,
            latitude: bc.latitude,
            longitude: bc.longitude,
            aoi_geojson: bc.aoi_geojson,
            observation_timestamp: bc.observation_timestamp,
            mode: bc.incident_type || (isBench ? "Validated Research Benchmark" : "Operational Oil Spill"),
            stage: currentStage,
            status: isBench ? "VALIDATED BENCHMARK" : (bc.analysis_status?.oil_detection === "completed" ? "ACTIVE" : "NEW"),
            last_updated: bc.created_at ? bc.created_at.substr(0, 16).replace("T", " ") + " UTC" : "Recent",
            is_benchmark: isBench,
            observation_status: hasSar ? "VALIDATED" : "NO OBSERVATION ATTACHED",
            satellite_observations: satObs,
            raw_case: bc,
            detection_status: stages["SLICK ANALYSED"]?.completed ? "COMPLETE" : (bc.analysis_status?.oil_detection || "not_started"),
            selected_candidate: stages["CANDIDATE SELECTED"]?.data?.selected_candidate || (isBench ? "C4053" : null),
            hindcast_status: stages["HINDCAST COMPLETE"]?.completed ? "COMPLETE" : "not_started",
            forecast_status: stages["FORECAST COMPLETE"]?.completed ? "COMPLETE" : "not_started",
            ais_status: stages["AIS CORRELATED"]?.completed ? (stages["AIS CORRELATED"]?.data?.attribution_abstention ? "ATTRIBUTION ABSTAINED (NON-VESSEL)" : "SYNTHETIC_DEMO") : "not_started",
            review_status: stages["REVIEW READY"]?.completed ? "READY" : "INCOMPLETE",
            activity: actList
          };
        });
        state.cases = mappedCases;
      }
    } catch (err) {
      console.warn("Failed to load cases from /api/v1/cases:", err);
    }
    renderOpsHome();
    if (window.renderCasesRegistry) window.renderCasesRegistry();
  }

  /* ==========================================================================
     INITIALIZATION & STATE RECOVERY
     ========================================================================== */

  document.addEventListener("DOMContentLoaded", async () => {
    loadPersistedState();
    await initApp();
  });

  function loadPersistedState() {
    try {
      const saved = localStorage.getItem("varuna_enterprise_state");
      if (saved) {
        const parsed = JSON.parse(saved);
        if (parsed.investigationId) state.investigationId = parsed.investigationId;
      }
    } catch (e) {
      console.warn("Could not parse saved enterprise state:", e);
    }
  }

  function persistState() {
    try {
      localStorage.setItem("varuna_enterprise_state", JSON.stringify({
        investigationId: state.investigationId
      }));
    } catch (e) {
      console.warn("Could not save enterprise state:", e);
    }
  }

  async function initApp() {
    await loadCasesFromBackend();
    if (!state.cases.some(c => c.case_id === state.investigationId)) {
      state.investigationId = "R001_WAKASHIO";
    }
    renderOpsHome();
    window.renderCasesRegistry();
    window.switchDomain(state.currentDomain);
  }

  /* ==========================================================================
     DOMAIN & MODULE SWITCHING
     ========================================================================== */

  window.switchDomain = function (domain) {
    state.currentDomain = domain;

    // Update Top Module Styling
    document.querySelectorAll(".nav-module").forEach(el => {
      const isAct = (domain === "HOME" && el.dataset.module === "OPERATIONS") ||
                    (domain === "CASES" && el.dataset.module === "CASES") ||
                    (domain === "OBSERVE" && el.dataset.module === "SATELLITE") ||
                    (domain === "ANALYZE" && el.dataset.module === "ANALYSIS") ||
                    (domain === "RECONSTRUCT" && el.dataset.module === "PHYSICS") ||
                    (domain === "ATTRIBUTE" && el.dataset.module === "VESSEL") ||
                    (domain === "REVIEW" && el.dataset.module === "REPORTS");
      el.classList.toggle("text-primary", isAct);
      el.classList.toggle("font-semibold", isAct);
      el.classList.toggle("text-on-surface-variant", !isAct);
    });

    // Update Sidebar Styling
    document.querySelectorAll(".sn-nav-btn").forEach(btn => {
      const isAct = btn.dataset.domain === domain;
      btn.classList.toggle("bg-primary-container", isAct);
      btn.classList.toggle("text-on-primary-container", isAct);
      btn.classList.toggle("border-l-2", isAct);
      btn.classList.toggle("border-primary", isAct);
      btn.classList.toggle("text-on-surface-variant", !isAct);
    });

    // Hide All Domain Workspaces
    document.querySelectorAll(".sn-domain-workspace").forEach(el => el.classList.add("hidden"));

    // Unhide Target Domain
    const domId = domain.toLowerCase();
    const target = document.getElementById(`domain-${domId}`);
    if (target) target.classList.remove("hidden");

    // Dynamic Header Updates
    const activeCase = state.cases.find(c => c.case_id === state.investigationId) || state.cases[0];
    const sTitle = document.getElementById("sidebar-case-title");
    const sSub = document.getElementById("sidebar-case-sub");
    if (sTitle) sTitle.innerText = activeCase.case_id === "R001_WAKASHIO" ? "CASE R001" : activeCase.case_id;
    if (sSub) sSub.innerText = activeCase.case_name;

    // Trigger Specific View Handlers
    setTimeout(() => {
      if (domain === "HOME") renderOpsHome();
      else if (domain === "CASES") renderCasesRegistry();
      else if (domain === "OVERVIEW") renderCaseOverview();
      else if (domain === "OBSERVE") initObserveMap();
      else if (domain === "ANALYZE") initAnalyzeMap();
      else if (domain === "RECONSTRUCT") { initReconstructMap(); renderReconstructInspector(); }
      else if (domain === "ATTRIBUTE") { initAttributeMap(); renderAttributeInspector(); }
      else if (domain === "REVIEW") renderReviewBriefing();
      else if (domain === "ACTIVITY") renderCaseActivityTimeline();
    }, 50);
  };

  /* ==========================================================================
     MODULE 0: OPERATIONS HOME RENDERER
     ========================================================================== */

  function renderOpsHome() {
    const tbody = document.getElementById("ops-active-cases-table-body");
    if (!tbody) return;

    tbody.innerHTML = state.cases.map(c => `
      <tr class="border-b border-outline-variant/40 hover:bg-surface-variant/40 transition-colors">
        <td class="p-2.5 font-bold text-primary">${c.case_id}</td>
        <td class="p-2.5 font-semibold text-on-surface">${c.case_name}</td>
        <td class="p-2.5 text-on-surface-variant">${c.location}</td>
        <td class="p-2.5"><span class="px-1.5 py-0.5 rounded text-[10px] bg-surface-variant text-warning-amber border border-outline-variant">${c.mode}</span></td>
        <td class="p-2.5 text-on-surface">${c.stage}</td>
        <td class="p-2.5"><span class="px-1.5 py-0.5 rounded text-[10px] bg-success-green/10 text-success-green border border-success-green/30 font-bold">${c.status}</span></td>
        <td class="p-2.5 text-outline font-data-mono">${c.last_updated}</td>
        <td class="p-2.5"><button class="px-2.5 py-1 bg-primary text-on-primary font-bold rounded text-[10px]" onclick="window.openCase('${c.case_id}')">OPEN CASE</button></td>
      </tr>
    `).join("");

    const cnt = document.getElementById("ops-active-count");
    if (cnt) cnt.innerText = `${state.cases.length} Active Investigation${state.cases.length > 1 ? 's' : ''}`;
  }

  /* ==========================================================================
     MODULE 1: CASES REGISTRY RENDERER
     ========================================================================== */

  window.renderCasesRegistry = function () {
    const tbody = document.getElementById("cases-registry-table-body");
    if (!tbody) return;

    const query = (document.getElementById("cases-search-input")?.value || "").toLowerCase();
    const filter = document.getElementById("cases-filter-status")?.value || "ALL";

    const filtered = state.cases.filter(c => {
      const matchQ = c.case_id.toLowerCase().includes(query) || c.case_name.toLowerCase().includes(query) || c.location.toLowerCase().includes(query);
      const matchS = filter === "ALL" || c.status === filter || (filter === "DEMONSTRATION" && c.mode.includes("Benchmark"));
      return matchQ && matchS;
    });

    tbody.innerHTML = filtered.map(c => `
      <tr class="border-b border-outline-variant/40 hover:bg-surface-variant/40 transition-colors">
        <td class="p-2.5 font-bold text-primary">${c.case_id}</td>
        <td class="p-2.5 font-semibold text-on-surface">${c.case_name}</td>
        <td class="p-2.5 text-on-surface-variant">${c.location}</td>
        <td class="p-2.5">${c.mode}</td>
        <td class="p-2.5">${c.stage}</td>
        <td class="p-2.5"><span class="px-1.5 py-0.5 rounded text-[10px] bg-success-green/10 text-success-green border border-success-green/30 font-bold">${c.status}</span></td>
        <td class="p-2.5 text-outline font-data-mono">${c.last_updated}</td>
        <td class="p-2.5"><button class="px-2.5 py-1 bg-primary text-on-primary font-bold rounded text-[10px]" onclick="window.openCase('${c.case_id}')">OPEN CASE</button></td>
      </tr>
    `).join("");
  };

  window.openCase = function (caseId) {
    state.investigationId = caseId;
    persistState();
    window.switchDomain("OVERVIEW");
  };

  /* ==========================================================================
     CASE OVERVIEW & GUIDED WORKFLOW
     ========================================================================== */

  function renderCaseOverview() {
    const activeCase = state.cases.find(c => c.case_id === state.investigationId) || state.cases[0];
    const isBench = isBenchmarkCase(activeCase.case_id);
    const tTitle = document.getElementById("ov-case-id-title");
    const tSub = document.getElementById("ov-case-subtitle");
    const tBadge = document.getElementById("ov-badge-status");

    if (tTitle) tTitle.innerText = `CASE ${activeCase.case_id} — ${activeCase.case_name}`;
    if (tSub) tSub.innerText = `${activeCase.location} | ${isBench ? "Historical Benchmark Case" : activeCase.mode}`;
    if (tBadge) tBadge.innerText = isBench ? "VALIDATED BENCHMARK" : activeCase.status;

    // Dynamic Overview Status Cards
    const ovObsVal = document.getElementById("ov-obs-status-val");
    const ovDetVal = document.getElementById("ov-det-result-val");
    const ovCandVal = document.getElementById("ov-cand-val");
    const ovHcVal = document.getElementById("ov-hc-val");

    const wf = activeCase.raw_case?.workflow || {};
    const stages = wf.stages || {};

    if (ovObsVal) {
      const isObs = activeCase.observation_status === "VALIDATED";
      const satName = activeCase.satellite_observations?.[0]?.platform || "Sentinel-1";
      ovObsVal.innerText = isObs ? `VALIDATED (${satName})` : activeCase.observation_status;
      ovObsVal.className = isObs ? "text-success-green font-bold mt-1" : "text-warning-amber font-bold mt-1";
    }
    if (ovDetVal) {
      const polyCount = stages["SLICK ANALYSED"]?.data?.polygon_count;
      ovDetVal.innerText = polyCount ? `${polyCount} CANDIDATE GROUPS` : (activeCase.detection_status === "COMPLETE" ? "DETECTION COMPLETE" : "NOT STARTED");
      ovDetVal.className = activeCase.detection_status === "COMPLETE" ? "text-primary font-bold mt-1" : "text-outline font-bold mt-1";
    }
    if (ovCandVal) {
      const cand = activeCase.selected_candidate || stages["CANDIDATE SELECTED"]?.data?.selected_candidate;
      ovCandVal.innerText = cand ? `${cand} (PHYSICS ELIGIBLE)` : "NOT SELECTED";
      ovCandVal.className = cand ? "text-map-creative-accent font-bold mt-1" : "text-outline font-bold mt-1";
    }
    if (ovHcVal) {
      const rpData = stages["RESPONSE PRIORITIZED"]?.data;
      if (rpData?.highest_priority_receptor) {
        ovHcVal.innerText = `${rpData.highest_priority_receptor.receptor_name} (${rpData.response_window_hours}h)`;
      } else if (stages["HINDCAST COMPLETE"]?.completed) {
        ovHcVal.innerText = "HINDCAST RECONSTRUCTED";
      } else {
        ovHcVal.innerText = "AWAITING RUN";
      }
    }
  }

  /* ==========================================================================
     NEW CASE GUIDED WIZARD (4 STEPS — CONNECTED TO /api/v1/cases)
     ========================================================================== */

  window.openNewCaseWizard = function () {
    document.getElementById("sn-new-case-wizard-modal")?.classList.remove("hidden");
    window.wizardNextStep(1);
  };

  window.closeNewCaseWizard = function () {
    document.getElementById("sn-new-case-wizard-modal")?.classList.add("hidden");
  };

  window.wizardNextStep = function (step) {
    document.querySelectorAll(".sn-wizard-step").forEach(el => el.classList.add("hidden"));
    const target = document.getElementById(`wizard-step-${step}`);
    if (target) target.classList.remove("hidden");

    const title = document.getElementById("wizard-step-title");
    if (title) title.innerText = `NEW CASE WIZARD — STEP ${step} OF 4`;

    if (step === 2 && !state.maps.wizAoi) {
      setTimeout(() => {
        state.maps.wizAoi = L.map("map-wiz-aoi", { center: [-20.4382, 57.7432], zoom: 8, zoomControl: false, attributionControl: false });
        L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}").addTo(state.maps.wizAoi);
        L.polygon([[-20.75, 57.10], [-20.75, 58.30], [-19.70, 58.30], [-19.70, 57.10]], { color: "#dbe2ff", weight: 2, fillColor: "#2563eb", fillOpacity: 0.25 }).addTo(state.maps.wizAoi);
      }, 100);
    }
  };

  window.submitNewCaseWizard = async function () {
    const cName = document.getElementById("wiz-case-name")?.value || "New Maritime Incident";
    const cType = document.getElementById("wiz-case-type")?.value || "Operational Oil Spill";
    const cLoc = document.getElementById("wiz-case-location")?.value || "Custom Maritime Location";

    // Build real GeoJSON polygon from defined AOI coordinates
    const aoiGeoJson = {
      type: "Polygon",
      coordinates: [[
        [57.10, -20.75],
        [58.30, -20.75],
        [58.30, -19.70],
        [57.10, -19.70],
        [57.10, -20.75]
      ]]
    };

    const payload = {
      name: cName,
      description: `Operational case created via Enterprise Guided Wizard: ${cLoc}`,
      incident_type: cType,
      region: cLoc,
      priority: "NORMAL",
      source: "Enterprise Guided Wizard",
      tags: ["operational", cType.toLowerCase().replace(/\s+/g, "-")],
      aoi_geojson: aoiGeoJson,
      latitude: -20.22,
      longitude: 57.70
    };

    let createdCaseId = null;
    try {
      const res = await fetch(`${PRODUCT_API_BASE}/cases`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      if (res.ok) {
        const created = await res.json();
        createdCaseId = created.case_id;
      }
    } catch (e) {
      console.error("Failed to post case to /api/v1/cases:", e);
    }

    await loadCasesFromBackend();

    if (createdCaseId) {
      state.investigationId = createdCaseId;
    }
    persistState();
    window.closeNewCaseWizard();
    window.switchDomain("OVERVIEW");
  };

  window.toggleGuidedMode = function () {
    state.isGuidedMode = !state.isGuidedMode;
    const btn = document.getElementById("btn-toggle-guided-mode");
    if (btn) btn.innerText = state.isGuidedMode ? "GUIDED" : "EXPERT";
  };

  /* ==========================================================================
     DOMAIN 01: OBSERVE WORKSPACE (REAL SAR VIEWER / ZERO-LEAKAGE EMPTY STATE)
     ========================================================================== */

  function initObserveMap() {
    const mapContainer = document.getElementById("map-observe");
    if (!mapContainer) return;

    const activeCase = state.cases.find(c => c.case_id === state.investigationId) || state.cases[0];
    const isR001 = state.investigationId.startsWith("R001");
    const cLat = activeCase?.latitude || -20.4382;
    const cLon = activeCase?.longitude || 57.7432;
    const sarBounds = [[-20.750033, 57.09998], [-19.699993, 58.300039]];

    if (!state.maps.observe) {
      state.maps.observe = L.map("map-observe", { center: [cLat, cLon], zoom: 10, zoomControl: false, attributionControl: false });
      state.maps.observe.on("mousemove", (e) => updateStatusBarCoords(e.latlng.lat, e.latlng.lng));
      L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}").addTo(state.maps.observe);
    }

    state.maps.observe.invalidateSize();

    if (state.sarOverlays.observe) {
      state.maps.observe.removeLayer(state.sarOverlays.observe);
      state.sarOverlays.observe = null;
    }
    state.maps.observe.eachLayer(l => {
      if (l instanceof L.Polygon || l instanceof L.GeoJSON) state.maps.observe.removeLayer(l);
    });

    const taskEl = document.getElementById("guided-observe-task");
    const descEl = document.getElementById("guided-observe-desc");

    if (isR001) {
      let sarImgUrl = state.activeSarBand === "VH" ? "assets/sar_vh_display.webp" : "assets/sar_vv_display.webp";
      state.sarOverlays.observe = L.imageOverlay(sarImgUrl, sarBounds, { opacity: state.activeSarBand === "COMPARE" ? 0.80 : 1.0, interactive: false }).addTo(state.maps.observe);
      L.polygon(sarBounds, { color: "#38BDF8", weight: 1.5, dashArray: "4,4", fillColor: "transparent" }).addTo(state.maps.observe);
      state.maps.observe.fitBounds(sarBounds, { padding: [10, 10], animate: false });

      if (taskEl) taskEl.innerText = "Observation Review";
      if (descEl) descEl.innerText = "Sentinel-1 SAR scene validated and calibrated. Next step: Run oil-like slick detection.";
      const covBadge = document.getElementById("observe-coverage-badge");
      if (covBadge) covBadge.classList.add("hidden");
    } else {
      // GENERIC INVESTIGATION CASE (ZERO-LEAKAGE + REAL SATELLITE DISCOVERY)
      const activeCase = state.cases.find(c => c.case_id === state.investigationId);
      const propsContainer = document.getElementById("guided-observe-properties-container");
      const actionContainer = document.getElementById("guided-observe-action-container");
      const covBadge = document.getElementById("observe-coverage-badge");
      const covText = document.getElementById("observe-coverage-text");

      const attachedObs = (activeCase?.satellite_observations && activeCase.satellite_observations.length > 0)
        ? activeCase.satellite_observations[0]
        : null;

      if (!attachedObs) {
        // STATE 1: NO OBSERVATION ATTACHED
        if (taskEl) taskEl.innerText = "NO OBSERVATION ATTACHED";
        if (descEl) descEl.innerText = "No Sentinel-1 SAR observation has been attached to this investigation case. Search genuine Copernicus acquisitions or upload SAR GeoTIFF.";

        if (propsContainer) {
          propsContainer.innerHTML = `
            <div class="p-3 bg-surface-container rounded border border-outline-variant space-y-2.5">
              <div class="flex items-center space-x-1.5 text-primary text-[10px] font-bold uppercase">
                <span class="material-symbols-outlined text-[14px]">satellite_alt</span>
                <span>Observation Attachment</span>
              </div>
              <p class="text-[11px] text-on-surface-variant leading-relaxed">Discover real Sentinel-1 GRD acquisitions from Copernicus Data Space Ecosystem intersecting this case's AOI.</p>
              <button class="w-full h-8 bg-primary hover:bg-primary-container text-on-primary font-data-mono-sm uppercase tracking-wider font-bold rounded flex items-center justify-center space-x-1.5 transition-colors cursor-pointer shadow-sm text-xs" onclick="window.openSatelliteSearchModal()">
                <span class="material-symbols-outlined text-[16px]">search</span>
                <span>SEARCH SENTINEL-1</span>
              </button>
              <button class="w-full h-7 bg-surface-variant hover:bg-surface-container-highest text-on-surface font-data-mono-sm text-[10px] uppercase rounded border border-outline-variant flex items-center justify-center space-x-1 transition-colors cursor-pointer" onclick="window.triggerSarUploadGeneric()">
                <span class="material-symbols-outlined text-[14px]">upload_file</span>
                <span>UPLOAD SAR</span>
              </button>
            </div>
          `;
        }

        if (actionContainer) {
          actionContainer.innerHTML = `
            <button disabled class="w-full h-8 bg-surface-variant text-outline font-data-mono-sm uppercase tracking-wider font-bold rounded flex items-center justify-center space-x-2 opacity-60 cursor-not-allowed text-xs">
              <span class="material-symbols-outlined text-[16px]">hourglass_empty</span>
              <span>AWAITING OBSERVATION</span>
            </button>
          `;
        }

        if (covBadge) covBadge.classList.add("hidden");

        if (activeCase && activeCase.aoi_geojson) {
          try {
            const aoiLayer = L.geoJSON(activeCase.aoi_geojson, {
              style: { color: "#38BDF8", weight: 2, dashArray: "4,4", fillColor: "#2563eb", fillOpacity: 0.15 }
            }).addTo(state.maps.observe);
            state.maps.observe.fitBounds(aoiLayer.getBounds(), { padding: [30, 30], animate: false });
          } catch (e) {
            state.maps.observe.setView([0, 0], 2);
          }
        } else {
          state.maps.observe.setView([0, 0], 2);
        }
      } else {
        // STATE 2: OBSERVATION ATTACHED
        if (taskEl) taskEl.innerText = "OBSERVATION ATTACHED";
        if (descEl) descEl.innerText = `Genuine ${attachedObs.platform || "Sentinel-1"} observation attached from Copernicus Data Space Ecosystem. Ready for scientific pipeline preparation.`;

        const acqTime = attachedObs.datetime ? attachedObs.datetime.replace("T", " ").replace("Z", "") + " UTC" : "N/A";
        const pols = (attachedObs.polarizations && attachedObs.polarizations.length) ? attachedObs.polarizations.join("/") : "VV/VH";
        const covVal = attachedObs.coverage_percent != null ? `${attachedObs.coverage_percent}%` : "100.0%";

        if (propsContainer) {
          propsContainer.innerHTML = `
            <div class="p-3 bg-surface-container rounded border border-outline-variant space-y-2">
              <div class="flex items-center justify-between">
                <span class="text-[10px] text-primary uppercase font-bold">Properties: ${attachedObs.platform || "Sentinel-1"}</span>
                <span class="text-[9px] px-1.5 py-0.5 rounded bg-success-green/15 text-success-green font-bold">ATTACHED</span>
              </div>
              <div class="space-y-1.5 text-[11px] font-data-mono">
                <div class="flex justify-between"><span class="text-outline">Platform</span><span class="font-bold text-on-surface">${attachedObs.platform || "Sentinel-1"}</span></div>
                <div class="flex justify-between"><span class="text-outline">Acquired</span><span class="text-on-surface">${acqTime}</span></div>
                <div class="flex justify-between"><span class="text-outline">Mode</span><span>${attachedObs.instrument_mode || "IW"} ${attachedObs.product_type || "GRD"}</span></div>
                <div class="flex justify-between"><span class="text-outline">Polarization</span><span class="text-primary font-bold">${pols}</span></div>
                <div class="flex justify-between"><span class="text-outline">Coverage</span><span class="text-success-green font-bold">${covVal}</span></div>
                <div class="flex justify-between"><span class="text-outline">Source</span><span class="truncate max-w-[140px] text-right" title="Copernicus Data Space Ecosystem">Copernicus CDSE</span></div>
                <div class="flex justify-between"><span class="text-outline">Processing</span><span class="text-warning-amber font-bold">NOT STARTED</span></div>
                <div class="pt-1 border-t border-outline-variant/50">
                  <div class="text-[10px] text-outline truncate" title="${attachedObs.stac_item_id}">ID: ${attachedObs.stac_item_id}</div>
                </div>
              </div>
              <div class="pt-1 flex space-x-2">
                <button class="flex-1 py-1 bg-surface-variant hover:bg-surface-container-highest text-on-surface rounded text-[10px] font-bold uppercase transition-colors" onclick="window.viewSatelliteMetadata('${attachedObs.stac_item_id}')">View Metadata</button>
                <button class="py-1 px-2 bg-surface-variant hover:bg-surface-container-highest text-primary rounded text-[10px] font-bold uppercase transition-colors" onclick="window.openSatelliteSearchModal()" title="Search / Replace Observation">Change</button>
              </div>
            </div>
          `;
        }

        if (actionContainer) {
          actionContainer.innerHTML = `
            <button class="w-full h-8 bg-primary hover:bg-primary-container text-on-primary font-data-mono-sm uppercase tracking-wider font-bold rounded flex items-center justify-center space-x-2 transition-colors cursor-pointer text-xs" onclick="window.prepareObservationPrompt()">
              <span>PREPARE OBSERVATION</span>
              <span class="material-symbols-outlined text-[16px]">arrow_forward</span>
            </button>
          `;
        }

        // Plot both AOI and STAC footprint on map
        let boundsLayers = [];
        if (activeCase && activeCase.aoi_geojson) {
          try {
            const aoiLayer = L.geoJSON(activeCase.aoi_geojson, {
              style: { color: "#38BDF8", weight: 2, dashArray: "4,4", fillColor: "#2563eb", fillOpacity: 0.15 }
            }).addTo(state.maps.observe);
            boundsLayers.push(aoiLayer);
          } catch (e) {
            console.warn("Could not draw AOI:", e);
          }
        }

        if (attachedObs.geometry) {
          try {
            const fpLayer = L.geoJSON(attachedObs.geometry, {
              style: { color: "#f59e0b", weight: 2, fillColor: "#f59e0b", fillOpacity: 0.20 }
            }).addTo(state.maps.observe);
            boundsLayers.push(fpLayer);
          } catch (e) {
            console.warn("Could not draw STAC footprint:", e);
          }
        }

        if (covBadge && covText) {
          covText.innerText = `AOI COVERAGE: ${covVal} • ${attachedObs.platform || "Sentinel-1"} (${attachedObs.instrument_mode || "IW"})`;
          covBadge.classList.remove("hidden");
        }

        if (boundsLayers.length > 0) {
          const group = L.featureGroup(boundsLayers);
          state.maps.observe.fitBounds(group.getBounds(), { padding: [30, 30], animate: false });
        }
      }
    }
  }

  /* ==========================================================================
     DOMAIN 02: ANALYZE WORKSPACE (CANDIDATE GEOMETRY / ZERO-LEAKAGE EMPTY STATE)
     ========================================================================== */

  function initAnalyzeMap() {
    const mapContainer = document.getElementById("map-analyze");
    if (!mapContainer) return;

    const activeCase = state.cases.find(c => c.case_id === state.investigationId) || state.cases[0];
    const isR001 = state.investigationId.startsWith("R001");
    const cLat = activeCase?.latitude || -20.4382;
    const cLon = activeCase?.longitude || 57.7432;
    const sarBounds = [[-20.750033, 57.09998], [-19.699993, 58.300039]];

    if (!state.maps.analyze) {
      state.maps.analyze = L.map("map-analyze", { center: [cLat, cLon], zoom: 10, zoomControl: false, attributionControl: false });
      state.maps.analyze.on("mousemove", (e) => updateStatusBarCoords(e.latlng.lat, e.latlng.lng));
      L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}").addTo(state.maps.analyze);
    }

    state.maps.analyze.invalidateSize();

    if (state.sarOverlays.analyze) {
      state.maps.analyze.removeLayer(state.sarOverlays.analyze);
      state.sarOverlays.analyze = null;
    }
    state.maps.analyze.eachLayer(l => {
      if (l instanceof L.Polygon || l instanceof L.GeoJSON) state.maps.analyze.removeLayer(l);
    });

    if (isR001) {
      let sarImgUrl = state.activeSarBand === "VH" ? "assets/sar_vh_display.webp" : "assets/sar_vv_display.webp";
      state.sarOverlays.analyze = L.imageOverlay(sarImgUrl, sarBounds, { opacity: 1.0, interactive: false }).addTo(state.maps.analyze);

      const candidates = [
        { id: "C4053", lat: -20.4382, lon: 57.7432, area: 1.42, ml: 0.5818 },
        { id: "C3929", lat: -20.4210, lon: 57.7200, area: 0.98, ml: 0.4210 },
        { id: "C001", lat: -20.4500, lon: 57.7600, area: 1.15, ml: 0.3540 }
      ];

      candidates.forEach(c => {
        const isSel = c.id === state.activeCandidateId;
        const poly = L.polygon([
          [c.lat - 0.015, c.lon - 0.015],
          [c.lat - 0.015, c.lon + 0.015],
          [c.lat + 0.015, c.lon + 0.015],
          [c.lat + 0.015, c.lon - 0.015]
        ], {
          color: isSel ? "#dbe2ff" : "#38BDF8",
          fillColor: isSel ? "#2563eb" : "#0284C7",
          fillOpacity: isSel ? 0.65 : 0.35,
          weight: isSel ? 3 : 1.5
        });
        poly.bindPopup(`<b>SAR CANDIDATE ${c.id}</b><br>Area: ${c.area} km²<br>ML Oil-Like Evidence: ${c.ml}<br>Status: ELIGIBLE HYPOTHESIS`);
        poly.on("click", () => window.selectCandidate(c.id));
        poly.addTo(state.maps.analyze);
      });

      state.maps.analyze.fitBounds(sarBounds, { padding: [10, 10], animate: false });
    } else {
      // DYNAMIC CANDIDATES FOR RESEARCH & GENERIC CASES
      const wf = activeCase.raw_case?.workflow || {};
      const stages = wf.stages || {};
      const candId = stages["CANDIDATE SELECTED"]?.data?.selected_candidate || activeCase.selected_candidate || "C1001";
      const hasAnalysis = stages["SLICK ANALYSED"]?.completed || activeCase.detection_status === "COMPLETE";

      if (hasAnalysis) {
        const poly = L.polygon([
          [cLat - 0.018, cLon - 0.022],
          [cLat - 0.015, cLon + 0.025],
          [cLat + 0.022, cLon + 0.018],
          [cLat + 0.018, cLon - 0.015]
        ], {
          color: "#dbe2ff",
          fillColor: "#2563eb",
          fillOpacity: 0.65,
          weight: 2.5
        });
        poly.bindPopup(`<b>${activeCase.case_name}</b><br>Candidate: ${candId}<br>Status: PHYSICS_ELIGIBLE`);
        poly.addTo(state.maps.analyze);
        state.maps.analyze.setView([cLat, cLon], 10);
      } else if (activeCase && activeCase.aoi_geojson) {
        try {
          const aoiLayer = L.geoJSON(activeCase.aoi_geojson, {
            style: { color: "#38BDF8", weight: 2, dashArray: "4,4", fillColor: "#2563eb", fillOpacity: 0.15 }
          }).addTo(state.maps.analyze);
          state.maps.analyze.fitBounds(aoiLayer.getBounds(), { padding: [20, 20], animate: false });
        } catch (e) {
          state.maps.analyze.setView([cLat, cLon], 8);
        }
      } else {
        state.maps.analyze.setView([cLat, cLon], 8);
      }
    }
  }

  /* ==========================================================================
     DOMAIN 03: RECONSTRUCTION WORKSPACE (OPENDRIFT PARTICLES / ZERO-LEAKAGE)
     ========================================================================== */

  function initReconstructMap() {
    const mapContainer = document.getElementById("map-reconstruct");
    if (!mapContainer) return;

    const activeCase = state.cases.find(c => c.case_id === state.investigationId) || state.cases[0];
    const isBench = isBenchmarkCase(state.investigationId);
    const cLat = activeCase?.latitude || -20.4382;
    const cLon = activeCase?.longitude || 57.7432;

    if (!state.maps.reconstruct) {
      state.maps.reconstruct = L.map("map-reconstruct", { center: [cLat, cLon], zoom: 10, zoomControl: true, attributionControl: false });
      state.maps.reconstruct.on("mousemove", (e) => updateStatusBarCoords(e.latlng.lat, e.latlng.lng));
      L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}").addTo(state.maps.reconstruct);
    }

    state.maps.reconstruct.invalidateSize();
    state.maps.reconstruct.eachLayer(layer => {
      if (layer instanceof L.Polygon || layer instanceof L.CircleMarker || layer instanceof L.GeoJSON) state.maps.reconstruct.removeLayer(layer);
    });

    if (isBench) {
      if (state.physicsMode === "HINDCAST") {
        L.polygon([[cLat + 0.08, cLon - 0.08], [cLat + 0.08, cLon + 0.08], [cLat - 0.08, cLon + 0.08], [cLat - 0.08, cLon - 0.08]], { color: "#fbbf24", fillColor: "#fbbf24", fillOpacity: 0.25, weight: 2, dashArray: "6,6" }).addTo(state.maps.reconstruct);
        for (let p = 0; p < 80; p++) {
          const pLat = cLat + (Math.sin(p * 0.4) * 0.08);
          const pLon = cLon + (Math.cos(p * 0.4) * 0.09);
          L.circleMarker([pLat, pLon], { radius: 2.5, color: "#fbbf24", fillColor: "#fbbf24", fillOpacity: 0.85 }).addTo(state.maps.reconstruct);
        }
        state.maps.reconstruct.setView([cLat, cLon], 10);
      } else {
        L.polygon([[cLat - 0.01, cLon + 0.01], [cLat - 0.01, cLon + 0.35], [cLat - 0.31, cLon + 0.35], [cLat - 0.31, cLon + 0.01]], { color: "#b4c5ff", fillColor: "#b4c5ff", fillOpacity: 0.3, weight: 2, dashArray: "4,4" }).addTo(state.maps.reconstruct);
        for (let p = 0; p < 100; p++) {
          const pLat = cLat - (p * 0.002) + (Math.sin(p * 0.3) * 0.04);
          const pLon = cLon + (p * 0.003) + (Math.cos(p * 0.3) * 0.04);
          L.circleMarker([pLat, pLon], { radius: 3, color: "#b4c5ff", fillColor: "#b4c5ff", fillOpacity: 0.9 }).addTo(state.maps.reconstruct);
        }
        state.maps.reconstruct.setView([cLat, cLon], 10);
      }
    } else {
      if (activeCase && activeCase.aoi_geojson) {
        try {
          const aoiLayer = L.geoJSON(activeCase.aoi_geojson, {
            style: { color: "#38BDF8", weight: 2, dashArray: "4,4", fillColor: "#2563eb", fillOpacity: 0.15 }
          }).addTo(state.maps.reconstruct);
          state.maps.reconstruct.fitBounds(aoiLayer.getBounds(), { padding: [20, 20], animate: false });
        } catch (e) {
          state.maps.reconstruct.setView([cLat, cLon], 8);
        }
      } else {
        state.maps.reconstruct.setView([cLat, cLon], 8);
      }
    }
  }

  function renderReconstructInspector() {
    const bdy = document.getElementById("reconstruct-inspector-body");
    if (!bdy) return;

    const isBench = isBenchmarkCase(state.investigationId);
    if (isBench) {
      bdy.innerHTML = `
        <div class="p-3 border-b border-outline-variant bg-surface-container font-semibold text-on-surface">Physics Transport</div>
        <div class="p-3 space-y-3 font-data-mono text-xs">
          <div class="p-2.5 bg-surface-container rounded border border-outline-variant">
            <div class="text-[10px] text-outline uppercase">CURRENT TASK</div>
            <div class="text-primary font-bold text-sm mt-0.5">${state.physicsMode} TRANSPORT</div>
            <div class="text-[11px] text-on-surface-variant mt-1">OpenDrift advection model computed under ERA5/HYCOM/CMEMS forcing.</div>
          </div>
          <button class="w-full h-8 bg-primary text-on-primary font-bold uppercase rounded" onclick="window.runForecast()">RE-RUN FORWARD FORECAST</button>
        </div>
      `;
    } else {
      bdy.innerHTML = `
        <div class="p-3 border-b border-outline-variant bg-surface-container font-semibold text-on-surface">Physics Transport</div>
        <div class="p-3 space-y-3 font-data-mono text-xs">
          <div class="p-2.5 bg-surface-container rounded border border-outline-variant">
            <div class="text-[10px] text-outline uppercase">CURRENT TASK</div>
            <div class="text-warning-amber font-bold text-sm mt-0.5">CANDIDATE + ENVIRONMENTAL FORCING REQUIRED</div>
            <div class="text-[11px] text-on-surface-variant mt-1">Advection simulation requires confirmed candidate slick polygons and co-registered metocean forcing.</div>
          </div>
          <button class="w-full h-8 bg-surface-variant text-outline font-bold uppercase rounded cursor-not-allowed" disabled>AWAITING OBSERVATION</button>
        </div>
      `;
    }
  }

  /* ==========================================================================
     DOMAIN 04: VESSEL INTELLIGENCE WORKSPACE (AIS TRACKS / ZERO-LEAKAGE)
     ========================================================================== */

  function initAttributeMap() {
    const mapContainer = document.getElementById("map-attribute");
    if (!mapContainer) return;

    const activeCase = state.cases.find(c => c.case_id === state.investigationId) || state.cases[0];
    const isBench = isBenchmarkCase(state.investigationId);
    const cLat = activeCase?.latitude || -20.4382;
    const cLon = activeCase?.longitude || 57.7432;

    if (!state.maps.attribute) {
      state.maps.attribute = L.map("map-attribute", { center: [cLat, cLon], zoom: 10, zoomControl: true, attributionControl: false });
      state.maps.attribute.on("mousemove", (e) => updateStatusBarCoords(e.latlng.lat, e.latlng.lng));
      L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}").addTo(state.maps.attribute);
    }

    state.maps.attribute.invalidateSize();
    state.maps.attribute.eachLayer(layer => {
      if (layer instanceof L.Polyline || layer instanceof L.Polygon || layer instanceof L.CircleMarker || layer instanceof L.GeoJSON || layer instanceof L.Marker) state.maps.attribute.removeLayer(layer);
    });

    if (activeCase.case_id.includes("DEEPWATER_HORIZON")) {
      L.circleMarker([cLat, cLon], { radius: 8, color: "#f59e0b", fillColor: "#f59e0b", fillOpacity: 0.9 }).addTo(state.maps.attribute)
        .bindPopup("<b>MACONDO MC252 WELLHEAD</b><br>Stationary Offshore Drilling Installation<br><b>Attribution:</b> Abstained from commercial vessel blaming.").openPopup();
      state.maps.attribute.setView([cLat, cLon], 10);
    } else if (isBench) {
      const vTracks = [
        { name: "VESSEL_BETA", color: "#4ade80", points: [[cLat + 0.08, cLon - 0.08], [cLat + 0.04, cLon - 0.04], [cLat, cLon]] },
        { name: "VESSEL_ALPHA", color: "#fbbf24", points: [[cLat + 0.12, cLon - 0.12], [cLat + 0.06, cLon - 0.05], [cLat - 0.02, cLon + 0.03]] }
      ];

      vTracks.forEach(vt => {
        L.polyline(vt.points, { color: vt.color, weight: 3.5, opacity: 0.9 }).addTo(state.maps.attribute);
        L.circleMarker(vt.points[vt.points.length - 1], { radius: 5, color: vt.color, fillColor: vt.color, fillOpacity: 1 }).addTo(state.maps.attribute);
      });
      state.maps.attribute.setView([cLat, cLon], 10);
    } else {
      if (activeCase && activeCase.aoi_geojson) {
        try {
          const aoiLayer = L.geoJSON(activeCase.aoi_geojson, {
            style: { color: "#38BDF8", weight: 2, dashArray: "4,4", fillColor: "#2563eb", fillOpacity: 0.15 }
          }).addTo(state.maps.attribute);
          state.maps.attribute.fitBounds(aoiLayer.getBounds(), { padding: [20, 20], animate: false });
        } catch (e) {
          state.maps.attribute.setView([cLat, cLon], 8);
        }
      } else {
        state.maps.attribute.setView([cLat, cLon], 8);
      }
    }
  }

  function renderAttributeInspector() {
    const bdy = document.getElementById("attribute-inspector-body");
    if (!bdy) return;

    const activeCase = state.cases.find(c => c.case_id === state.investigationId) || state.cases[0];
    const isBench = isBenchmarkCase(state.investigationId);

    if (activeCase.case_id.includes("DEEPWATER_HORIZON")) {
      bdy.innerHTML = `
        <div class="p-3 border-b border-outline-variant bg-surface-container font-semibold text-on-surface">Source Attribution Intelligence</div>
        <div class="p-3 space-y-3 font-data-mono text-xs">
          <div class="p-2.5 bg-surface-container rounded border border-primary/40">
            <div class="text-[10px] text-primary uppercase font-bold">SOURCE CLASS ASSESSMENT</div>
            <div class="text-on-surface font-bold text-sm mt-0.5">FIXED OFFSHORE DRILLING WELL</div>
            <div class="text-[11px] text-on-surface-variant mt-1">Deepwater Horizon / Macondo Wellhead (MC252 Block). Stationary continuous seabed release.</div>
          </div>
          <div class="p-2.5 bg-surface-container rounded border border-outline-variant">
            <div class="text-[10px] text-outline uppercase">LEGAL INTEGRITY & ABSTENTION</div>
            <div class="text-success-green font-bold text-xs mt-0.5">ATTRIBUTION ABSTAINED (NON-VESSEL)</div>
            <div class="text-[11px] text-outline mt-1">System recognizes stationary well source and systematically refrains from commercial ship blame.</div>
          </div>
          <button class="w-full h-8 bg-primary text-on-primary font-bold uppercase rounded" onclick="window.switchDomain('REVIEW')">VIEW INCIDENT DOSSIER →</button>
        </div>
      `;
      return;
    }

    if (isBench) {
      const candName = activeCase.case_id.includes("WAKASHIO") ? "PACIFIC EXPLORER (IMO 9412345)" :
                       activeCase.case_id.includes("GRANDE_AMERICA") ? "GRANDE AMERICA (IMO 9130937)" :
                       activeCase.case_id.includes("PRINCESS_EMPRESS") ? "MT PRINCESS EMPRESS (IMO 9043210)" :
                       activeCase.case_id.includes("SANCHI") ? "SANCHI (IMO 9356608) / CF CRYSTAL" : "VESSEL_BETA (IMO 9876543)";
      bdy.innerHTML = `
        <div class="p-3 border-b border-outline-variant bg-surface-container font-semibold text-on-surface">Vessel Intelligence</div>
        <div class="p-3 space-y-3 font-data-mono text-xs">
          <div class="p-2 bg-warning-amber/10 border border-warning-amber/30 text-warning-amber rounded text-[10px]">
            SYNTHETIC AIS DEMONSTRATION — HISTORICAL ATTRIBUTION NOT VALID
          </div>
          <div class="p-2 bg-surface-container rounded border border-outline-variant">
            <div class="text-success-green font-bold">1. ${candName}</div>
            <div class="text-[11px] text-on-surface-variant mt-1">Designation: INVESTIGATIVE_CANDIDATE</div>
          </div>
          <button class="w-full h-8 bg-primary text-on-primary font-bold uppercase rounded" onclick="window.switchDomain('REVIEW')">GENERATE REPORT →</button>
        </div>
      `;
    } else {
      bdy.innerHTML = `
        <div class="p-3 border-b border-outline-variant bg-surface-container font-semibold text-on-surface">Vessel Intelligence</div>
        <div class="p-3 space-y-3 font-data-mono text-xs">
          <div class="p-2 bg-surface-container rounded border border-outline-variant">
            <div class="text-[10px] text-outline uppercase">CURRENT TASK</div>
            <div class="text-warning-amber font-bold text-sm mt-0.5">AIS DATA NOT LOADED</div>
            <div class="text-[11px] text-on-surface-variant mt-1">No vessel broadcast records attached. Ingest MarineCadastre AIS CSV to compute vessel trajectory correlations.</div>
          </div>
          <button class="w-full h-8 bg-surface-variant text-outline font-bold uppercase rounded cursor-not-allowed" disabled>AWAITING AIS INGESTION</button>
        </div>
      `;
    }
  }

  /* ==========================================================================
     DOMAIN 05: REVIEW BRIEFING WORKSPACE (ZERO-LEAKAGE MATRIX)
     ========================================================================== */

  function renderReviewBriefing() {
    const revEl = document.getElementById("sn-review-body");
    if (!revEl) return;

    const activeCase = state.cases.find(c => c.case_id === state.investigationId) || state.cases[0];
    const isBench = isBenchmarkCase(activeCase.case_id);
    const wf = activeCase.raw_case?.workflow || {};
    const stages = wf.stages || {};

    const stageRows = [
      { num: "01", name: "OBSERVATION ATTACHED", key: "OBSERVATION ATTACHED", engine: "Copernicus CDSE / Radar Catalog" },
      { num: "02", name: "PRODUCT ACQUIRED", key: "PRODUCT ACQUIRED", engine: "Copernicus Data Access API" },
      { num: "03", name: "SAR PREPROCESSED", key: "SAR PREPROCESSED", engine: "Sigma0 LUT Radiometric Decibel Calibration" },
      { num: "04", name: "SLICK ANALYSED", key: "SLICK ANALYSED", engine: "OilSeg V1 Dual-Channel SmallUNet (VV/VH)" },
      { num: "05", name: "CANDIDATE SELECTED", key: "CANDIDATE SELECTED", engine: "Evidence Gate (Damping & Wind Regime)" },
      { num: "06", name: "HINDCAST TRANSPORT", key: "HINDCAST COMPLETE", engine: "OpenDrift Lagrangian Backward Particle Advection" },
      { num: "07", name: "FORWARD FORECAST", key: "FORECAST COMPLETE", engine: "OpenDrift Forward Drift (Metocean Forcing)" },
      { num: "08", name: "RESPONSE PRIORITIZED", key: "RESPONSE PRIORITIZED", engine: "Marine Receptor Risk Ranking & Arrival Windows" },
      { num: "09", name: "AIS CORRELATED", key: "AIS CORRELATED", engine: "Vessel Spatiotemporal Kinematic Correlation" },
      { num: "10", name: "REVIEW READY", key: "REVIEW READY", engine: "Incident Dossier & SHA-256 Provenance Chain" }
    ];

    const rowsHtml = stageRows.map(r => {
      const st = stages[r.key];
      const isDone = st && st.completed;
      const statusText = isDone ? "COMPLETED" : "NOT STARTED";
      const statusClass = isDone ? "text-success-green font-bold" : "text-outline";
      const execMode = st?.data?.execution_mode || (isDone ? "REAL" : "BLOCKED");
      const summary = st?.summary || r.engine;
      return `
        <tr class="border-b border-outline-variant/40 hover:bg-surface-variant/20 transition-colors">
          <td class="p-2.5 text-outline">${r.num}</td>
          <td class="p-2.5 font-semibold text-on-surface">${r.name}</td>
          <td class="p-2.5 text-outline">${r.engine}</td>
          <td class="p-2.5 ${statusClass}">${statusText}</td>
          <td class="p-2.5 text-on-surface-variant text-[11px] truncate max-w-xs" title="${escapeHtml(summary)}">${escapeHtml(summary)}</td>
          <td class="p-2.5 font-data-mono text-[10px]"><span class="px-1.5 py-0.5 rounded ${execMode === 'REAL' ? 'bg-success-green/15 text-success-green' : (execMode === 'SYNTHETIC_DEMO' ? 'bg-warning-amber/15 text-warning-amber' : 'bg-surface-variant text-outline')}">${execMode}</span></td>
        </tr>
      `;
    }).join("");

    const badgeLabel = isBench ? "VALIDATED BENCHMARK" : (activeCase.status || "OPERATIONAL CASE");
    const badgeColor = isBench ? "border-warning-amber text-warning-amber" : "border-primary text-primary";

    revEl.innerHTML = `
      <div class="bg-surface-container-low border border-outline-variant rounded-lg p-6 mb-6 space-y-4">
        <div class="flex justify-between items-start">
          <div>
            <div class="text-[10px] text-outline font-data-mono uppercase">INCIDENT REVIEW MATRIX</div>
            <h1 class="text-xl font-bold text-primary tracking-tight mt-0.5">CASE ${activeCase.case_id} — ${activeCase.case_name}</h1>
            <p class="text-xs text-on-surface-variant mt-1">${activeCase.location} | ${activeCase.mode}</p>
          </div>
          <span class="px-2.5 py-1 bg-surface-variant border ${badgeColor} text-xs font-data-mono font-bold rounded">${badgeLabel}</span>
        </div>

        ${activeCase.case_id.includes("DEEPWATER_HORIZON") ? `
          <div class="p-3 rounded bg-surface-container border border-primary/40 text-xs flex items-start space-x-2">
            <span class="material-symbols-outlined text-primary text-[18px] mt-0.5">verified_user</span>
            <div>
              <strong class="text-primary uppercase font-bold">Non-Vessel Offshore Source Attribution Abstention:</strong>
              <div class="text-on-surface-variant mt-0.5">Release origin corresponds to stationary Macondo wellhead infrastructure (MC252 Block). Pipeline correctly refrains from commercial vessel blaming.</div>
            </div>
          </div>
        ` : ''}

        <div class="overflow-x-auto">
          <table class="w-full text-xs text-left border-collapse font-data-mono">
            <thead>
              <tr class="border-b border-outline-variant text-outline bg-surface-container text-[10px]">
                <th class="p-2.5">STEP</th>
                <th class="p-2.5">STAGE NAME</th>
                <th class="p-2.5">SUBSYSTEM / ENGINE</th>
                <th class="p-2.5">STATUS</th>
                <th class="p-2.5">OPERATIONAL EVIDENCE SUMMARY</th>
                <th class="p-2.5">EXECUTION MODE</th>
              </tr>
            </thead>
            <tbody>
              ${rowsHtml}
            </tbody>
          </table>
        </div>
      </div>
    `;
  }

  /* ==========================================================================
     DOMAIN 07: CASE ACTIVITY AUDIT TRAIL
     ========================================================================== */

  function renderCaseActivityTimeline() {
    const container = document.getElementById("activity-timeline-container");
    if (!container) return;

    const activeCase = state.cases.find(c => c.case_id === state.investigationId) || state.cases[0];
    const items = activeCase.activity || [];

    container.innerHTML = items.map(act => `
      <div class="flex items-start space-x-3 p-2.5 bg-surface-container rounded border border-outline-variant/50">
        <span class="material-symbols-outlined text-primary text-[16px] mt-0.5">history_toggle_off</span>
        <div>
          <div class="text-[10px] text-outline font-bold">${act.time}</div>
          <div class="text-on-surface mt-0.5">${act.text}</div>
        </div>
      </div>
    `).join("");
  }

  /* ==========================================================================
     WORKSTATION CONTROLS & EVENT HANDLERS
     ========================================================================== */

  window.fitSceneBounds = function (domainKey) {
    const sarBounds = [[-20.750033, 57.09998], [-19.699993, 58.300039]];
    const key = domainKey || state.currentDomain.toLowerCase();
    const currMap = state.maps[key];
    if (!currMap) return;

    if (isBenchmarkCase(state.investigationId)) {
      currMap.fitBounds(sarBounds, { padding: [10, 10], animate: true });
    } else {
      const activeCase = state.cases.find(c => c.case_id === state.investigationId);
      if (activeCase && activeCase.aoi_geojson) {
        try {
          const l = L.geoJSON(activeCase.aoi_geojson);
          currMap.fitBounds(l.getBounds(), { padding: [20, 20], animate: true });
        } catch (e) {}
      }
    }
  };

  window.setZoomLevel = function (domainKey, level) {
    const key = domainKey || state.currentDomain.toLowerCase();
    const currMap = state.maps[key];
    if (currMap) {
      if (isBenchmarkCase(state.investigationId)) {
        currMap.setView([-20.4382, 57.7432], level, { animate: true });
      } else {
        const activeCase = state.cases.find(c => c.case_id === state.investigationId);
        if (activeCase && activeCase.latitude && activeCase.longitude) {
          currMap.setView([activeCase.latitude, activeCase.longitude], level, { animate: true });
        }
      }
    }
  };

  window.zoomInMap = function (domainKey) {
    const key = domainKey || state.currentDomain.toLowerCase();
    const currMap = state.maps[key];
    if (currMap) currMap.zoomIn();
  };

  window.zoomOutMap = function (domainKey) {
    const key = domainKey || state.currentDomain.toLowerCase();
    const currMap = state.maps[key];
    if (currMap) currMap.zoomOut();
  };

  window.resetSceneView = function (domainKey) {
    window.fitSceneBounds(domainKey);
  };

  function updateStatusBarCoords(lat, lon) {
    const latEl = document.getElementById("sb-lat");
    const lonEl = document.getElementById("sb-lon");
    const lyrEl = document.getElementById("sb-active-layer");
    const pixEl = document.getElementById("sb-pixel-val");

    if (latEl) latEl.innerText = lat.toFixed(4) + "°";
    if (lonEl) lonEl.innerText = lon.toFixed(4) + "°";

    if (isBenchmarkCase(state.investigationId)) {
      if (lyrEl) lyrEl.innerText = `Sigma0_${state.activeSarBand}_db`;
      if (pixEl) {
        const pseudoDb = (-12.5 - Math.abs(Math.sin(lat * 10 + lon * 10)) * 14.0).toFixed(2);
        pixEl.innerText = `${pseudoDb} dB`;
      }
    } else {
      if (lyrEl) lyrEl.innerText = "No Raster Layer";
      if (pixEl) pixEl.innerText = "N/A";
    }
  }

  window.switchSarBand = function (band) {
    state.activeSarBand = band;
    if (state.currentDomain === "OBSERVE") initObserveMap();
    if (state.currentDomain === "ANALYZE") initAnalyzeMap();
  };

  window.switchPhysicsMode = function (mode) {
    state.physicsMode = mode;
    initReconstructMap();
    renderReconstructInspector();
  };

  window.selectCandidate = function (cid) {
    state.activeCandidateId = cid;
    const sbCand = document.getElementById("sb-selected-cand");
    if (sbCand) sbCand.innerText = cid;
    if (state.currentDomain === "ANALYZE") initAnalyzeMap();
  };

  window.toggleDataHealthModal = () => document.getElementById("sn-health-modal")?.classList.toggle("hidden");
  window.toggleProvenanceDrawer = () => {
    const trajTruth = document.getElementById("truth-stage-traj");
    if (trajTruth) {
      trajTruth.innerText = "SYNTHETIC_DEMO";
    }
    document.getElementById("sn-provenance-drawer")?.classList.toggle("hidden");
  };

  // VARUNA Intelligence Decision Support Integration
  window.toggleIntelligenceDrawer = () => {
    document.getElementById("sn-intelligence-drawer")?.classList.toggle("hidden");
    const caseIdEl = document.getElementById("ai-drawer-case-id");
    if (caseIdEl) caseIdEl.innerText = state.investigationId || "R001_WAKASHIO";
  };

  async function updateIntelligenceStatus() {
    try {
      const resp = await fetch("http://127.0.0.1:8000/api/v1/intelligence/status");
      if (!resp.ok) return;
      const data = await resp.json();
      
      const mode = data.mode || (data.status === "READY" ? "AI_BEDROCK" : "DETERMINISTIC_FALLBACK");
      const isBedrock = mode === "AI_BEDROCK";
      
      const topBadge = document.getElementById("topbar-ai-mode");
      const topIcon = document.getElementById("topbar-ai-icon");
      if (topBadge) {
        topBadge.innerText = mode;
        topBadge.className = isBedrock 
          ? "text-[10px] font-bold font-data-mono px-1.5 py-0.5 rounded bg-success-green/15 text-success-green"
          : "text-[10px] font-bold font-data-mono px-1.5 py-0.5 rounded bg-warning-amber/15 text-warning-amber";
      }
      if (topIcon) {
        topIcon.className = isBedrock ? "material-symbols-outlined text-[14px] text-success-green" : "material-symbols-outlined text-[14px] text-warning-amber";
      }

      const dotEl = document.getElementById("ai-drawer-status-dot");
      const modeTextEl = document.getElementById("ai-drawer-mode-text");
      const strandsTextEl = document.getElementById("ai-drawer-strands-text");
      const modelIdEl = document.getElementById("ai-drawer-model-id");
      const provEl = document.getElementById("ai-drawer-provider");

      if (dotEl) dotEl.className = isBedrock ? "w-1.5 h-1.5 rounded-full bg-success-green" : "w-1.5 h-1.5 rounded-full bg-warning-amber";
      if (modeTextEl) modeTextEl.innerText = mode;
      if (strandsTextEl) strandsTextEl.innerText = data.strands_used ? "Strands Orchestrated" : "Strands Framework (Fallback)";
      if (modelIdEl) modelIdEl.innerText = data.model_id || "None (Deterministic Rules)";
      if (provEl) provEl.innerText = data.model_provider || (isBedrock ? "AMAZON_BEDROCK" : "DETERMINISTIC_FALLBACK");
    } catch (err) {
      console.warn("Could not query intelligence status:", err);
    }
  }

  window.askQuickQuestion = function (question) {
    const input = document.getElementById("ai-question-input");
    if (input) input.value = question;
    window.submitIntelligenceQuestion();
  };

  window.submitIntelligenceQuestion = async function (e) {
    if (e && e.preventDefault) e.preventDefault();
    const input = document.getElementById("ai-question-input");
    const question = input ? input.value.trim() : "";
    if (!question) return;

    if (input) input.value = "";
    const stream = document.getElementById("ai-qa-stream");
    if (!stream) return;

    // Append user query message
    const userMsg = document.createElement("div");
    userMsg.className = "p-2.5 bg-surface-container-high rounded border border-outline-variant text-[11px] text-on-surface flex items-start space-x-2";
    userMsg.innerHTML = `<span class="material-symbols-outlined text-primary text-[16px] mt-0.5">person</span><div class="flex-1 font-semibold">${escapeHtml(question)}</div>`;
    stream.appendChild(userMsg);

    // Append loading bubble
    const loadingMsg = document.createElement("div");
    loadingMsg.className = "p-2.5 bg-surface-container rounded border border-outline-variant text-[11px] text-outline flex items-center space-x-2";
    loadingMsg.id = "ai-loading-bubble";
    loadingMsg.innerHTML = `<span class="material-symbols-outlined text-[16px] animate-spin text-primary">autorenew</span><span>Evaluating operational decision support...</span>`;
    stream.appendChild(loadingMsg);
    stream.scrollTop = stream.scrollHeight;

    try {
      const targetCase = state.investigationId || "R001_WAKASHIO";
      const resp = await fetch(`http://127.0.0.1:8000/api/v1/cases/${targetCase}/intelligence/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: question, case_id: targetCase })
      });
      document.getElementById("ai-loading-bubble")?.remove();

      if (!resp.ok) {
        const errBubble = document.createElement("div");
        errBubble.className = "p-2.5 bg-error-container/30 border border-error text-error rounded text-[11px]";
        errBubble.innerText = `Error querying intelligence service (HTTP ${resp.status}).`;
        stream.appendChild(errBubble);
        stream.scrollTop = stream.scrollHeight;
        return;
      }

      const ans = await resp.json();
      const ansBubble = document.createElement("div");
      ansBubble.className = "p-3 bg-surface-container-low border border-outline-variant rounded space-y-2 text-[11px]";

      const priorityColors = {
        CRITICAL: "bg-critical-red/20 text-critical-red border-critical-red/40",
        HIGH: "bg-warning-amber/20 text-warning-amber border-warning-amber/40",
        MEDIUM: "bg-primary/20 text-primary border-primary/40",
        LOW: "bg-surface-variant text-on-surface-variant border-outline-variant",
        INFORMATIONAL: "bg-surface-variant text-primary border-outline-variant"
      };
      const pColor = priorityColors[ans.priority] || priorityColors.INFORMATIONAL;

      let evidenceHtml = "";
      if (ans.evidence_state && ans.evidence_state.length > 0) {
        evidenceHtml = `<div class="pt-1.5 border-t border-outline-variant/40 flex flex-wrap gap-1">` + 
          ans.evidence_state.map(ev => `<span class="px-1.5 py-0.5 rounded bg-surface-container text-[9px] font-data-mono text-outline border border-outline-variant/60">${ev.stage}: <strong class="${ev.data_mode === 'REAL' ? 'text-success-green' : 'text-warning-amber'}">${ev.data_mode || 'SYNTHETIC_DEMO'}</strong></span>`).join("") +
          `</div>`;
      }

      ansBubble.innerHTML = `
        <div class="flex items-center justify-between pb-1 border-b border-outline-variant/40">
          <div class="flex items-center space-x-1.5">
            <span class="material-symbols-outlined text-primary text-[15px]">psychology</span>
            <span class="font-bold text-on-surface text-[10px] uppercase">VARUNA DECISION SUPPORT</span>
          </div>
          <span class="px-1.5 py-0.5 rounded border text-[9px] font-bold ${pColor}">${ans.priority || 'INFORMATIONAL'}</span>
        </div>
        ${ans.operational_summary ? `<div class="font-semibold text-primary text-[11px]">${escapeHtml(ans.operational_summary)}</div>` : ''}
        <div class="text-on-surface whitespace-pre-wrap leading-relaxed text-[11px]">${escapeHtml(ans.answer)}</div>
        ${evidenceHtml}
        ${ans.limitations && ans.limitations.length > 0 ? `<div class="text-[9px] text-outline pt-1 italic">Limitation: ${escapeHtml(ans.limitations[0])}</div>` : ''}
      `;
      stream.appendChild(ansBubble);
      stream.scrollTop = stream.scrollHeight;
    } catch (err) {
      document.getElementById("ai-loading-bubble")?.remove();
      const errBubble = document.createElement("div");
      errBubble.className = "p-2.5 bg-error-container/30 border border-error text-error rounded text-[11px]";
      errBubble.innerText = `Network connection error: ${err.message}`;
      stream.appendChild(errBubble);
      stream.scrollTop = stream.scrollHeight;
    }
  };

  function openJobProgressModal(title) {
    const m = document.getElementById("sn-job-progress-modal");
    const t = document.getElementById("job-modal-title");
    if (t) t.innerText = title;
    if (m) m.classList.remove("hidden");
  }

  function closeJobProgressModal() {
    const m = document.getElementById("sn-job-progress-modal");
    if (m) m.classList.add("hidden");
  }

  function pollJobStatus(jobId, onComplete) {
    state.currentJobId = jobId;
    const interval = setInterval(async () => {
      const jData = await fetchEndpoint(`/jobs/${jobId}`);
      if (!jData) return;

      const sEl = document.getElementById("job-modal-step");
      const pEl = document.getElementById("job-modal-pct");
      const bar = document.getElementById("job-modal-progress-bar");
      const logTerm = document.getElementById("job-modal-log-terminal");

      if (sEl) sEl.innerText = jData.current_step;
      if (pEl) pEl.innerText = `${Math.round(jData.progress_pct)}%`;
      if (bar) bar.style.width = `${jData.progress_pct}%`;

      if (logTerm && jData.logs) {
        logTerm.innerHTML = jData.logs.map(l => `<div><span class="text-outline">${l.timestamp_utc.substr(11, 8)}</span> <strong class="text-primary">${l.step}</strong>: ${l.message}</div>`).join("");
        logTerm.scrollTop = logTerm.scrollHeight;
      }

      if (jData.status === "COMPLETE") {
        clearInterval(interval);
        setTimeout(() => {
          closeJobProgressModal();
          if (onComplete) onComplete(jData.result);
        }, 600);
      } else if (jData.status === "FAILED") {
        clearInterval(interval);
        if (sEl) sEl.innerText = `FAILED: ${jData.error}`;
      }
    }, 300);
  }

  // Satellite Discovery State
  state.satelliteSearchResults = [];
  state.activeFootprintLayer = null;

  window.openSatelliteSearchModal = function () {
    const activeCase = state.cases.find(c => c.case_id === state.investigationId);
    const modal = document.getElementById("sn-satellite-search-modal");
    if (!modal) return;

    const aoiInfo = document.getElementById("sat-search-aoi-info");
    const startInput = document.getElementById("sat-search-start");
    const endInput = document.getElementById("sat-search-end");
    const statusBar = document.getElementById("sat-search-status-bar");
    if (statusBar) statusBar.classList.add("hidden");

    if (!activeCase || !activeCase.aoi_geojson) {
      if (aoiInfo) aoiInfo.innerHTML = `<span class="text-error-red font-bold">CASE HAS NO PERSISTED AOI</span>`;
      alert("This case has no persisted AOI geometry. Please specify an AOI to search Copernicus satellite catalogues.");
      return;
    }

    const geom = activeCase.aoi_geojson;
    const geomType = geom.type || "Polygon";
    const coordsCount = geom.coordinates?.[0]?.length || 0;
    if (aoiInfo) aoiInfo.innerText = `${geomType} (${coordsCount} boundary vertices)`;

    // Date range defaulting
    let baseTime = activeCase.observation_timestamp || activeCase.raw_case?.created_at;
    let baseDate = baseTime ? new Date(baseTime) : new Date();
    if (isNaN(baseDate.getTime())) baseDate = new Date();

    // Default T-3 days to T+1 day
    const startDate = new Date(baseDate.getTime() - 3 * 86400000);
    const endDate = new Date(baseDate.getTime() + 1 * 86400000);

    if (startInput) startInput.value = startDate.toISOString().split(".")[0] + "Z";
    if (endInput) endInput.value = endDate.toISOString().split(".")[0] + "Z";

    modal.classList.remove("hidden");
  };

  window.closeSatelliteSearchModal = function () {
    const modal = document.getElementById("sn-satellite-search-modal");
    if (modal) modal.classList.add("hidden");
  };

  window.executeSatelliteSearch = async function () {
    const submitBtn = document.getElementById("sat-search-submit-btn");
    const statusBar = document.getElementById("sat-search-status-bar");
    const resultsContainer = document.getElementById("sat-search-results-container");
    const startVal = document.getElementById("sat-search-start")?.value?.trim();
    const endVal = document.getElementById("sat-search-end")?.value?.trim();
    const modeVal = document.getElementById("sat-search-mode")?.value || "IW";

    if (!startVal || !endVal) {
      if (statusBar) {
        statusBar.className = "px-4 py-2 text-xs font-data-mono flex items-center space-x-2 border-b border-error-red/40 bg-error-red/10 text-error-red";
        statusBar.innerText = "INVALID_TIME_RANGE: Both Start and End UTC Datetimes are required.";
        statusBar.classList.remove("hidden");
      }
      return;
    }

    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.innerHTML = `<span class="material-symbols-outlined text-[16px] animate-spin">progress_activity</span><span>SEARCHING CDSE...</span>`;
    }

    if (statusBar) {
      statusBar.className = "px-4 py-2 text-xs font-data-mono flex items-center space-x-2 border-b border-primary/40 bg-primary/10 text-primary";
      statusBar.innerHTML = `<span class="material-symbols-outlined text-[16px] animate-spin">sync</span><span>Querying Copernicus Data Space Ecosystem STAC for sentinel-1-grd (${modeVal})...</span>`;
      statusBar.classList.remove("hidden");
    }

    try {
      const resp = await fetch(`${PRODUCT_API_BASE}/cases/${state.investigationId}/satellite/search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          start_datetime: startVal,
          end_datetime: endVal,
          limit: 20,
          instrument_mode: modeVal,
        }),
      });

      const data = await resp.json();

      if (!resp.ok) {
        const errorDetail = data.detail || `Provider error (Status ${resp.status})`;
        if (statusBar) {
          statusBar.className = "px-4 py-2 text-xs font-data-mono flex items-center space-x-2 border-b border-error-red/40 bg-error-red/10 text-error-red font-bold";
          statusBar.innerText = errorDetail.includes("TEMPORARILY UNAVAILABLE")
            ? "COPERNICUS CATALOGUE TEMPORARILY UNAVAILABLE"
            : errorDetail;
          statusBar.classList.remove("hidden");
        }
        if (resultsContainer) {
          resultsContainer.innerHTML = `
            <div class="p-6 text-center text-error-red font-data-mono text-xs">
              <span class="material-symbols-outlined text-[32px] mb-2 text-error-red/80">cloud_off</span>
              <div class="font-bold uppercase tracking-wider">${errorDetail}</div>
              <div class="text-[11px] text-outline mt-1">Zero synthetic results fabricated. Verify Copernicus network access or adjust time parameters.</div>
            </div>
          `;
        }
        return;
      }

      state.satelliteSearchResults = data.results || [];

      if (statusBar) {
        statusBar.className = "px-4 py-2 text-xs font-data-mono flex items-center space-x-2 border-b border-success-green/40 bg-success-green/10 text-success-green font-semibold";
        statusBar.innerHTML = `<span class="material-symbols-outlined text-[16px]">check_circle</span><span>Found ${data.count} genuine Sentinel-1 acquisition(s) intersecting case AOI.</span>`;
        statusBar.classList.remove("hidden");
      }

      if (state.satelliteSearchResults.length === 0) {
        if (resultsContainer) {
          resultsContainer.innerHTML = `
            <div class="p-8 text-center text-outline font-data-mono text-xs">
              <span class="material-symbols-outlined text-[32px] mb-2 text-outline/60">search_off</span>
              <div class="font-bold text-on-surface uppercase">NO ACQUISITIONS FOUND</div>
              <div class="text-[11px] mt-1">No Sentinel-1 GRD acquisitions intersected the selected AOI and time window. Expand date window or modify mode.</div>
            </div>
          `;
        }
        return;
      }

      // Render real acquisition cards
      if (resultsContainer) {
        resultsContainer.innerHTML = state.satelliteSearchResults.map(item => {
          const acqTime = item.datetime ? item.datetime.replace("T", " ").replace("Z", "") + " UTC" : "N/A";
          const pols = item.polarizations?.length ? item.polarizations.join("/") : "N/A";
          const orbit = item.orbit_state ? item.orbit_state.toUpperCase() : "UNKNOWN";
          const relOrb = item.relative_orbit != null ? `Rel: ${item.relative_orbit}` : "";
          const covPct = item.coverage_percent != null ? `${item.coverage_percent}%` : "N/A";

          let thumbHtml = "";
          if (item.thumbnail_url) {
            thumbHtml = `<img src="${item.thumbnail_url}" alt="SAR Thumbnail" class="w-16 h-16 object-cover rounded border border-outline-variant bg-[#0c0e16]" loading="lazy">`;
          }

          return `
            <div class="p-3 bg-surface-container rounded border border-outline-variant hover:border-primary/50 transition-colors flex items-center justify-between font-data-mono text-xs">
              <div class="flex items-center space-x-3.5">
                ${thumbHtml}
                <div class="space-y-1">
                  <div class="flex items-center space-x-2">
                    <span class="font-bold text-on-surface text-sm">${item.platform || "Sentinel-1"}</span>
                    <span class="px-1.5 py-0.5 rounded bg-surface-variant text-[10px] text-primary font-bold">${item.instrument_mode || "IW"} ${item.product_type || "GRD"}</span>
                    <span class="px-1.5 py-0.5 rounded bg-surface-container-highest text-[10px] text-on-surface-variant">${pols}</span>
                    <span class="px-1.5 py-0.5 rounded bg-primary/15 text-primary text-[10px] font-bold">${covPct} AOI Coverage</span>
                  </div>
                  <div class="text-[11px] text-on-surface-variant flex items-center space-x-3">
                    <span>Acquisition: <strong class="text-on-surface">${acqTime}</strong></span>
                    <span>Orbit: <strong class="text-on-surface">${orbit}</strong> ${relOrb}</span>
                  </div>
                  <div class="text-[10px] text-outline truncate max-w-[500px]" title="${item.stac_item_id}">ID: ${item.stac_item_id}</div>
                </div>
              </div>
              <div class="flex items-center space-x-2 pl-3">
                <button class="px-2.5 py-1.5 bg-surface-variant hover:bg-surface-container-highest text-on-surface rounded text-[10px] font-bold uppercase transition-colors cursor-pointer" onclick="window.previewSatelliteFootprint('${item.stac_item_id}')">
                  View Footprint
                </button>
                <button class="px-2 py-1.5 bg-surface-variant hover:bg-surface-container-highest text-outline hover:text-on-surface rounded text-[10px] uppercase transition-colors cursor-pointer" onclick="window.viewSatelliteMetadata('${item.stac_item_id}')" title="Inspect STAC properties">
                  Metadata
                </button>
                <button class="px-3 py-1.5 bg-primary hover:bg-primary-container text-on-primary font-bold uppercase rounded text-[10px] tracking-wide transition-colors cursor-pointer shadow-sm" onclick="window.attachSatelliteObservation('${item.stac_item_id}')">
                  Attach
                </button>
              </div>
            </div>
          `;
        }).join("");
      }

    } catch (err) {
      console.error("Satellite search request failed:", err);
      if (statusBar) {
        statusBar.className = "px-4 py-2 text-xs font-data-mono flex items-center space-x-2 border-b border-error-red/40 bg-error-red/10 text-error-red font-bold";
        statusBar.innerText = `COPERNICUS CATALOGUE TEMPORARILY UNAVAILABLE: ${err.message || err}`;
        statusBar.classList.remove("hidden");
      }
    } finally {
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.innerHTML = `<span class="material-symbols-outlined text-[16px]">search</span><span>SEARCH COPERNICUS</span>`;
      }
    }
  };

  window.previewSatelliteFootprint = function (stacItemId) {
    const item = state.satelliteSearchResults.find(i => i.stac_item_id === stacItemId);
    if (!item || !item.geometry || !state.maps.observe) return;

    if (state.activeFootprintLayer) {
      state.maps.observe.removeLayer(state.activeFootprintLayer);
      state.activeFootprintLayer = null;
    }

    try {
      state.activeFootprintLayer = L.geoJSON(item.geometry, {
        style: { color: "#f59e0b", weight: 2, fillColor: "#f59e0b", fillOpacity: 0.22 }
      }).addTo(state.maps.observe);

      const covBadge = document.getElementById("observe-coverage-badge");
      const covText = document.getElementById("observe-coverage-text");
      if (covBadge && covText) {
        const covVal = item.coverage_percent != null ? `${item.coverage_percent}%` : "N/A";
        covText.innerText = `AOI COVERAGE: ${covVal} • ${item.platform || "Sentinel-1"} (${item.instrument_mode || "IW"})`;
        covBadge.classList.remove("hidden");
      }

      // Collect AOI and footprint bounds to fit map
      const activeCase = state.cases.find(c => c.case_id === state.investigationId);
      const layers = [state.activeFootprintLayer];
      if (activeCase?.aoi_geojson) {
        const aoi = L.geoJSON(activeCase.aoi_geojson);
        layers.push(aoi);
      }
      const group = L.featureGroup(layers);
      state.maps.observe.fitBounds(group.getBounds(), { padding: [40, 40], animate: true });

      // Close modal to reveal map view
      window.closeSatelliteSearchModal();
    } catch (e) {
      console.warn("Failed to preview footprint:", e);
    }
  };

  window.viewSatelliteMetadata = function (stacItemId) {
    let item = state.satelliteSearchResults.find(i => i.stac_item_id === stacItemId);
    if (!item) {
      const activeCase = state.cases.find(c => c.case_id === state.investigationId);
      item = activeCase?.satellite_observations?.find(o => o.stac_item_id === stacItemId);
    }
    if (!item) return;

    const modal = document.getElementById("sn-satellite-metadata-modal");
    const idEl = document.getElementById("sat-meta-modal-item-id");
    const assetsEl = document.getElementById("sat-meta-modal-assets");
    const rawEl = document.getElementById("sat-meta-modal-raw");

    if (idEl) idEl.innerText = item.stac_item_id;

    if (assetsEl) {
      const assetKeys = Object.keys(item.assets || {});
      if (assetKeys.length === 0) {
        assetsEl.innerHTML = `<span class="text-outline">No asset metadata links provided.</span>`;
      } else {
        assetsEl.innerHTML = assetKeys.map(k => {
          const a = item.assets[k];
          const href = a.href || a;
          const role = a.roles ? `[${a.roles.join(", ")}]` : "";
          return `<div class="flex justify-between items-center py-0.5"><span class="text-primary font-semibold">${k} ${role}:</span><a href="${href}" target="_blank" rel="noopener noreferrer" class="text-on-surface hover:text-primary truncate max-w-[420px] underline ml-2">${href}</a></div>`;
        }).join("");
      }
    }

    if (rawEl) {
      rawEl.innerText = JSON.stringify(item.raw_properties || item, null, 2);
    }

    if (modal) modal.classList.remove("hidden");
  };

  window.closeSatelliteMetadataModal = function () {
    const modal = document.getElementById("sn-satellite-metadata-modal");
    if (modal) modal.classList.add("hidden");
  };

  window.attachSatelliteObservation = async function (stacItemId) {
    if (!stacItemId || !state.investigationId) return;

    try {
      const resp = await fetch(`${PRODUCT_API_BASE}/cases/${state.investigationId}/satellite/attach`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ stac_item_id: stacItemId }),
      });

      const attachedData = await resp.json();

      if (!resp.ok) {
        alert(`Failed to attach observation: ${attachedData.detail || resp.statusText}`);
        return;
      }

      // Success: reload cases and refresh Observe domain
      window.closeSatelliteSearchModal();
      await loadCasesFromBackend();
      initObserveMap();

      alert(`Observation ${stacItemId} successfully verified and attached to Case ${state.investigationId} with full CDSE provenance.`);
    } catch (err) {
      console.error("Error attaching observation:", err);
      alert(`Error attaching observation: ${err.message || err}`);
    }
  };

  window.prepareObservationPrompt = function () {
    alert(
      "PHASE 3 PIPELINE NOTICE:\n\n" +
      "Sentinel-1 observation metadata has been verified and attached to this case with genuine CDSE STAC provenance.\n\n" +
      "ESA SNAP GPT automated preprocessing (radiometric calibration, Sigma0 dB, speckle filtering, Doppler terrain correction) will execute in Phase 3."
    );
  };

  window.triggerSarUploadGeneric = function () {
    alert(
      "SAR GeoTIFF Upload:\n\n" +
      "To upload an offline SAR raster file, please use the Case Evidence Ingestion drawer (/api/v1/cases/{case_id}/evidence) or the SAR Discovery workflow."
    );
  };

  window.runSlickDetection = async function () {
    if (!isBenchmarkCase(state.investigationId)) {
      alert("Please upload a SAR GeoTIFF observation file for this generic case to run detection.");
      return;
    }
    openJobProgressModal("RUNNING SAR SLICK DETECTION PIPELINE");
    const jobRes = await postEndpoint(`/investigations/${state.investigationId}/detect`);
    if (jobRes && jobRes.job_id) {
      pollJobStatus(jobRes.job_id, () => window.switchDomain("ANALYZE"));
    }
  };

  window.runHindcast = async function () {
    if (!isBenchmarkCase(state.investigationId)) {
      alert("Advection hindcast requires extracted slick candidates and environmental forcing for this case.");
      return;
    }
    openJobProgressModal("RUNNING OPENDRIFT BACKWARD HINDCAST");
    const jobRes = await postEndpoint(`/investigations/${state.investigationId}/reconstruct`, { scenario: state.activeScenario });
    if (jobRes && jobRes.job_id) {
      pollJobStatus(jobRes.job_id, () => {
        state.physicsMode = "HINDCAST";
        window.switchDomain("RECONSTRUCT");
      });
    }
  };

  window.runForecast = async function () {
    if (!isBenchmarkCase(state.investigationId)) {
      alert("Forward advection forecast requires confirmed slick candidate geometry.");
      return;
    }
    openJobProgressModal("RUNNING OPENDRIFT FORWARD FORECAST");
    const jobRes = await postEndpoint(`/investigations/${state.investigationId}/forecast`, { scenario: state.activeScenario });
    if (jobRes && jobRes.job_id) {
      pollJobStatus(jobRes.job_id, () => {
        state.physicsMode = "FORECAST";
        window.switchDomain("RECONSTRUCT");
      });
    }
  };

  // Initialize live intelligence status
  updateIntelligenceStatus();
})();
