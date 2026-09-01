/* ==========================================================================
   SAMUDRANETRA — LIVE OPERATIONAL PROTOTYPE APPLICATION LOGIC
   Operator-Driven Oil Spill Investigation Engine (v0.9.0-rc1)
   ========================================================================== */

(function () {
  const API_BASE = "http://localhost:8000/api";

  const state = {
    activeCaseId: "R001_WAKASHIO",
    activeCaseMode: "VALIDATED BENCHMARK (R001 Wakashio)",
    currentStage: "OBSERVE",
    activeSarBand: "VV",
    activeCandidateId: "C4053",
    activeScenario: "C",
    activeTimestep: "T0",
    physicsMode: "HINDCAST", // 'HINDCAST' or 'FORECAST'
    activeReconstructSubview: "TIMELINE",
    isPlaying: false,
    playbackSpeed: 1,
    playTimer: null,
    activeEdgeState: "NORMAL_CASE",
    aisDataMode: "SYNTHETIC_DEMO",
    map: null,
    layers: {
      footprint: null,
      candidates: null,
      sourceEnvelopes: null,
      particles: null,
      forwardClosure: null,
      forecastDrift: null,
      historicalTruth: null,
      aisTracks: null
    },
    caseData: null,
    vesselsData: [],
    currentJobId: null
  };

  async function fetchEndpoint(endpoint) {
    try {
      const res = await fetch(`${API_BASE}${endpoint}`);
      if (!res.ok) return null;
      return await res.json();
    } catch (e) {
      console.warn(`API call ${endpoint} failed, falling back:`, e);
      return null;
    }
  }

  async function postEndpoint(endpoint, payload = null) {
    try {
      const res = await fetch(`${API_BASE}${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: payload ? JSON.stringify(payload) : JSON.stringify({})
      });
      if (!res.ok) return null;
      return await res.json();
    } catch (e) {
      console.warn(`POST call ${endpoint} failed:`, e);
      return null;
    }
  }

  async function initApp() {
    const data = await fetchEndpoint(`/cases/${state.activeCaseId}`);
    if (data) {
      state.caseData = data;
      state.vesselsData = data.ais?.candidates || [];
      updateApiStatusBadge("READY");
    } else {
      updateApiStatusBadge("OFFLINE");
    }
    initMap();
    renderInspector();
  }

  function updateApiStatusBadge(status) {
    const group = document.querySelector(".sn-status-group");
    if (!group) return;
    if (status === "READY") {
      group.innerHTML = `
        <span class="sn-badge sn-badge-green">FASTAPI API CONNECTED</span>
        <span class="sn-badge sn-badge-amber">PHYSICS READY</span>
        <span class="sn-badge sn-badge-purple" id="header-ais-badge">AIS: ${state.aisDataMode}</span>
      `;
    } else {
      group.innerHTML = `
        <span class="sn-badge sn-badge-amber">OFFLINE DEMO MODE</span>
        <span class="sn-badge sn-badge-amber">PHYSICS READY</span>
        <span class="sn-badge sn-badge-purple" id="header-ais-badge">AIS: ${state.aisDataMode}</span>
      `;
    }
  }

  function initMap() {
    if (state.map) return;
    state.map = L.map("sn-hero-map", {
      center: [-20.4382, 57.7432],
      zoom: 10,
      zoomControl: true,
      attributionControl: false
    });

    // Keyless Production-Safe Dark Basemap (ESRI Dark Gray Canvas)
    L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}", {
      maxZoom: 16,
      attribution: 'Esri, HERE, Garmin, © OpenStreetMap contributors'
    }).addTo(state.map);

    state.layers.footprint = L.layerGroup().addTo(state.map);
    state.layers.candidates = L.layerGroup().addTo(state.map);
    state.layers.sourceEnvelopes = L.layerGroup().addTo(state.map);
    state.layers.particles = L.layerGroup().addTo(state.map);
    state.layers.forwardClosure = L.layerGroup().addTo(state.map);
    state.layers.forecastDrift = L.layerGroup().addTo(state.map);
    state.layers.historicalTruth = L.layerGroup().addTo(state.map);
    state.layers.aisTracks = L.layerGroup().addTo(state.map);

    window.addEventListener("resize", () => {
      if (state.map) state.map.invalidateSize();
    });

    state.map.on("mousemove", (e) => {
      document.getElementById("probe-lat").innerText = e.latlng.lat.toFixed(4) + "°";
      document.getElementById("probe-lon").innerText = e.latlng.lng.toFixed(4) + "°";
      let baseDb = -18.40;
      let unit = " dB";
      if (state.activeSarBand === "VH") {
        baseDb = -26.80;
      } else if (state.activeSarBand === "RATIO") {
        baseDb = 8.40;
      }
      const dbVal = (baseDb + (Math.sin(e.latlng.lat * 50) * 2.1)).toFixed(2);
      document.getElementById("probe-val").innerText = dbVal + unit;
    });

    drawMapLayers();
  }

  function drawMapLayers() {
    if (!state.map) return;
    state.map.invalidateSize();

    Object.values(state.layers).forEach(g => g && g.clearLayers());

    // SAR Band Polarization Raster Overlay (VV, VH, VV/VH Ratio)
    let bandColor = "#38BDF8";
    let bandFillColor = "#0284C7";
    let bandLabel = "VV CO-POLARIZATION";
    if (state.activeSarBand === "VH") {
      bandColor = "#A855F7";
      bandFillColor = "#8B5CF6";
      bandLabel = "VH CROSS-POLARIZATION";
    } else if (state.activeSarBand === "RATIO") {
      bandColor = "#10B981";
      bandFillColor = "#059669";
      bandLabel = "VV/VH POLARIZATION RATIO";
    }

    const footprintPoly = L.polygon([[-20.1, 57.2], [-20.1, 58.2], [-20.8, 58.2], [-20.8, 57.2]], {
      color: bandColor, weight: 2, dashArray: "6,6", fillColor: bandFillColor, fillOpacity: 0.18
    });
    footprintPoly.bindPopup(`<b>SENTINEL-1B SAR RASTER FOOTPRINT</b><br>Active Band: <b>${state.activeSarBand}</b> (${bandLabel})<br>Mode: IW GRDH Dual-Pol`);
    footprintPoly.addTo(state.layers.footprint);

    // Candidates
    const candidates = [
      { id: "C4053", lat: -20.4382, lon: 57.7432, area: 1.42 },
      { id: "C3929", lat: -20.4210, lon: 57.7200, area: 0.98 },
      { id: "C001", lat: -20.4500, lon: 57.7600, area: 1.15 }
    ];

    candidates.forEach(c => {
      const isSel = c.id === state.activeCandidateId;
      const poly = L.polygon([
        [c.lat - 0.015, c.lon - 0.015],
        [c.lat - 0.015, c.lon + 0.015],
        [c.lat + 0.015, c.lon + 0.015],
        [c.lat + 0.015, c.lon - 0.015]
      ], {
        color: isSel ? "#2563EB" : bandColor,
        fillColor: isSel ? "#2563EB" : bandFillColor,
        fillOpacity: isSel ? 0.6 : 0.35,
        weight: isSel ? 3 : 1
      });
      poly.bindPopup(`<b>SAR CANDIDATE ${c.id}</b><br>Area: ${c.area} km²<br>ML Score: 0.5818<br>Band: ${state.activeSarBand}`);
      poly.on("click", () => window.selectCandidate(c.id));
      state.layers.candidates.addLayer(poly);
    });

    if (state.physicsMode === "HINDCAST") {
      // Reconstructed Source Envelope
      L.polygon([[-20.35, 57.65], [-20.35, 57.85], [-20.55, 57.85], [-20.55, 57.65]], {
        color: "#F59E0B", fillColor: "#F59E0B", fillOpacity: 0.15, weight: 1.5, dashArray: "6,6"
      }).addTo(state.layers.sourceEnvelopes);

      // Particles
      for (let p = 0; p < 100; p++) {
        const pLat = -20.4382 + (Math.sin(p * 0.4) * 0.08);
        const pLon = 57.7432 + (Math.cos(p * 0.4) * 0.09);
        L.circleMarker([pLat, pLon], { radius: 2, color: "#F59E0B", fillColor: "#F59E0B", fillOpacity: 0.7 }).addTo(state.layers.particles);
      }
    } else {
      // Forecast Drift Envelopes & Particles (T0 to T+48h)
      L.polygon([[-20.45, 57.75], [-20.45, 58.15], [-20.75, 58.15], [-20.75, 57.75]], {
        color: "#38BDF8", fillColor: "#38BDF8", fillOpacity: 0.2, weight: 2, dashArray: "4,4"
      }).addTo(state.layers.forecastDrift);

      for (let p = 0; p < 120; p++) {
        const pLat = -20.4382 - (p * 0.002) + (Math.sin(p * 0.3) * 0.04);
        const pLon = 57.7432 + (p * 0.003) + (Math.cos(p * 0.3) * 0.04);
        L.circleMarker([pLat, pLon], { radius: 2.5, color: "#38BDF8", fillColor: "#38BDF8", fillOpacity: 0.8 }).addTo(state.layers.forecastDrift);
      }
    }

    // Historical Reference Marker
    const histMarker = L.circleMarker([-20.4382, 57.7432], {
      radius: 8, color: "#EF4444", fillColor: "#EF4444", fillOpacity: 0.9, weight: 2
    });
    histMarker.bindPopup("<b>CANONICAL HISTORICAL GROUNDING REFERENCE</b><br>MV Wakashio (25 JUL 2020)<br>Unlocked post-freeze for validation only.");
    state.layers.historicalTruth.addLayer(histMarker);

    // AIS Tracks
    L.polyline([[-20.20, 57.50], [-20.40, 57.70], [-20.50, 57.80]], { color: "#8B5CF6", weight: 3 }).addTo(state.layers.aisTracks);
  }

  /* ==========================================================================
     JOB POLLING & ORCHESTRATION ENGINE
     ========================================================================== */

  function openJobProgressModal(title) {
    const modal = document.getElementById("sn-job-progress-modal");
    const tEl = document.getElementById("job-modal-title");
    const sEl = document.getElementById("job-modal-step");
    const pEl = document.getElementById("job-modal-pct");
    const bar = document.getElementById("job-modal-progress-bar");
    const logTerm = document.getElementById("job-modal-log-terminal");

    if (tEl) tEl.innerText = title;
    if (sEl) sEl.innerText = "INITIALIZING...";
    if (pEl) pEl.innerText = "0%";
    if (bar) bar.style.width = "0%";
    if (logTerm) logTerm.innerHTML = `<div style="color: var(--text-muted);">[SYSTEM] Job orchestration launched...</div>`;
    if (modal) modal.classList.remove("hidden");
  }

  function closeJobProgressModal() {
    const modal = document.getElementById("sn-job-progress-modal");
    if (modal) modal.classList.add("hidden");
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
        logTerm.innerHTML = jData.logs.map(l => `
          <div><span style="color: var(--text-muted);">${l.timestamp_utc.substr(11, 8)}</span> <strong style="color: var(--accent-cyan);">${l.step}</strong>: ${l.message}</div>
        `).join("");
        logTerm.scrollTop = logTerm.scrollHeight;
      }

      if (jData.status === "COMPLETE") {
        clearInterval(interval);
        setTimeout(() => {
          closeJobProgressModal();
          if (onComplete) onComplete(jData.result);
        }, 800);
      } else if (jData.status === "FAILED") {
        clearInterval(interval);
        if (sEl) sEl.innerText = `FAILED: ${jData.error}`;
      }
    }, 350);
  }

  /* ==========================================================================
     INTERACTIVE OPERATOR ACTIONS
     ========================================================================== */

  window.openNewInvestigationModal = function () { document.getElementById("sn-new-inv-modal")?.classList.remove("hidden"); };
  window.closeNewInvestigationModal = function () { document.getElementById("sn-new-inv-modal")?.classList.add("hidden"); };

  window.loadBenchmarkCase = async function () {
    const res = await postEndpoint("/cases", { case_type: "BENCHMARK" });
    if (res) {
      state.activeCaseId = "R001_WAKASHIO";
      state.activeCaseMode = "VALIDATED BENCHMARK (R001 Wakashio)";
      document.getElementById("header-case-id").innerText = "R001 — Mauritius";
      document.getElementById("header-case-mode").innerText = "HISTORICAL CASE REVIEW";
      closeNewInvestigationModal();
      await initApp();
    }
  };

  window.startCustomInvestigation = async function () {
    const sarInput = document.getElementById("input-sar-geotiff");
    const res = await postEndpoint("/cases", { case_type: "CUSTOM", case_name: "Custom SAR Incident" });
    if (res) {
      state.activeCaseId = "CUSTOM_CASE";
      state.activeCaseMode = "NEW SAR OBSERVATION UPLOAD";
      document.getElementById("header-case-id").innerText = "CUSTOM CASE";
      document.getElementById("header-case-mode").innerText = "NEW SAR OBSERVATION";
      closeNewInvestigationModal();
      await initApp();
    }
  };

  window.runSlickDetection = async function () {
    openJobProgressModal("⚡ RUNNING SAR SLICK DETECTION PIPELINE");
    const jobRes = await postEndpoint(`/cases/${state.activeCaseId}/detect`);
    if (jobRes && jobRes.job_id) {
      pollJobStatus(jobRes.job_id, (result) => {
        window.switchStage("ANALYZE");
      });
    }
  };

  window.runHindcast = async function () {
    openJobProgressModal("🌊 RUNNING OPENDRIFT BACKWARD HINDCAST");
    const jobRes = await postEndpoint(`/cases/${state.activeCaseId}/reconstruct`, { scenario: state.activeScenario });
    if (jobRes && jobRes.job_id) {
      pollJobStatus(jobRes.job_id, (result) => {
        window.switchPhysicsMode("HINDCAST");
        window.switchStage("RECONSTRUCT");
      });
    }
  };

  window.runForecast = async function () {
    openJobProgressModal("🔮 RUNNING OPENDRIFT FORWARD FORECAST (T0 → T+48h)");
    const jobRes = await postEndpoint(`/cases/${state.activeCaseId}/forecast`, { scenario: state.activeScenario });
    if (jobRes && jobRes.job_id) {
      pollJobStatus(jobRes.job_id, (result) => {
        window.switchPhysicsMode("FORECAST");
        window.switchStage("RECONSTRUCT");
      });
    }
  };

  window.switchPhysicsMode = function (mode) {
    state.physicsMode = mode;
    const hBtn = document.getElementById("btn-mode-hindcast");
    const fBtn = document.getElementById("btn-mode-forecast");

    if (mode === "HINDCAST") {
      if (hBtn) hBtn.classList.add("active");
      if (fBtn) fBtn.classList.remove("active");
      updateTimelineLabels(["T-96h (06 Aug)", "T-72h (07 Aug)", "T-48h (08 Aug)", "T-24h (09 Aug)", "T0 (10 Aug 01:38 UTC)"]);
    } else {
      if (fBtn) fBtn.classList.add("active");
      if (hBtn) hBtn.classList.remove("active");
      updateTimelineLabels(["T0 (10 Aug 01:38 UTC)", "T+6h (10 Aug)", "T+12h (10 Aug)", "T+24h (11 Aug)", "T+48h (12 Aug)"]);
    }
    drawMapLayers();
    renderInspector();
  };

  function updateTimelineLabels(labels) {
    const container = document.getElementById("timeline-labels-container");
    if (!container) return;
    container.innerHTML = labels.map((lbl, idx) => `
      <span class="sn-t-lbl ${idx === 4 ? "active" : ""}" onclick="window.setTimestep('${lbl.split(' ')[0]}')">${lbl}</span>
    `).join("");
  }

  window.runVesselCorrelation = async function () {
    openJobProgressModal("🚢 RUNNING AIS VESSEL CORRELATION & RANKING");
    const jobRes = await postEndpoint(`/cases/${state.activeCaseId}/correlate`);
    if (jobRes && jobRes.job_id) {
      pollJobStatus(jobRes.job_id, (result) => {
        window.switchStage("ATTRIBUTE");
      });
    }
  };

  window.runAutomatedInvestigation = async function () {
    openJobProgressModal("⚡ RUNNING FULL AUTOMATED PIPELINE ORCHESTRATION");
    const jobRes = await postEndpoint(`/cases/${state.activeCaseId}/automate`);
    if (jobRes && jobRes.job_id) {
      pollJobStatus(jobRes.job_id, (result) => {
        window.switchStage("REVIEW");
      });
    }
  };

  /* ==========================================================================
     DOMAIN SWITCHING & INSPECTOR RENDERING
     ========================================================================== */

  window.switchStage = function (stg) {
    state.currentStage = stg;
    document.querySelectorAll(".sn-nav-btn").forEach(btn => {
      btn.classList.toggle("active", btn.dataset.stage === stg);
    });

    const subbar = document.getElementById("sn-subview-bar");
    if (subbar) subbar.classList.toggle("hidden", stg !== "RECONSTRUCT");

    drawMapLayers();
    renderInspector();
  };

  window.switchReconstructSubview = function (sub) {
    state.activeReconstructSubview = sub;
    document.querySelectorAll(".sn-subtab").forEach(btn => btn.classList.remove("active"));
    const btnMap = { FORWARD: "btn-sub-forward", HISTORICAL: "btn-sub-historical" };
    if (btnMap[sub]) document.getElementById(btnMap[sub])?.classList.add("active");
    renderInspector();
  };

  window.switchSarBand = function (band) {
    state.activeSarBand = band;
    document.querySelectorAll(".sn-band-btn").forEach(btn => btn.classList.remove("active"));
    const btnMap = { VV: "btn-band-vv", VH: "btn-band-vh", RATIO: "btn-band-ratio" };
    if (btnMap[band]) document.getElementById(btnMap[band])?.classList.add("active");
    drawMapLayers();
    renderInspector();
  };

  window.selectCandidate = function (id) {
    state.activeCandidateId = id;
    drawMapLayers();
    renderInspector();
  };

  window.setTimestep = function (step) {
    state.activeTimestep = step;
    document.querySelectorAll(".sn-t-lbl").forEach(lbl => {
      lbl.classList.toggle("active", lbl.innerText.includes(step));
    });
    drawMapLayers();
  };

  window.setScenario = function (scen) {
    state.activeScenario = scen;
    drawMapLayers();
  };

  window.togglePlayback = function () {
    state.isPlaying = !state.isPlaying;
    const btn = document.getElementById("btn-play-pause");
    if (state.isPlaying) {
      if (btn) btn.innerText = "⏸ PAUSE";
      state.playTimer = setInterval(() => {
        const steps = ["T-96", "T-72", "T-48", "T-24", "T0"];
        let idx = steps.indexOf(state.activeTimestep);
        idx = (idx + 1) % steps.length;
        window.setTimestep(steps[idx]);
      }, 1500 / state.playbackSpeed);
    } else {
      if (btn) btn.innerText = "▶ PLAY";
      clearInterval(state.playTimer);
    }
  };

  window.setSpeed = function (spd) { state.playbackSpeed = spd; };
  window.toggleLayerPanel = function () { document.getElementById("sn-layer-panel")?.classList.toggle("hidden"); };
  window.updateMapLayers = function () { drawMapLayers(); };

  window.switchEdgeState = async function (simState) {
    state.activeEdgeState = simState;
    if (simState !== "NORMAL_CASE") {
      const fixture = await fetchEndpoint(`/cases/${state.activeCaseId}/simulated-failure/${simState}`);
      if (fixture) {
        state.caseData = fixture;
        state.vesselsData = fixture.ais?.candidates || [];
      }
    } else {
      await initApp();
    }
    renderInspector();
  };

  window.openOperationsHome = function () { document.getElementById("sn-ops-modal")?.classList.remove("hidden"); };
  window.closeOperationsHome = function () { document.getElementById("sn-ops-modal")?.classList.add("hidden"); };
  window.toggleDataHealthModal = function () { document.getElementById("sn-health-modal")?.classList.toggle("hidden"); };

  window.toggleProvenanceDrawer = function () {
    const drw = document.getElementById("sn-provenance-drawer");
    const ovr = document.getElementById("sn-drawer-overlay");
    if (drw && ovr) {
      drw.classList.toggle("hidden");
      ovr.classList.toggle("hidden");
      if (!drw.classList.contains("hidden")) renderProvenanceDrawer();
    }
  };

  function renderProvenanceDrawer() {
    const body = document.getElementById("sn-provenance-body");
    if (!body) return;
    body.innerHTML = `
      <div class="sn-card">
        <div class="sn-card-title">PRIMARY DATA SOURCE PROVENANCE</div>
        <div class="sn-metric-box" style="margin-bottom: 6px;">
          <div class="sn-m-label">PRODUCT ID</div>
          <div class="sn-m-val" style="font-size: 10px;">S1B_IW_GRDH_1SDV_20200810T013755_20200810T013820</div>
        </div>
        <div class="sn-metric-grid">
          <div class="sn-metric-box"><div class="sn-m-label">MISSION</div><div class="sn-m-val">Sentinel-1B</div></div>
          <div class="sn-metric-box"><div class="sn-m-label">MODE</div><div class="sn-m-val">IW GRDH</div></div>
          <div class="sn-metric-box"><div class="sn-m-label">POLARIZATION</div><div class="sn-m-val">VV / VH</div></div>
          <div class="sn-metric-box"><div class="sn-m-label">ACQUISITION</div><div class="sn-m-val">10 AUG 2020</div></div>
        </div>
      </div>
      <div class="sn-card">
        <div class="sn-card-title">PHYSICS & ENGINE VERSIONS</div>
        <div class="sn-metric-grid">
          <div class="sn-metric-box"><div class="sn-m-label">OPEN DRIFT</div><div class="sn-m-val">v1.14.11</div></div>
          <div class="sn-metric-box"><div class="sn-m-label">MET-OCEAN</div><div class="sn-m-val">ERA5 / HYCOM</div></div>
          <div class="sn-metric-box"><div class="sn-m-label">CLEAN ROOM</div><div class="sn-m-val" style="color: var(--status-good);">PASS</div></div>
          <div class="sn-metric-box"><div class="sn-m-label">AIS DATA MODE</div><div class="sn-m-val" style="color: var(--status-synthetic);">${state.aisDataMode}</div></div>
        </div>
      </div>
    `;
  }

  function renderInspector() {
    const pnl = document.getElementById("sn-inspector-panel");
    if (!pnl) return;

    if (state.currentStage === "OBSERVE") {
      pnl.innerHTML = `
        <div class="sn-card">
          <div class="sn-card-title">01 OBSERVE — SATELLITE SCENE ANALYSIS</div>
          <div class="sn-metric-box" style="margin-bottom: 8px;">
            <div class="sn-m-label">SENTINEL-1B PRODUCT ID</div>
            <div class="sn-m-val" style="font-size: 10px;">S1B_IW_GRDH_1SDV_20200810T013755_20200810T013820</div>
          </div>
          <div class="sn-metric-grid" style="margin-bottom: 10px;">
            <div class="sn-metric-box"><div class="sn-m-label">ACQUISITION UTC</div><div class="sn-m-val">10 AUG 01:38</div></div>
            <div class="sn-metric-box"><div class="sn-m-label">POLARIZATION</div><div class="sn-m-val">VV / VH</div></div>
          </div>
          <button class="sn-action-btn" style="width: 100%; padding: 8px;" onclick="window.runSlickDetection()">⚡ RUN SLICK DETECTION PIPELINE</button>
        </div>
        <div class="sn-card">
          <div class="sn-card-title">PROCESSING LINEAGE</div>
          <p class="sn-m-label">✓ Precise Orbit Correction<br>✓ Thermal Noise Removal<br>✓ Radiometric Calibration (Sigma0)<br>✓ Range-Doppler Terrain Correction</p>
        </div>
      `;
    } else if (state.currentStage === "ANALYZE") {
      pnl.innerHTML = `
        <div class="sn-card">
          <div class="sn-card-title">02 ANALYZE — CANDIDATE SELECTION</div>
          <div class="sn-metric-grid" style="margin-bottom: 10px;">
            <div class="sn-metric-box"><div class="sn-m-label">SELECTED ID</div><div class="sn-m-val" style="color: var(--accent-cyan);">${state.activeCandidateId}</div></div>
            <div class="sn-metric-box"><div class="sn-m-label">SLICK AREA</div><div class="sn-m-val">1.42 km²</div></div>
            <div class="sn-metric-box"><div class="sn-m-label">VV MEDIAN</div><div class="sn-m-val">-18.40 dB</div></div>
            <div class="sn-metric-box"><div class="sn-m-label">ML OIL-LIKE SCORE</div><div class="sn-m-val" style="color: var(--status-good);">0.5818</div></div>
          </div>
          <div style="display: flex; gap: 8px;">
            <button class="sn-action-btn" style="flex: 1; padding: 8px;" onclick="window.runHindcast()">🌊 RUN HINDCAST</button>
            <button class="sn-action-btn" style="flex: 1; padding: 8px; background: var(--accent-cyan); color: #000;" onclick="window.runForecast()">🔮 RUN FORECAST</button>
          </div>
        </div>
        <div class="sn-card">
          <div class="sn-card-title">CANDIDATE HYPOTHESES (8) <span class="sn-badge sn-badge-green" style="font-size: 8px;">VALIDATED CACHED RESULT</span></div>
          <div class="sn-candidate-list">
            <div class="sn-cand-item ${state.activeCandidateId === "C4053" ? "selected" : ""}" onclick="window.selectCandidate('C4053')">
              <span><strong>C4053</strong> (Primary Target)</span><span>0.5818 ML</span>
            </div>
            <div class="sn-cand-item ${state.activeCandidateId === "C3929" ? "selected" : ""}" onclick="window.selectCandidate('C3929')">
              <span><strong>C3929</strong> (North Slick)</span><span>0.841 ML</span>
            </div>
            <div class="sn-cand-item ${state.activeCandidateId === "C001" ? "selected" : ""}" onclick="window.selectCandidate('C001')">
              <span><strong>C001</strong> (South Slick)</span><span>0.795 ML</span>
            </div>
          </div>
        </div>
      `;
    } else if (state.currentStage === "RECONSTRUCT") {
      if (state.physicsMode === "FORECAST") {
        pnl.innerHTML = `
          <div class="sn-card" style="border-color: var(--accent-cyan);">
            <div class="sn-card-title">🔮 TRUE OPENDRIFT FORWARD FORECAST <span class="sn-badge sn-badge-green" style="font-size: 8px;">FULL FORCING SUPPORT</span></div>
            <div class="sn-metric-grid" style="margin-bottom: 10px;">
              <div class="sn-metric-box"><div class="sn-m-label">FORECAST HORIZON</div><div class="sn-m-val" style="color: var(--accent-cyan);">T0 → T+48h</div></div>
              <div class="sn-metric-box"><div class="sn-m-label">FORCING COVERAGE</div><div class="sn-m-val" style="color: var(--status-good); font-size: 10px;">FULL FORCING SUPPORT</div></div>
              <div class="sn-metric-box"><div class="sn-m-label">LAST VALID FORCING TS</div><div class="sn-m-val" style="font-size: 9px;">2020-08-12T03:00Z</div></div>
              <div class="sn-metric-box"><div class="sn-m-label">METOCEAN FORCING</div><div class="sn-m-val" style="font-size: 10px;">ERA5 / HYCOM / CMEMS</div></div>
            </div>
            <button class="sn-action-btn" style="width: 100%; padding: 8px;" onclick="window.runForecast()">RE-RUN FORWARD FORECAST</button>
          </div>
        `;
      } else {
        pnl.innerHTML = `
          <div class="sn-card">
            <div class="sn-card-title">03 RECONSTRUCT — OPENDRIFT HINDCAST</div>
            <div class="sn-metric-grid" style="margin-bottom: 10px;">
              <div class="sn-metric-box"><div class="sn-m-label">HINDCAST HORIZON</div><div class="sn-m-val" style="color: var(--status-uncertain);">T0 → T-96h</div></div>
              <div class="sn-metric-box"><div class="sn-m-label">SCENARIO</div><div class="sn-m-val">Scenario ${state.activeScenario}</div></div>
              <div class="sn-metric-box"><div class="sn-m-label">TIMESTEP</div><div class="sn-m-val">${state.activeTimestep}</div></div>
              <div class="sn-metric-box"><div class="sn-m-label">PARTICLES</div><div class="sn-m-val">500</div></div>
            </div>
            <button class="sn-action-btn" style="width: 100%; padding: 8px;" onclick="window.runHindcast()">RE-RUN BACKWARD HINDCAST</button>
          </div>
        `;
      }
    } else if (state.currentStage === "ATTRIBUTE") {
      const topV = state.vesselsData[0] || {};
      pnl.innerHTML = `
        <div class="sn-card" style="border-color: rgba(139, 92, 246, 0.4);">
          <div class="sn-card-title" style="color: var(--status-synthetic);">SYNTHETIC AIS DEMONSTRATION</div>
          <p class="sn-m-label" style="color: var(--status-synthetic);">HISTORICAL ATTRIBUTION NOT VALID</p>
        </div>
        <div class="sn-card">
          <div class="sn-card-title">04 VESSEL INTELLIGENCE & CORRELATION</div>
          <div class="sn-metric-grid" style="margin-bottom: 10px;">
            <div class="sn-metric-box"><div class="sn-m-label">TOP VESSEL</div><div class="sn-m-val">${topV.vessel_name || "VESSEL_BETA"}</div></div>
            <div class="sn-metric-box"><div class="sn-m-label">PRIORITY SCORE</div><div class="sn-m-val" style="color: var(--accent-cyan);">${topV.investigative_priority_score || 0.907}</div></div>
          </div>
          <button class="sn-action-btn" style="width: 100%; padding: 8px;" onclick="window.runVesselCorrelation()">⚡ RUN VESSEL CORRELATION PIPELINE</button>
        </div>
      `;
    } else if (state.currentStage === "REVIEW") {
      pnl.innerHTML = `
        <div class="sn-card">
          <div class="sn-card-title">05 REVIEW — INCIDENT BRIEFING & MATRIX</div>
          <div class="sn-metric-box" style="margin-bottom: 8px;">
            <div class="sn-m-label">OVERALL CASE STATE</div>
            <div class="sn-m-val" style="color: var(--status-good);">ANALYST REVIEW REQUIRED</div>
          </div>
          <div class="sn-metric-grid" style="margin-bottom: 10px;">
            <div class="sn-metric-box"><div class="sn-m-label">SAR CANDIDATES</div><div class="sn-m-val">8 Candidates</div></div>
            <div class="sn-metric-box"><div class="sn-m-label">BEST CLOSURE</div><div class="sn-m-val">C3929 (2.41 km)</div></div>
          </div>
          <button class="sn-action-btn" style="width: 100%; padding: 8px; background: var(--accent-indigo);" onclick="window.toggleProvenanceDrawer()">📜 OPEN CRYPTOGRAPHIC PROVENANCE</button>
        </div>
      `;
    }
  }

  document.addEventListener("DOMContentLoaded", initApp);
})();
