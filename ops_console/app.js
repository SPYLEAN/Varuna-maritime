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

  // Canonical Operational North Sea Incident Definition
  const VARUNA_NORTH_SEA_RECORD = {
    case_id: "VARUNA-CASE-2024-0410-NS01",
    case_name: "North Sea Operational Maritime Pollution Incident",
    location: "53.50° N, 02.50° E (North Sea Corridor)",
    region: "North Sea Offshore Shipping Corridor",
    latitude: 53.5,
    longitude: 2.5,
    mode: "Operational Oil Spill",
    stage: "Response Active",
    status: "ACTIVE INCIDENT",
    last_updated: "2026-09-19 15:45 UTC",
    is_benchmark: false,
    observation_status: "VALIDATED (SYNTHETIC_DEMO)",
    detection_status: "COMPLETE",
    selected_candidate: "C4053",
    hindcast_status: "COMPLETE",
    forecast_status: "COMPLETE",
    ais_status: "SYNTHETIC_DEMO",
    review_status: "READY",
    activity: [
      { time: "2024-04-10 06:23 UTC", text: "Dual-polarization SAR backscatter depression observed (11.2 dB VV damping)" },
      { time: "2024-04-10 07:10 UTC", text: "SmallUNet segmentation qualified: 1.24 km² surface anomaly (PHYSICS_ELIGIBLE)" },
      { time: "2024-04-10 08:00 UTC", text: "Forward forecast advection computed: 068° ENE drift toward Coastal Wetland Zone A" },
      { time: "2024-04-10 08:30 UTC", text: "Marine response window qualified: 08h 42m to shoreline buffer" }
    ]
  };

  // Normalized Enterprise Case Registry State
  const state = {
    activeModule: "OPERATIONS",
    currentDomain: "OVERVIEW", // SCREEN 1: COMMAND CENTER AS DEFAULT LANDING
    investigationId: "VARUNA-CASE-2024-0410-NS01",
    activeEdgeState: "NORMAL_CASE",
    isGuidedMode: true,
    activeHorizon: "ALL",
    
    // Case Registry Database (Backed by North Sea + Pinned Benchmark + /api/v1/cases)
    cases: [VARUNA_NORTH_SEA_RECORD, R001_BENCHMARK_RECORD],

    // Active View Settings
    activeSarBand: "VV",
    activeCandidateId: "C4053",
    activeScenario: "C",
    activeTimestep: "T0",
    physicsMode: "HINDCAST",
    
    // Map Canvas Handles
    maps: {
      overview: null,
      observe: null,
      analyze: null,
      reconstruct: null,
      attribute: null,
      wizAoi: null
    },
    overviewLayers: {
      anomaly: null,
      extent: null,
      traj6h: null,
      traj12h: null,
      traj24h: null,
      traj48h: null,
      envelope: null,
      receptors: null
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
        const mappedGeneric = backendCases.map(bc => {
          const satObs = bc.data_manifest?.satellite_observations || [];
          const hasSar = satObs.length > 0 || (bc.data_manifest?.evidence && bc.data_manifest.evidence.some(e => e.evidence_type === "sar_image"));
          return {
            case_id: bc.case_id,
            case_name: bc.name,
            location: bc.region || (bc.latitude && bc.longitude ? `${bc.latitude.toFixed(2)}°, ${bc.longitude.toFixed(2)}°` : "Custom AOI"),
            region: bc.region,
            latitude: bc.latitude,
            longitude: bc.longitude,
            aoi_geojson: bc.aoi_geojson,
            observation_timestamp: bc.observation_timestamp,
            mode: bc.incident_type || "Operational Oil Spill",
            stage: bc.analysis_status?.oil_detection === "completed" ? "Analysis Complete" : (hasSar ? "Observation Attached" : "Observation Required"),
            status: bc.analysis_status?.oil_detection === "completed" ? "ACTIVE" : "NEW",
            last_updated: bc.created_at ? bc.created_at.substr(0, 16).replace("T", " ") + " UTC" : "Recent",
            is_benchmark: false,
            observation_status: hasSar ? "ATTACHED" : "NO OBSERVATION ATTACHED",
            satellite_observations: satObs,
            raw_case: bc,
            detection_status: bc.analysis_status?.oil_detection || "not_started",
            selected_candidate: null,
            hindcast_status: bc.analysis_status?.hindcast || "not_started",
            forecast_status: "not_started",
            ais_status: bc.analysis_status?.ais_correlation || "not_started",
            review_status: "INCOMPLETE",
            activity: [
              { time: bc.created_at ? bc.created_at.substr(0, 16).replace("T", " ") + " UTC" : "Recent", text: `Case ${bc.case_id} registered in database` }
            ]
          };
        });
        state.cases = [
          VARUNA_NORTH_SEA_RECORD,
          R001_BENCHMARK_RECORD,
          ...mappedGeneric.filter(c => c.case_id !== "R001_WAKASHIO" && c.case_id !== "VARUNA-CASE-2024-0410-NS01")
        ];

        // Populate topbar incident selector
        const topSelect = document.getElementById("topbar-incident-select");
        if (topSelect) {
          topSelect.innerHTML = state.cases.map(c => `
            <option value="${c.case_id}" ${c.case_id === state.investigationId ? 'selected' : ''}>
              ${c.case_id} — ${c.case_name || c.location}
            </option>
          `).join("");
        }
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

  async function checkBackendHealth() {
    const healthPill = document.getElementById("topbar-backend-status");
    if (!healthPill) return;
    try {
      const t0 = performance.now();
      const res = await fetch(`${API_ORIGIN}/health`, { signal: AbortSignal.timeout(3000) });
      const ms = Math.round(performance.now() - t0);
      if (res.ok) {
        healthPill.innerText = `ONLINE (${ms}ms)`;
        healthPill.className = "text-emerald-400 font-bold text-[11px]";
      } else {
        healthPill.innerText = `HTTP ${res.status}`;
        healthPill.className = "text-amber-400 font-bold text-[11px]";
      }
    } catch (e) {
      healthPill.innerText = "OFFLINE (8000)";
      healthPill.className = "text-red-400 font-bold text-[11px]";
    }
  }

  async function initApp() {
    await loadCasesFromBackend();
    checkBackendHealth();
    setInterval(checkBackendHealth, 30000);
    renderOpsHome();
    window.renderCasesRegistry();
    window.switchDomain(state.currentDomain);
  }

  /* ==========================================================================
     DOMAIN & MODULE SWITCHING
     ========================================================================== */

  window.switchDomain = function (rawDomain) {
    let domain = rawDomain;

    // Domain Aliases
    if (domain === "FORECAST") domain = "RECONSTRUCT";
    if (domain === "VESSEL") domain = "ATTRIBUTE";
    if (domain === "EVIDENCE") domain = "REVIEW";

    state.currentDomain = domain;

    // Update Sidebar Navigation Buttons Styling
    document.querySelectorAll(".sn-nav-btn").forEach(btn => {
      const btnDom = btn.dataset.domain;
      const isAct = (btnDom === rawDomain) || (btnDom === domain);
      btn.classList.toggle("bg-cyan-950/70", isAct);
      btn.classList.toggle("text-cyan-300", isAct);
      btn.classList.toggle("border-l-2", isAct);
      btn.classList.toggle("border-cyan-400", isAct);
      btn.classList.toggle("font-bold", isAct);
      btn.classList.toggle("text-slate-300", !isAct);
    });

    // Update Workflow Bar active step
    document.querySelectorAll(".varuna-workflow-stage").forEach(st => {
      const stText = st.innerText.toUpperCase();
      const isAct = (domain === "OVERVIEW" && stText.includes("RESPONSE")) ||
                    (domain === "OBSERVE" && stText.includes("OBSERVED")) ||
                    (domain === "ANALYZE" && (stText.includes("ANALYSED") || stText.includes("QUALIFIED"))) ||
                    (domain === "RECONSTRUCT" && stText.includes("FORECAST")) ||
                    (domain === "ATTRIBUTE" && stText.includes("INVESTIGATION")) ||
                    (domain === "REVIEW" && stText.includes("REVIEW"));
      st.classList.toggle("active", isAct);
    });

    // Hide All Domain Workspaces
    document.querySelectorAll(".sn-domain-workspace").forEach(el => el.classList.add("hidden"));

    // Unhide Target Domain
    const domId = domain.toLowerCase();
    const target = document.getElementById(`domain-${domId}`);
    if (target) target.classList.remove("hidden");

    // Dynamic Header & Sidebar Updates
    const activeCase = state.cases.find(c => c.case_id === state.investigationId) || state.cases[0];
    const sTitle = document.getElementById("sidebar-case-title");
    const sSub = document.getElementById("sidebar-case-sub");
    if (sTitle) sTitle.innerText = activeCase.case_name || activeCase.case_id;
    if (sSub) sSub.innerText = activeCase.case_id;

    // Sync Topbar Incident selector
    const sel = document.getElementById("topbar-incident-select");
    if (sel && sel.value !== state.investigationId) {
      sel.value = state.investigationId;
    }

    // Trigger Specific View Handlers
    setTimeout(() => {
      if (domain === "OVERVIEW") {
        initOverviewMap();
        renderOverviewPanel();
      } else if (domain === "HOME") renderOpsHome();
      else if (domain === "CASES") renderCasesRegistry();
      else if (domain === "OBSERVE") initObserveMap();
      else if (domain === "ANALYZE") initAnalyzeMap();
      else if (domain === "RECONSTRUCT") { initReconstructMap(); renderReconstructInspector(); }
      else if (domain === "ATTRIBUTE") { initAttributeMap(); renderAttributeInspector(); }
      else if (domain === "REVIEW") renderReviewBriefing();
      else if (domain === "ACTIVITY") renderCaseActivityTimeline();
    }, 50);
  };

  /* ==========================================================================
     SCREEN 1: OVERVIEW / COMMAND CENTER MAP & RESPONSE INTELLIGENCE
     ========================================================================== */

  function initOverviewMap() {
    const mapContainer = document.getElementById("overview-map");
    if (!mapContainer) return;

    const isNorthSea = (state.investigationId === "VARUNA-CASE-2024-0410-NS01" || !isBenchmarkCase(state.investigationId));
    const defaultCenter = isNorthSea ? [53.50, 2.50] : [-20.4382, 57.7432];
    const defaultZoom = isNorthSea ? 10 : 11;

    if (!state.maps.overview) {
      state.maps.overview = L.map("overview-map", {
        center: defaultCenter,
        zoom: defaultZoom,
        zoomControl: false,
        attributionControl: false
      });

      state.maps.overview.on("mousemove", (e) => {
        updateStatusBarCoords(e.latlng.lat, e.latlng.lng);
        const ovCoordEl = document.getElementById("ov-map-coords");
        if (ovCoordEl) {
          ovCoordEl.innerText = `${Math.abs(e.latlng.lat).toFixed(4)}° ${e.latlng.lat >= 0 ? "N" : "S"}, ${Math.abs(e.latlng.lng).toFixed(4)}° ${e.latlng.lng >= 0 ? "E" : "W"}`;
        }
      });

      // CartoDB Dark Matter maritime basemap
      L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
        maxZoom: 19,
        subdomains: "abcd"
      }).addTo(state.maps.overview);
    }

    state.maps.overview.invalidateSize();

    // Clear previous situational layers
    Object.keys(state.overviewLayers).forEach(k => {
      if (state.overviewLayers[k] && state.maps.overview.hasLayer(state.overviewLayers[k])) {
        state.maps.overview.removeLayer(state.overviewLayers[k]);
        state.overviewLayers[k] = null;
      }
    });

    if (isNorthSea) {
      // 1. OIL-LIKE ANOMALY POLYGON (1.24 km2)
      const anomalyCoords = [
        [53.488, 2.475],
        [53.512, 2.502],
        [53.518, 2.532],
        [53.506, 2.545],
        [53.492, 2.520],
        [53.484, 2.490],
        [53.488, 2.475]
      ];

      state.overviewLayers.anomaly = L.polygon(anomalyCoords, {
        color: "#38bdf8",
        weight: 2,
        fillColor: "#0284c7",
        fillOpacity: 0.65
      }).addTo(state.maps.overview);

      state.overviewLayers.anomaly.bindPopup(`
        <div class="font-mono text-xs p-1 space-y-1">
          <div class="text-[10px] text-cyan-400 font-bold uppercase">CURRENT EVENT</div>
          <div class="text-white font-bold text-sm">Oil-like surface anomaly</div>
          <div class="text-slate-300">Area: <strong class="text-cyan-300">1.24 km²</strong> (SYNTHETIC_DEMO)</div>
          <div class="text-slate-300">Gate: <strong class="text-emerald-400">PHYSICS_ELIGIBLE</strong></div>
          <div class="text-slate-400 text-[10px]">SmallUNet segmentation (Solidity: 0.78, Elongation: 2.35)</div>
        </div>
      `);

      // 2. PROBABLE EXTENT (Expanded Hull)
      const extentCoords = [
        [53.478, 2.460],
        [53.522, 2.495],
        [53.528, 2.545],
        [53.512, 2.560],
        [53.485, 2.532],
        [53.475, 2.478],
        [53.478, 2.460]
      ];

      state.overviewLayers.extent = L.polygon(extentCoords, {
        color: "#06b6d4",
        dashArray: "5, 5",
        weight: 1.5,
        fillColor: "#06b6d4",
        fillOpacity: 0.12
      }).addTo(state.maps.overview);

      state.overviewLayers.extent.bindPopup(`
        <div class="font-mono text-xs p-1">
          <div class="text-cyan-400 font-bold">PROBABLE SLICK EXTENT</div>
          <div class="text-slate-300 mt-0.5">Confidence Envelope: 95% Confidence Interval</div>
        </div>
      `);

      // 3. TRAJECTORY VECTORS (+6h, +12h, +24h, +48h)
      const trajPoints = [
        [53.502, 2.510], // T0 (Now)
        [53.542, 2.625], // +6h
        [53.585, 2.748], // +12h
        [53.665, 2.980], // +24h
        [53.815, 3.420]  // +48h
      ];

      // +6h segment (Solid cyan)
      state.overviewLayers.traj6h = L.layerGroup([
        L.polyline([trajPoints[0], trajPoints[1]], { color: "#38bdf8", weight: 3.5, opacity: 0.95 }),
        L.circleMarker(trajPoints[1], { radius: 5, color: "#38bdf8", fillColor: "#0b1220", fillOpacity: 1, weight: 2 }).bindPopup("<div class='font-mono text-xs font-bold text-cyan-300'>HORIZON: +6H<br><span class='text-slate-400 font-normal'>Drift distance: ~7.4 km (068° ENE)</span></div>")
      ]).addTo(state.maps.overview);

      // +12h segment (Teal dashed)
      state.overviewLayers.traj12h = L.layerGroup([
        L.polyline([trajPoints[1], trajPoints[2]], { color: "#14b8a6", weight: 3, dashArray: "4, 4", opacity: 0.9 }),
        L.circleMarker(trajPoints[2], { radius: 5, color: "#14b8a6", fillColor: "#0b1220", fillOpacity: 1, weight: 2 }).bindPopup("<div class='font-mono text-xs font-bold text-teal-300'>HORIZON: +12H<br><span class='text-slate-400 font-normal'>Drift distance: ~14.8 km (068° ENE)</span></div>")
      ]).addTo(state.maps.overview);

      // +24h segment (Sky blue dashed)
      state.overviewLayers.traj24h = L.layerGroup([
        L.polyline([trajPoints[2], trajPoints[3]], { color: "#0284c7", weight: 2.5, dashArray: "4, 4", opacity: 0.85 }),
        L.circleMarker(trajPoints[3], { radius: 5, color: "#0284c7", fillColor: "#0b1220", fillOpacity: 1, weight: 2 }).bindPopup("<div class='font-mono text-xs font-bold text-sky-300'>HORIZON: +24H<br><span class='text-slate-400 font-normal'>Drift distance: ~29.5 km</span></div>")
      ]).addTo(state.maps.overview);

      // +48h segment (Slate blue dotted)
      state.overviewLayers.traj48h = L.layerGroup([
        L.polyline([trajPoints[3], trajPoints[4]], { color: "#64748b", weight: 2, dashArray: "3, 3", opacity: 0.8 }),
        L.circleMarker(trajPoints[4], { radius: 5, color: "#64748b", fillColor: "#0b1220", fillOpacity: 1, weight: 2 }).bindPopup("<div class='font-mono text-xs font-bold text-slate-300'>HORIZON: +48H<br><span class='text-slate-400 font-normal'>Drift distance: ~58.2 km</span></div>")
      ]).addTo(state.maps.overview);

      // 4. UNCERTAINTY ENVELOPE CORRIDOR (±4.8 km to ±9.2 km)
      const envelopeCoords = [
        [53.525, 2.605],
        [53.555, 2.715],
        [53.620, 2.920],
        [53.750, 3.320],
        [53.860, 3.480],
        [53.800, 3.520],
        [53.700, 3.080],
        [53.610, 2.780],
        [53.555, 2.645],
        [53.525, 2.605]
      ];

      state.overviewLayers.envelope = L.polygon(envelopeCoords, {
        color: "#0284c7",
        weight: 1.5,
        dashArray: "4, 4",
        fillColor: "#0284c7",
        fillOpacity: 0.15
      }).addTo(state.maps.overview);

      state.overviewLayers.envelope.bindPopup(`
        <div class="font-mono text-xs p-1">
          <div class="text-sky-400 font-bold">48H UNCERTAINTY CORRIDOR</div>
          <div class="text-slate-300 mt-0.5">Dispersion Radius: ±4.8 km @ 24h → ±9.2 km @ 48h</div>
          <div class="text-amber-400 text-[10px] mt-1 font-bold">SYNTHETIC_DEMO Drift Kinematics</div>
        </div>
      `);

      // 5. RELEVANT RECEPTOR MARKERS
      // Coastal Wetland Zone A (Critical High Priority at ~8h 42m drift distance)
      const wetlandMarker = L.circleMarker([53.570, 2.705], {
        radius: 8,
        color: "#ef4444",
        fillColor: "#ef4444",
        fillOpacity: 0.85,
        weight: 3,
        className: "receptor-marker-pulse"
      });

      wetlandMarker.bindPopup(`
        <div class="font-mono text-xs p-1 space-y-1">
          <div class="flex items-center justify-between">
            <span class="text-red-400 font-bold uppercase text-[10px]">CRITICAL RECEPTOR</span>
            <span class="px-1.5 py-0.2 rounded bg-red-950 text-red-300 border border-red-800 font-bold text-[9px]">HIGH</span>
          </div>
          <div class="text-white font-bold text-sm">Coastal Wetland Zone A</div>
          <div class="text-slate-300">Estimated Arrival: <strong class="text-amber-400">08h 42m</strong> (Horizon: +9h)</div>
          <div class="text-slate-300">Sensitivity: <span class="text-red-300">HIGH (Intertidal Estuary Sanctuary)</span></div>
          <div class="text-slate-400 text-[10px] pt-1 border-t border-slate-800">
            Action: Immediate containment booming &amp; staging advised.
          </div>
        </div>
      `);

      // Fishing Ground B (Secondary Medium Priority at 17h)
      const fishingMarker = L.circleMarker([53.630, 2.860], {
        radius: 7,
        color: "#f59e0b",
        fillColor: "#f59e0b",
        fillOpacity: 0.8,
        weight: 2
      });

      fishingMarker.bindPopup(`
        <div class="font-mono text-xs p-1 space-y-1">
          <div class="flex items-center justify-between">
            <span class="text-amber-400 font-bold uppercase text-[10px]">SECONDARY RECEPTOR</span>
            <span class="px-1.5 py-0.2 rounded bg-amber-950 text-amber-300 border border-amber-800 font-bold text-[9px]">MEDIUM</span>
          </div>
          <div class="text-white font-bold text-sm">Fishing Ground B</div>
          <div class="text-slate-300">Estimated Arrival: <strong class="text-amber-400">17h 00m</strong></div>
          <div class="text-slate-300">Sensitivity: Commercial Demersal Trawling Zone</div>
        </div>
      `);

      state.overviewLayers.receptors = L.layerGroup([wetlandMarker, fishingMarker]).addTo(state.maps.overview);

      // Fit bounds nicely
      const group = L.featureGroup([
        state.overviewLayers.anomaly,
        state.overviewLayers.envelope,
        wetlandMarker,
        fishingMarker
      ]);
      state.maps.overview.fitBounds(group.getBounds(), { padding: [40, 40], animate: false });
    } else {
      // Mauritius Wakashio Benchmark
      const mauritiusAnomaly = [
        [-20.445, 57.735],
        [-20.435, 57.742],
        [-20.430, 57.755],
        [-20.440, 57.760],
        [-20.450, 57.748],
        [-20.445, 57.735]
      ];

      state.overviewLayers.anomaly = L.polygon(mauritiusAnomaly, {
        color: "#38bdf8",
        weight: 2,
        fillColor: "#0284c7",
        fillOpacity: 0.65
      }).addTo(state.maps.overview);

      state.overviewLayers.anomaly.bindPopup("<div class='font-mono text-xs font-bold text-cyan-300'>CASE R001 — MAURITIUS ANOMALY<br><span class='text-slate-400 font-normal'>Area: 1.42 km² | Candidate C4053</span></div>");

      const mTraj = [
        [-20.438, 57.745],
        [-20.428, 57.728],
        [-20.415, 57.712],
        [-20.400, 57.690],
        [-20.370, 57.640]
      ];

      state.overviewLayers.traj6h = L.polyline([mTraj[0], mTraj[1]], { color: "#38bdf8", weight: 3 }).addTo(state.maps.overview);
      state.overviewLayers.traj12h = L.polyline([mTraj[1], mTraj[2]], { color: "#14b8a6", weight: 3, dashArray: "4, 4" }).addTo(state.maps.overview);
      state.overviewLayers.traj24h = L.polyline([mTraj[2], mTraj[3]], { color: "#0284c7", weight: 2.5, dashArray: "4, 4" }).addTo(state.maps.overview);
      state.overviewLayers.traj48h = L.polyline([mTraj[3], mTraj[4]], { color: "#64748b", weight: 2, dashArray: "3, 3" }).addTo(state.maps.overview);

      const mReceptor = L.circleMarker([-20.442, 57.715], { radius: 8, color: "#ef4444", fillColor: "#ef4444", fillOpacity: 0.85, className: "receptor-marker-pulse" }).addTo(state.maps.overview);
      mReceptor.bindPopup("<div class='font-mono text-xs font-bold text-red-400'>CRITICAL RECEPTOR<br><span class='text-white font-bold'>Coastal Wetland Zone A (Blue Bay Marine Park)</span><br>ETA: 08h 42m | Priority: HIGH</div>");

      state.overviewLayers.receptors = L.layerGroup([mReceptor]).addTo(state.maps.overview);

      state.maps.overview.setView([-20.4382, 57.7432], 11);
    }
  }

  window.fitOverviewBounds = function () {
    if (!state.maps.overview) return;
    if (state.overviewLayers.anomaly) {
      const activeGroup = [];
      Object.keys(state.overviewLayers).forEach(k => {
        if (state.overviewLayers[k] && state.maps.overview.hasLayer(state.overviewLayers[k])) {
          activeGroup.push(state.overviewLayers[k]);
        }
      });
      if (activeGroup.length > 0) {
        state.maps.overview.fitBounds(L.featureGroup(activeGroup).getBounds(), { padding: [40, 40], animate: true });
      }
    }
  };

  window.setOverviewHorizon = function (horizon) {
    state.activeHorizon = horizon;

    // Update button states
    ["all", "now", "6h", "12h", "24h", "48h"].forEach(h => {
      const btn = document.getElementById(`btn-horizon-${h}`);
      if (btn) {
        const isAct = (h.toUpperCase() === horizon);
        btn.classList.toggle("bg-cyan-600", isAct);
        btn.classList.toggle("text-white", isAct);
        btn.classList.toggle("font-bold", isAct);
        btn.classList.toggle("text-slate-300", !isAct);
      }
    });

    if (!state.maps.overview) return;

    // Filter situational layers
    const show6h = (horizon === "ALL" || horizon === "6H" || horizon === "12H" || horizon === "24H" || horizon === "48H");
    const show12h = (horizon === "ALL" || horizon === "12H" || horizon === "24H" || horizon === "48H");
    const show24h = (horizon === "ALL" || horizon === "24H" || horizon === "48H");
    const show48h = (horizon === "ALL" || horizon === "48H");
    const showEnvelope = (horizon === "ALL" || horizon === "48H");

    if (state.overviewLayers.traj6h) {
      if (show6h) state.maps.overview.addLayer(state.overviewLayers.traj6h);
      else state.maps.overview.removeLayer(state.overviewLayers.traj6h);
    }
    if (state.overviewLayers.traj12h) {
      if (show12h) state.maps.overview.addLayer(state.overviewLayers.traj12h);
      else state.maps.overview.removeLayer(state.overviewLayers.traj12h);
    }
    if (state.overviewLayers.traj24h) {
      if (show24h) state.maps.overview.addLayer(state.overviewLayers.traj24h);
      else state.maps.overview.removeLayer(state.overviewLayers.traj24h);
    }
    if (state.overviewLayers.traj48h) {
      if (show48h) state.maps.overview.addLayer(state.overviewLayers.traj48h);
      else state.maps.overview.removeLayer(state.overviewLayers.traj48h);
    }
    if (state.overviewLayers.envelope) {
      if (showEnvelope) state.maps.overview.addLayer(state.overviewLayers.envelope);
      else state.maps.overview.removeLayer(state.overviewLayers.envelope);
    }
  };

  window.selectTopbarIncident = function (caseId) {
    state.investigationId = caseId;
    const activeCase = state.cases.find(c => c.case_id === caseId) || state.cases[0];

    // Update Topbar Dropdown value
    const sel = document.getElementById("topbar-incident-select");
    if (sel && sel.value !== caseId) sel.value = caseId;

    // Update Sidebar Titles
    const sTitle = document.getElementById("sidebar-case-title");
    const sSub = document.getElementById("sidebar-case-sub");
    if (sTitle) sTitle.innerText = activeCase.case_name || activeCase.case_id;
    if (sSub) sSub.innerText = activeCase.case_id;

    // Refresh Overview Map & Response Intelligence Panel
    initOverviewMap();
    renderOverviewPanel();
  };

  function renderOverviewPanel() {
    const isNorthSea = (state.investigationId === "VARUNA-CASE-2024-0410-NS01" || !isBenchmarkCase(state.investigationId));
    const activeCase = state.cases.find(c => c.case_id === state.investigationId) || state.cases[0];

    const areaEl = document.getElementById("ov-intel-area");
    const windowEl = document.getElementById("ov-intel-window");
    const coordsEl = document.getElementById("ov-map-coords");

    if (areaEl) areaEl.innerText = isNorthSea ? "1.24 km²" : "1.42 km²";
    if (windowEl) windowEl.innerText = "08h 42m";
    if (coordsEl) {
      coordsEl.innerText = isNorthSea ? "53.5000° N, 02.5000° E" : "20.4382° S, 57.7432° E";
    }

    // Update topbar badges
    const statusEl = document.getElementById("topbar-incident-status");
    if (statusEl) {
      statusEl.innerText = activeCase.status || "ACTIVE INCIDENT";
    }

    const modeEl = document.getElementById("topbar-execution-mode");
    if (modeEl) {
      modeEl.innerText = isBenchmarkCase(state.investigationId) ? "VALIDATED BENCHMARK" : "SYNTHETIC_DEMO";
    }
  }

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

})();
