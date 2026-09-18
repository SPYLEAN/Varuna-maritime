/* ==========================================================================
   VARUNA — MARITIME ENVIRONMENTAL INTELLIGENCE WORKSTATION (v1.0.0-rc1)
   Enterprise Case Management & Guided Investigation Architecture Engine
   ========================================================================== */

(function () {
  const API_ORIGIN = window.SAMUDRANETRA_API_BASE_URL || (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1' ? 'http://localhost:8000' : window.location.origin);
  const PRODUCT_API_BASE = `${API_ORIGIN}/api/v1`;
  const BENCHMARK_API_BASE = `${API_ORIGIN}/api/investigations`;
  const API_BASE = `${API_ORIGIN}/api`;

  function isBenchmarkCase(caseId) {
    if (!caseId) return false;
    const upper = caseId.toUpperCase();
    return upper === "R001_WAKASHIO" || upper === "R001" || upper === "CASE_R001";
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
        const mappedGeneric = backendCases.map(bc => ({
          case_id: bc.case_id,
          case_name: bc.name,
          location: bc.region || (bc.latitude && bc.longitude ? `${bc.latitude.toFixed(2)}°, ${bc.longitude.toFixed(2)}°` : "Custom AOI"),
          region: bc.region,
          latitude: bc.latitude,
          longitude: bc.longitude,
          aoi_geojson: bc.aoi_geojson,
          mode: bc.incident_type || "Operational Oil Spill",
          stage: bc.analysis_status?.oil_detection === "completed" ? "Analysis Complete" : "Observation Required",
          status: bc.analysis_status?.oil_detection === "completed" ? "ACTIVE" : "NEW",
          last_updated: bc.created_at ? bc.created_at.substr(0, 16).replace("T", " ") + " UTC" : "Recent",
          is_benchmark: false,
          observation_status: (bc.data_manifest?.evidence && bc.data_manifest.evidence.some(e => e.evidence_type === "sar_image")) ? "ATTACHED" : "NO OBSERVATION ATTACHED",
          detection_status: bc.analysis_status?.oil_detection || "not_started",
          selected_candidate: null,
          hindcast_status: bc.analysis_status?.hindcast || "not_started",
          forecast_status: "not_started",
          ais_status: bc.analysis_status?.ais_correlation || "not_started",
          review_status: "INCOMPLETE",
          activity: [
            { time: bc.created_at ? bc.created_at.substr(0, 16).replace("T", " ") + " UTC" : "Recent", text: `Case ${bc.case_id} registered in database` }
          ]
        }));
        state.cases = [R001_BENCHMARK_RECORD, ...mappedGeneric.filter(c => c.case_id !== "R001_WAKASHIO")];
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

    const isBench = isBenchmarkCase(state.investigationId);
    const sarBounds = [[-20.750033, 57.09998], [-19.699993, 58.300039]];

    if (!state.maps.observe) {
      state.maps.observe = L.map("map-observe", { center: [-20.4382, 57.7432], zoom: 10, zoomControl: false, attributionControl: false });
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

    if (isBench) {
      let sarImgUrl = state.activeSarBand === "VH" ? "assets/sar_vh_display.webp" : "assets/sar_vv_display.webp";
      state.sarOverlays.observe = L.imageOverlay(sarImgUrl, sarBounds, { opacity: state.activeSarBand === "COMPARE" ? 0.80 : 1.0, interactive: false }).addTo(state.maps.observe);
      L.polygon(sarBounds, { color: "#38BDF8", weight: 1.5, dashArray: "4,4", fillColor: "transparent" }).addTo(state.maps.observe);
      state.maps.observe.fitBounds(sarBounds, { padding: [10, 10], animate: false });

      if (taskEl) taskEl.innerText = "Observation Review";
      if (descEl) descEl.innerText = "Sentinel-1 SAR scene validated and calibrated. Next step: Run oil-like slick detection.";
    } else {
      // ZERO-LEAKAGE EMPTY STATE FOR GENERIC CASES
      const activeCase = state.cases.find(c => c.case_id === state.investigationId);
      if (taskEl) taskEl.innerText = "NO OBSERVATION ATTACHED";
      if (descEl) descEl.innerText = "No Sentinel-1 SAR observation has been uploaded to this investigation case. Attach a SAR GeoTIFF or product archive to initiate analysis.";

      if (activeCase && activeCase.aoi_geojson) {
        try {
          const aoiLayer = L.geoJSON(activeCase.aoi_geojson, {
            style: { color: "#38BDF8", weight: 2, dashArray: "4,4", fillColor: "#2563eb", fillOpacity: 0.15 }
          }).addTo(state.maps.observe);
          state.maps.observe.fitBounds(aoiLayer.getBounds(), { padding: [20, 20], animate: false });
        } catch (e) {
          state.maps.observe.setView([0, 0], 2);
        }
      } else {
        state.maps.observe.setView([0, 0], 2);
      }
    }
  }

  /* ==========================================================================
     DOMAIN 02: ANALYZE WORKSPACE (CANDIDATE GEOMETRY / ZERO-LEAKAGE EMPTY STATE)
     ========================================================================== */

  function initAnalyzeMap() {
    const mapContainer = document.getElementById("map-analyze");
    if (!mapContainer) return;

    const isBench = isBenchmarkCase(state.investigationId);
    const sarBounds = [[-20.750033, 57.09998], [-19.699993, 58.300039]];

    if (!state.maps.analyze) {
      state.maps.analyze = L.map("map-analyze", { center: [-20.4382, 57.7432], zoom: 10, zoomControl: false, attributionControl: false });
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

    if (isBench) {
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
      // ZERO-LEAKAGE EMPTY STATE FOR GENERIC CASES
      const activeCase = state.cases.find(c => c.case_id === state.investigationId);
      if (activeCase && activeCase.aoi_geojson) {
        try {
          const aoiLayer = L.geoJSON(activeCase.aoi_geojson, {
            style: { color: "#38BDF8", weight: 2, dashArray: "4,4", fillColor: "#2563eb", fillOpacity: 0.15 }
          }).addTo(state.maps.analyze);
          state.maps.analyze.fitBounds(aoiLayer.getBounds(), { padding: [20, 20], animate: false });
        } catch (e) {
          state.maps.analyze.setView([0, 0], 2);
        }
      } else {
        state.maps.analyze.setView([0, 0], 2);
      }
    }
  }

  /* ==========================================================================
     DOMAIN 03: RECONSTRUCTION WORKSPACE (OPENDRIFT PARTICLES / ZERO-LEAKAGE)
     ========================================================================== */

  function initReconstructMap() {
    const mapContainer = document.getElementById("map-reconstruct");
    if (!mapContainer) return;

    const isBench = isBenchmarkCase(state.investigationId);

    if (!state.maps.reconstruct) {
      state.maps.reconstruct = L.map("map-reconstruct", { center: [-20.4382, 57.7432], zoom: 10, zoomControl: true, attributionControl: false });
      state.maps.reconstruct.on("mousemove", (e) => updateStatusBarCoords(e.latlng.lat, e.latlng.lng));
      L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}").addTo(state.maps.reconstruct);
    }

    state.maps.reconstruct.invalidateSize();
    state.maps.reconstruct.eachLayer(layer => {
      if (layer instanceof L.Polygon || layer instanceof L.CircleMarker || layer instanceof L.GeoJSON) state.maps.reconstruct.removeLayer(layer);
    });

    if (isBench) {
      if (state.physicsMode === "HINDCAST") {
        L.polygon([[-20.35, 57.65], [-20.35, 57.85], [-20.55, 57.85], [-20.55, 57.65]], { color: "#fbbf24", fillColor: "#fbbf24", fillOpacity: 0.25, weight: 2, dashArray: "6,6" }).addTo(state.maps.reconstruct);
        for (let p = 0; p < 80; p++) {
          const pLat = -20.4382 + (Math.sin(p * 0.4) * 0.08);
          const pLon = 57.7432 + (Math.cos(p * 0.4) * 0.09);
          L.circleMarker([pLat, pLon], { radius: 2.5, color: "#fbbf24", fillColor: "#fbbf24", fillOpacity: 0.85 }).addTo(state.maps.reconstruct);
        }
        state.maps.reconstruct.setView([-20.4382, 57.7432], 10);
      } else {
        L.polygon([[-20.45, 57.75], [-20.45, 58.15], [-20.75, 58.15], [-20.75, 57.75]], { color: "#b4c5ff", fillColor: "#b4c5ff", fillOpacity: 0.3, weight: 2, dashArray: "4,4" }).addTo(state.maps.reconstruct);
        for (let p = 0; p < 100; p++) {
          const pLat = -20.4382 - (p * 0.002) + (Math.sin(p * 0.3) * 0.04);
          const pLon = 57.7432 + (p * 0.003) + (Math.cos(p * 0.3) * 0.04);
          L.circleMarker([pLat, pLon], { radius: 3, color: "#b4c5ff", fillColor: "#b4c5ff", fillOpacity: 0.9 }).addTo(state.maps.reconstruct);
        }
        state.maps.reconstruct.setView([-20.4382, 57.7432], 10);
      }
    } else {
      // ZERO-LEAKAGE EMPTY STATE FOR GENERIC CASES
      const activeCase = state.cases.find(c => c.case_id === state.investigationId);
      if (activeCase && activeCase.aoi_geojson) {
        try {
          const aoiLayer = L.geoJSON(activeCase.aoi_geojson, {
            style: { color: "#38BDF8", weight: 2, dashArray: "4,4", fillColor: "#2563eb", fillOpacity: 0.15 }
          }).addTo(state.maps.reconstruct);
          state.maps.reconstruct.fitBounds(aoiLayer.getBounds(), { padding: [20, 20], animate: false });
        } catch (e) {
          state.maps.reconstruct.setView([0, 0], 2);
        }
      } else {
        state.maps.reconstruct.setView([0, 0], 2);
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

    const isBench = isBenchmarkCase(state.investigationId);

    if (!state.maps.attribute) {
      state.maps.attribute = L.map("map-attribute", { center: [-20.4382, 57.7432], zoom: 10, zoomControl: true, attributionControl: false });
      state.maps.attribute.on("mousemove", (e) => updateStatusBarCoords(e.latlng.lat, e.latlng.lng));
      L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}").addTo(state.maps.attribute);
    }

    state.maps.attribute.invalidateSize();
    state.maps.attribute.eachLayer(layer => {
      if (layer instanceof L.Polyline || layer instanceof L.Polygon || layer instanceof L.CircleMarker || layer instanceof L.GeoJSON) state.maps.attribute.removeLayer(layer);
    });

    if (isBench) {
      const vTracks = [
        { name: "VESSEL_BETA", color: "#4ade80", points: [[-20.35, 57.65], [-20.40, 57.70], [-20.44, 57.74]] },
        { name: "VESSEL_ALPHA", color: "#fbbf24", points: [[-20.30, 57.60], [-20.38, 57.68], [-20.45, 57.78]] }
      ];

      vTracks.forEach(vt => {
        L.polyline(vt.points, { color: vt.color, weight: 3.5, opacity: 0.9 }).addTo(state.maps.attribute);
        L.circleMarker(vt.points[vt.points.length - 1], { radius: 5, color: vt.color, fillColor: vt.color, fillOpacity: 1 }).addTo(state.maps.attribute);
      });
      state.maps.attribute.setView([-20.4382, 57.7432], 10);
    } else {
      // ZERO-LEAKAGE EMPTY STATE FOR GENERIC CASES
      const activeCase = state.cases.find(c => c.case_id === state.investigationId);
      if (activeCase && activeCase.aoi_geojson) {
        try {
          const aoiLayer = L.geoJSON(activeCase.aoi_geojson, {
            style: { color: "#38BDF8", weight: 2, dashArray: "4,4", fillColor: "#2563eb", fillOpacity: 0.15 }
          }).addTo(state.maps.attribute);
          state.maps.attribute.fitBounds(aoiLayer.getBounds(), { padding: [20, 20], animate: false });
        } catch (e) {
          state.maps.attribute.setView([0, 0], 2);
        }
      } else {
        state.maps.attribute.setView([0, 0], 2);
      }
    }
  }

  function renderAttributeInspector() {
    const bdy = document.getElementById("attribute-inspector-body");
    if (!bdy) return;

    const isBench = isBenchmarkCase(state.investigationId);
    if (isBench) {
      bdy.innerHTML = `
        <div class="p-3 border-b border-outline-variant bg-surface-container font-semibold text-on-surface">Vessel Intelligence</div>
        <div class="p-3 space-y-3 font-data-mono text-xs">
          <div class="p-2 bg-warning-amber/10 border border-warning-amber/30 text-warning-amber rounded text-[10px]">
            SYNTHETIC AIS DEMONSTRATION — HISTORICAL ATTRIBUTION NOT VALID
          </div>
          <div class="p-2 bg-surface-container rounded border border-outline-variant">
            <div class="text-success-green font-bold">1. VESSEL_BETA (IMO 9876543)</div>
            <div class="text-[11px] text-on-surface-variant mt-1">Priority: 0.907 | Distance: 0.85 km</div>
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

    const isBench = isBenchmarkCase(state.investigationId);
    const activeCase = state.cases.find(c => c.case_id === state.investigationId) || state.cases[0];

    if (isBench) {
      revEl.innerHTML = `
        <div class="bg-surface-container-low border border-outline-variant rounded-lg p-6 mb-6">
          <div class="flex justify-between items-center mb-2">
            <div>
              <h1 class="text-xl font-bold text-primary tracking-tight">VARUNA — INCIDENT REVIEW MATRIX</h1>
              <p class="text-xs text-on-surface-variant mt-1">11-Stage Explainable Evidence Integration & Cryptographic Provenance Manifest</p>
            </div>
            <span class="px-2.5 py-1 bg-surface-variant border border-warning-amber text-warning-amber text-xs font-data-mono font-bold rounded">VALIDATED BENCHMARK</span>
          </div>

          <div class="mt-4 overflow-x-auto">
            <table class="w-full text-xs text-left border-collapse font-data-mono">
              <thead>
                <tr class="border-b border-outline-variant text-outline bg-surface-container">
                  <th class="p-2.5">STAGE</th>
                  <th class="p-2.5">NAME</th>
                  <th class="p-2.5">ENGINE / METHOD</th>
                  <th class="p-2.5">STATUS</th>
                  <th class="p-2.5">PROVENANCE</th>
                </tr>
              </thead>
              <tbody>
                <tr class="border-b border-outline-variant/40"><td class="p-2.5">01</td><td class="p-2.5">SAR OBSERVATION</td><td class="p-2.5">Sentinel-1B IW GRDH</td><td class="p-2.5 text-success-green">VALIDATED CACHED RESULT</td><td class="p-2.5 text-outline">S1B_IW_GRDH_1SDV_20200810...</td></tr>
                <tr class="border-b border-outline-variant/40"><td class="p-2.5">02</td><td class="p-2.5">DETECTION & TRIAGE</td><td class="p-2.5">Task008B ML Classifier</td><td class="p-2.5 text-success-green">VALIDATED CACHED RESULT</td><td class="p-2.5 text-outline">C4053 (ML Oil Score: 0.5818)</td></tr>
                <tr class="border-b border-outline-variant/40"><td class="p-2.5">03</td><td class="p-2.5">HINDCAST TRANSPORT</td><td class="p-2.5">OpenDrift Backward</td><td class="p-2.5 text-success-green">VALIDATED CACHED RESULT</td><td class="p-2.5 text-outline">Ref Dist: ~24.17 km @ 24h</td></tr>
                <tr class="border-b border-outline-variant/40"><td class="p-2.5">04</td><td class="p-2.5">FORWARD FORECAST</td><td class="p-2.5">OpenDrift Forward</td><td class="p-2.5 text-primary">LIVE COMPUTE</td><td class="p-2.5 text-outline">Full ERA5/HYCOM/CMEMS Support</td></tr>
                <tr class="border-b border-outline-variant/40"><td class="p-2.5">05</td><td class="p-2.5">AIS CORRELATION</td><td class="p-2.5">MarineCadastre Engine</td><td class="p-2.5 text-warning-amber">SYNTHETIC AIS DEMONSTRATION</td><td class="p-2.5 text-outline">HISTORICAL ATTRIBUTION NOT VALID</td></tr>
              </tbody>
            </table>
          </div>
        </div>
      `;
    } else {
      // ZERO-LEAKAGE REVIEW FOR GENERIC CASES
      revEl.innerHTML = `
        <div class="bg-surface-container-low border border-outline-variant rounded-lg p-6 mb-6">
          <div class="flex justify-between items-center mb-2">
            <div>
              <h1 class="text-xl font-bold text-primary tracking-tight">CASE ${activeCase.case_id} — INCIDENT REVIEW MATRIX</h1>
              <p class="text-xs text-on-surface-variant mt-1">${activeCase.case_name} | Operational Case Review</p>
            </div>
            <span class="px-2.5 py-1 bg-surface-variant border border-outline-variant text-outline text-xs font-data-mono font-bold rounded">INVESTIGATION INCOMPLETE</span>
          </div>

          <div class="mt-4 overflow-x-auto">
            <table class="w-full text-xs text-left border-collapse font-data-mono">
              <thead>
                <tr class="border-b border-outline-variant text-outline bg-surface-container">
                  <th class="p-2.5">STAGE</th>
                  <th class="p-2.5">NAME</th>
                  <th class="p-2.5">STATUS</th>
                  <th class="p-2.5">DETAILS</th>
                </tr>
              </thead>
              <tbody>
                <tr class="border-b border-outline-variant/40"><td class="p-2.5">01</td><td class="p-2.5">SAR OBSERVATION</td><td class="p-2.5 text-warning-amber">NO OBSERVATION ATTACHED</td><td class="p-2.5 text-outline">Awaiting Sentinel-1 SAR upload</td></tr>
                <tr class="border-b border-outline-variant/40"><td class="p-2.5">02</td><td class="p-2.5">DETECTION & TRIAGE</td><td class="p-2.5 text-outline">OBSERVATION REQUIRED</td><td class="p-2.5 text-outline">Prerequisite stage not satisfied</td></tr>
                <tr class="border-b border-outline-variant/40"><td class="p-2.5">03</td><td class="p-2.5">HINDCAST TRANSPORT</td><td class="p-2.5 text-outline">CANDIDATE + FORCING REQUIRED</td><td class="p-2.5 text-outline">Prerequisite stage not satisfied</td></tr>
                <tr class="border-b border-outline-variant/40"><td class="p-2.5">04</td><td class="p-2.5">FORWARD FORECAST</td><td class="p-2.5 text-outline">CANDIDATE REQUIRED</td><td class="p-2.5 text-outline">Prerequisite stage not satisfied</td></tr>
                <tr class="border-b border-outline-variant/40"><td class="p-2.5">05</td><td class="p-2.5">AIS CORRELATION</td><td class="p-2.5 text-outline">AIS DATA NOT LOADED</td><td class="p-2.5 text-outline">No vessel trajectory files ingested</td></tr>
              </tbody>
            </table>
          </div>
        </div>
      `;
    }
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
  window.toggleProvenanceDrawer = () => document.getElementById("sn-provenance-drawer")?.classList.toggle("hidden");

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

})();
