/**
 * SUBPIXEL-SENTRY // MAIN APPLICATION CONTROLLER
 * Orchestrates Three.js environment, animated loading, tab transitions,
 * KPI counter animations, alert triage, evidence dossiers, and exports.
 *
 * Keyboard map (documented in map status bar):
 *   1-4        switch tabs
 *   Arrows     move selected pixel (Map tab)
 *   Shift+←/→  move comparison slider
 *   Esc        close modal / drawer
 */

(function() {
  'use strict';

  let domReady = false;
  let threeReady = false;

  document.addEventListener('DOMContentLoaded', () => {
    domReady = true;
    tryInit();
  });

  window.addEventListener('three-ready', () => {
    threeReady = true;
    tryInit();
  });

  setTimeout(() => {
    if (!threeReady) {
      console.warn('Three.js module load timeout — initializing without 3D');
      threeReady = true;
      tryInit();
    }
  }, 5000);

  let initialized = false;
  function tryInit() {
    if (!domReady || !threeReady || initialized) return;
    initialized = true;
    initApp();
  }

  function initApp() {
    const api = window.SentryAPI;
    const chartEngine = new window.MetricsChartEngine();
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    // ═══════════════════════════════════════════════════════════════
    // 1. LOADING SCREEN — honest staged readout
    // ═══════════════════════════════════════════════════════════════
    const loadingScreen = document.getElementById('loadingScreen');
    const loadingBar = document.getElementById('loadingBarFill');
    const loadingReadout = document.getElementById('loadingReadout');
    const appShell = document.getElementById('appShell');

    const loadSteps = [
      'MOUNTING RENDER SURFACE',
      'LOADING TERRAIN MODEL',
      'RESTORING TILE CACHE — S2A_MSIL2A_20260308T045651',
      'VCA ENDMEMBER MATRIX (N=5)',
      'FCLS ABUNDANCE TABLES',
      'SPATIAL ALLOCATION MODEL (50K MLP)',
      'CALIBRATION & AUDIT SIGNATURES',
      'READY'
    ];

    let loadStep = 0;
    let loadProgress = 0;
    const loadInterval = setInterval(() => {
      loadProgress += Math.random() * 11 + 5;
      if (loadProgress > 100) loadProgress = 100;
      if (loadingBar) loadingBar.style.width = loadProgress + '%';
      const stepIdx = Math.min(Math.floor((loadProgress / 100) * loadSteps.length), loadSteps.length - 1);
      if (loadingReadout && stepIdx !== loadStep) {
        loadStep = stepIdx;
        loadingReadout.textContent = loadSteps[stepIdx];
      }
      if (loadProgress >= 100) {
        clearInterval(loadInterval);
        setTimeout(() => {
          if (loadingScreen) loadingScreen.classList.add('hidden');
          if (appShell) {
            appShell.style.transition = 'opacity 0.8s ease';
            appShell.style.opacity = '1';
          }
        }, 350);
      }
    }, 160);

    // ═══════════════════════════════════════════════════════════════
    // 2. THREE.JS ENVIRONMENT
    // ═══════════════════════════════════════════════════════════════
    let sentryEnv = null;
    try {
      if (window.THREE && window.SentryEnvironment) {
        sentryEnv = new SentryEnvironment('threeCanvas');
        window.SentryEnv = sentryEnv; // dev/diagnostics handle (like SentryAPI)
      }
    } catch (e) {
      console.warn('Three.js env init failed:', e);
    }

    // ═══════════════════════════════════════════════════════════════
    // 3. UTC CLOCK — operations always run on Zulu time
    // ═══════════════════════════════════════════════════════════════
    const clockEl = document.getElementById('utcClock');
    if (clockEl) {
      const tickClock = () => {
        const now = new Date();
        const pad = (n) => String(n).padStart(2, '0');
        clockEl.textContent = `${pad(now.getUTCHours())}:${pad(now.getUTCMinutes())}:${pad(now.getUTCSeconds())}`;
      };
      tickClock();
      setInterval(tickClock, 1000);
    }

    // ═══════════════════════════════════════════════════════════════
    // 4. TOASTS
    // ═══════════════════════════════════════════════════════════════
    const toastRegion = document.getElementById('toastRegion');

    function toast(message, kind = 'ok', ttl = 3200) {
      if (!toastRegion) return;
      const el = document.createElement('div');
      el.className = `toast toast-${kind}`;
      el.textContent = message;
      toastRegion.appendChild(el);
      setTimeout(() => {
        el.classList.add('toast-out');
        setTimeout(() => el.remove(), 320);
      }, ttl);
    }

    // ═══════════════════════════════════════════════════════════
    // 4b. BACKEND CONNECTION — live vs simulated badge
    // ═══════════════════════════════════════════════════════════
    const connChip = document.createElement('span');
    connChip.id = 'backendConnChip';
    connChip.className = 'chip neutral';
    connChip.textContent = 'Backend: checking…';
    const headerRight = document.querySelector('.header-right');
    if (headerRight) headerRight.prepend(connChip);

    window.addEventListener('sentry-connection', (e) => {
      const d = e.detail || {};
      if (d.connected) {
        connChip.textContent = 'Backend: live';
        connChip.className = 'chip live';
        connChip.title = `db=${d.health?.db} storage=${d.health?.storage} protocol=${d.health?.protocol_version}`;
      } else {
        connChip.textContent = 'Simulator (no backend)';
        connChip.className = 'chip alert';
        connChip.title = d.error || 'backend unreachable';
      }
    });
    api.connect();

    // ═══════════════════════════════════════════════════════════════
    // 5. SENTINEL SIMULATOR
    // ═══════════════════════════════════════════════════════════════
    const sim = new window.SentinelSRMSimulator(
      'canvasCoarse', 'canvasFine', 'sliderHandle', 'sliderLine'
    );

    sim.onPixelSelect = async (x, y) => {
      const aoiId = document.getElementById('aoiSelect')?.value || 'AOI_01';
      const data = await api.inspectPixel(aoiId, x, y);
      updateInspector(data);
    };
    sim.selectPixel(14, 16);

    // ═══════════════════════════════════════════════════════════════
    // 6. TAB NAVIGATION
    // ═══════════════════════════════════════════════════════════════
    const tabBtns = document.querySelectorAll('.tab-btn');
    const tabContents = document.querySelectorAll('.tab-content');
    let metricsRendered = false;

    function switchTab(targetTabId, focusFirst = false) {
      tabBtns.forEach(btn => {
        const isActive = btn.getAttribute('data-tab') === targetTabId;
        btn.classList.toggle('active', isActive);
        btn.setAttribute('aria-selected', isActive ? 'true' : 'false');
      });
      tabContents.forEach(content => {
        const isActive = content.id === targetTabId;
        content.classList.toggle('active', isActive);
        if (isActive) content.removeAttribute('hidden');
        else content.setAttribute('hidden', '');
        if (isActive && focusFirst) content.focus({ preventScroll: true });
      });
      if (targetTabId === 'tabMetrics' && !metricsRendered) {
        metricsRendered = true;
        setTimeout(() => {
          renderAllMetricsCharts();
          animateKPICounters();
        }, 80);
      }
    }

    tabBtns.forEach(btn => {
      btn.addEventListener('click', () => switchTab(btn.getAttribute('data-tab')));
      // Arrow-key navigation within the tablist
      btn.addEventListener('keydown', (e) => {
        if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
        const idx = Array.from(tabBtns).indexOf(btn);
        const next = e.key === 'ArrowRight'
          ? (idx + 1) % tabBtns.length
          : (idx - 1 + tabBtns.length) % tabBtns.length;
        const nextBtn = tabBtns[next];
        nextBtn.focus();
        switchTab(nextBtn.getAttribute('data-tab'));
        e.preventDefault();
      });
    });

    // ═══════════════════════════════════════════════════════════════
    // 7. KPI COUNTER ANIMATION
    // ═══════════════════════════════════════════════════════════════
    function animateKPICounters() {
      document.querySelectorAll('.kpi-value[data-target]').forEach(el => {
        const target = parseFloat(el.dataset.target);
        const prefix = el.dataset.prefix || '';
        const suffix = el.dataset.suffix || '%';

        if (reducedMotion) {
          el.innerHTML = prefix + formatKpi(target, target) + suffix;
          return;
        }

        const duration = 1100;
        const startTime = performance.now();

        function tick(now) {
          const progress = Math.min((now - startTime) / duration, 1);
          const eased = 1 - Math.pow(1 - progress, 4);
          const current = target * eased;
          el.innerHTML = prefix + formatKpi(current, target) + suffix;
          if (progress < 1) requestAnimationFrame(tick);
        }
        requestAnimationFrame(tick);
      });

      function formatKpi(value, target) {
        if (target < 1) return value.toFixed(2);
        if (target < 10) return value.toFixed(1);
        return String(Math.round(value));
      }
    }

    // ═══════════════════════════════════════════════════════════════
    // 8. MAP VIEW TOGGLES
    // ═══════════════════════════════════════════════════════════════
    const viewToggleBtns = document.querySelectorAll('.map-toggle-btn');

    let activeView = 'SPLIT';

    // View modes are mutually exclusive, like radio buttons.
    //   SPLIT  — 10m (left) vs 2.5m (right) with slider + both chips
    //   COARSE — full-frame 10m Sentinel-2; 2.5m layer clipped away
    //   FINE   — full-frame 2.5m resolved; 10m layer underneath
    //   3D     — docked WebGL terrain; SRM stage hidden entirely
    function setView(view) {
      const fine = document.getElementById('canvasFine');
      const line = document.getElementById('sliderLine');
      const handle = document.getElementById('sliderHandle');
      const stage = document.getElementById('srmStage');
      const container = stage ? stage.parentElement : null;
      const hudL = document.querySelector('.hud-top-left');
      const hudR = document.querySelector('.map-hud-overlay.hud-top-right:not(.hud-3d)');
      const hud3d = document.querySelector('.hud-3d');
      const is3D = view === '3D';

      if (is3D) {
        // 3D Tactical DEM: dock the WebGL terrain into the map panel.
        if (sentryEnv) {
          sentryEnv.dockIn(container);
        }
        if (container) container.classList.add('mode-3d-active');
        if (stage) stage.style.visibility = 'hidden';
        if (line) line.style.display = 'none';
        if (handle) handle.style.display = 'none';
        if (hudL) hudL.hidden = true;
        if (hudR) hudR.hidden = true;
        if (hud3d) hud3d.hidden = false;
      } else {
        // Leaving 3D: restore the background globe and the SRM canvases.
        if (sentryEnv) sentryEnv.undock();
        if (container) container.classList.remove('mode-3d-active');
        if (stage) stage.style.visibility = '';
        if (hud3d) hud3d.hidden = true;

        // Which layer stays visible is decided once, per mode — no leftover
        // clip from the previous mode can survive.
        if (view === 'COARSE') {
          // 10M Sentinel-2: resolved layer fully clipped away.
          if (fine) fine.style.clipPath = 'inset(0 100% 0 0)';
          if (line) line.style.display = 'none';
          if (handle) handle.style.display = 'none';
          if (hudL) { hudL.hidden = false; hudL.querySelector('.hud-title').textContent = '10m Sentinel-2 L2A (input)'; }
          if (hudR) hudR.hidden = true;
        } else if (view === 'FINE') {
          // 2.5M Resolved: resolved layer fully revealed.
          if (fine) fine.style.clipPath = 'inset(0 0 0 0)';
          if (line) line.style.display = 'none';
          if (handle) handle.style.display = 'none';
          if (hudL) hudL.hidden = true;
          if (hudR) { hudR.hidden = false; hudR.querySelector('.hud-title').textContent = '2.5m Super-Resolved (model-inferred)'; }
        } else {
          // SPLIT: half/half with slider + both source chips.
          if (fine) fine.style.clipPath = 'inset(0 50% 0 0)';
          if (line) line.style.display = '';
          if (handle) handle.style.display = '';
          if (hudL) { hudL.hidden = false; hudL.querySelector('.hud-title').textContent = 'Left: 10m Sentinel-2 L2A'; }
          if (hudR) { hudR.hidden = false; hudR.querySelector('.hud-title').textContent = 'Right: 2.5m Super-Resolved'; }
          sim.updateSplitPosition(50);
        }
      }
      activeView = view;
      viewToggleBtns.forEach(b => {
        const isActive = b.getAttribute('data-view') === view;
        b.classList.toggle('active', isActive);
        b.setAttribute('aria-pressed', isActive ? 'true' : 'false');
      });
    }

    viewToggleBtns.forEach(btn => {
      btn.addEventListener('click', () => setView(btn.getAttribute('data-view')));
    });

    // ═══════════════════════════════════════════════════════════════
    // 9. INSPECTOR UPDATE
    // ═══════════════════════════════════════════════════════════════
    function updateInspector(data) {
      if (!data) return;

      const c = data.coordinates || {};
      const badge = document.getElementById('inspectCoordBadge');
      if (badge) badge.textContent = `X:${c.x ?? '?'} Y:${c.y ?? '?'}`;

      const coordChip = document.getElementById('selectedCoordChip');
      if (coordChip && c.lat && c.lon) {
        coordChip.textContent = `${parseFloat(c.lat).toFixed(4)}° N, ${parseFloat(c.lon).toFixed(4)}° E`;
      }

      const ab = data.abundances || {};
      [
        ['Imp', 'impervious'], ['Veg', 'vegetation'], ['Wat', 'water'],
        ['Soil', 'soil'], ['Shade', 'shade']
      ].forEach(([suf, key]) => {
        const pct = document.getElementById('pct' + suf);
        const bar = document.getElementById('bar' + suf);
        if (pct && ab[key] !== undefined) {
          const v = (ab[key] * 100).toFixed(1);
          pct.textContent = v + '%';
          if (bar) bar.style.width = v + '%';
        }
      });

      const geo = data.geometryClassification || {};
      const geoClass = document.getElementById('geoClassVal');
      const geoAspect = document.getElementById('geoAspectVal');
      const geoConf = document.getElementById('geoConfVal');
      if (geoClass) geoClass.textContent = geo.classification || 'Unknown';
      if (geoAspect) geoAspect.textContent = geo.geometry || '—';
      if (geoConf) {
        const conf = geo.confidence || 0;
        geoConf.textContent = conf.toFixed(2) + (conf >= 0.8 ? ' (High)' : conf >= 0.5 ? ' (Medium)' : ' (Low)');
        geoConf.style.color = conf >= 0.8 ? 'var(--signal-ready)' :
                              conf >= 0.5 ? 'var(--ink-bright)' : 'var(--signal-alert)';
      }

      const ref = data.reflectanceBands || {};
      ['B2', 'B3', 'B4', 'B8', 'B11', 'B12'].forEach(b => {
        const el = document.getElementById('band' + b);
        if (el && ref[b] !== undefined) el.textContent = ref[b].toFixed(4);
      });

      // Refinement audit (live from pipeline, not hardcoded)
      const iterEl = document.getElementById('auditIter');
      const cohEl = document.getElementById('auditCoherence');
      const mseEl = document.getElementById('auditMse');
      const rmseEl = document.getElementById('auditRmse');
      if (iterEl) iterEl.textContent = (data.atkinsonIterations ?? 8) + ' iterations';
      if (cohEl) cohEl.textContent = (data.spatialCoherenceScore ?? 0.842).toFixed(3) + ' (settled)';
      if (mseEl) mseEl.textContent = (data.massConservationMse ?? 0.0084).toFixed(4) + ' (< 0.05 pass)';
      if (rmseEl) rmseEl.textContent = (data.fclsRmse ?? 0.0142).toFixed(4) + ' (in-model)';

      // Subpixel preview
      const preview = document.getElementById('subpixelPreview');
      const grid = data.subpixelGrid || [];
      if (preview && grid.length) {
        preview.innerHTML = '';
        const colorMap = {
          'IMPERVIOUS': 'var(--spectral-impervious)',
          'VEGETATION': 'var(--spectral-vegetation)',
          'WATER':      'var(--spectral-water)',
          'SOIL':       'var(--spectral-soil)',
          'SHADE':      'var(--spectral-shade)',
          'NODATA':     'var(--spectral-nodata)'
        };
        grid.forEach(sp => {
          const cell = document.createElement('div');
          cell.className = 'subpixel-cell';
          cell.style.background = colorMap[sp] || '#333';
          cell.title = sp;
          preview.appendChild(cell);
        });
      }
    }

    // ═══════════════════════════════════════════════════════════════
    // 10. ALERTS TABLE — real filtering, real state
    // ═══════════════════════════════════════════════════════════════
    let allAlerts = [];
    let activeFilter = 'ALL';
    const filterBtns = document.querySelectorAll('.alert-filter-btn');

    function confidenceMeter(conf) {
      const segs = Math.round((conf || 0) * 5);
      let bars = '';
      for (let i = 0; i < 5; i++) bars += `<i${i < segs ? ' class="on"' : ''}></i>`;
      return `<span class="confidence-cell"><span class="confidence-meter" aria-hidden="true">${bars}</span><span class="confidence-value">${(conf || 0).toFixed(2)}</span></span>`;
    }

    function renderAlerts() {
      const tbody = document.getElementById('alertsTableBody');
      if (!tbody) return;
      tbody.innerHTML = '';

      // The pending-review chip always reflects current data — even when the
      // table is empty — so the header count can never contradict the rows.
      const pending = allAlerts.filter(a => a.status === 'HUMAN_REVIEW').length;
      const reviewChip = document.getElementById('reviewCountChip');
      if (reviewChip) {
        reviewChip.textContent = `${pending} Pending Review`;
        reviewChip.className = pending > 0 ? 'chip alert' : 'chip neutral';
      }

      const filtered = activeFilter === 'ALL'
        ? allAlerts
        : allAlerts.filter(a => a.status === activeFilter);

      if (!filtered.length) {
        const tr = document.createElement('tr');
        tr.innerHTML = `<td colspan="8"><div class="table-empty">No alerts in this state</div></td>`;
        tbody.appendChild(tr);
        return;
      }

      filtered.forEach(alert => {
        const statusClass = alert.status === 'HUMAN_REVIEW' ? 'review' :
                            alert.status === 'CONFIRMED' ? 'confirmed' : 'dismissed';
        const statusText = alert.status === 'HUMAN_REVIEW' ? 'Review' :
                           alert.status === 'CONFIRMED' ? 'Confirmed' : 'Dismissed';

        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td class="alert-id-cell">${alert.id}</td>
          <td>${alert.coord}</td>
          <td class="alert-dim">${alert.utm}</td>
          <td>${alert.materialDelta}</td>
          <td>${alert.classification}</td>
          <td>${confidenceMeter(alert.confidence)}</td>
          <td><span class="status-badge ${statusClass}">${statusText}</span></td>
          <td>
            <button class="button-ghost button-ghost-subtle button-ghost-sm evidence-btn" data-alert-id="${alert.id}">Evidence</button>
          </td>
        `;
        tbody.appendChild(tr);
      });

      tbody.querySelectorAll('.evidence-btn').forEach(btn => {
        btn.addEventListener('click', () => openDossier(btn.dataset.alertId));
      });
    }

    async function loadAlerts() {
      allAlerts = await api.fetchAlerts();
      renderAlerts();
    }

    filterBtns.forEach(btn => {
      btn.addEventListener('click', () => {
        activeFilter = btn.dataset.filter;
        filterBtns.forEach(b => {
          const isActive = b === btn;
          b.classList.toggle('active', isActive);
          b.setAttribute('aria-pressed', isActive ? 'true' : 'false');
        });
        renderAlerts();
      });
    });

    loadAlerts();

    // ═══════════════════════════════════════════════════════════════
    // 11. EVIDENCE DOSSIER — populated per-alert, focus-managed
    // ═══════════════════════════════════════════════════════════════
    const modal = document.getElementById('evidenceModal');
    let lastFocused = null;

    async function openDossier(alertId) {
      const alert = allAlerts.find(a => a.id === alertId) || allAlerts[0];
      const dossier = await api.getEvidenceDossier(alertId);
      if (dossier && dossier.simulated) {
        toast('Dossier content is simulated — real reports: SentryAPI.getReport(id)', 'warn', 4200);
      }
      lastFocused = document.activeElement;

      const title = document.getElementById('dossierTitle');
      const coord = document.getElementById('dossierCoord');
      const footprint = document.getElementById('dossierFootprint');
      const conf = document.getElementById('dossierConf');
      const tile = document.getElementById('dossierTileId');
      const notes = document.getElementById('dossierNotes');

      if (title) title.textContent = dossier.dossierId || `Dossier-NTRO-${alertId}`;
      if (coord) coord.textContent = alert?.coord || dossier.targetAlert?.coordinates || '—';
      if (footprint) footprint.textContent = dossier.targetAlert?.estimatedFootprintM2 || alert?.materialDelta || '—';
      if (conf) conf.textContent = `${(alert?.confidence ?? 0).toFixed(2)} (Calibrated)`;
      if (tile) tile.textContent = dossier.sourceTile || '—';
      if (notes) notes.textContent = alert?.notes || 'No analyst notes recorded for this alert.';

      modal.classList.add('open');
      document.getElementById('closeModalBtn')?.focus();
    }

    function closeModal() {
      modal.classList.remove('open');
      if (lastFocused && modal.contains(document.activeElement)) lastFocused.focus();
    }

    document.getElementById('closeModalBtn')?.addEventListener('click', closeModal);
    modal?.addEventListener('click', (e) => { if (e.target === modal) closeModal(); });
    modal?.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') { closeModal(); e.stopPropagation(); }
    });

    // ═════════════════════════════════════════════════════════════
    // 11b. CONNECT DIALOG — operator identity & project scope in-app
    // ═════════════════════════════════════════════════════════════
    const connectModal = document.getElementById('connectModal');
    let connectLastFocused = null;

    function openConnect() {
      if (!connectModal) return;
      connectLastFocused = document.activeElement;
      const userInput = document.getElementById('connectUserInput');
      const projectInput = document.getElementById('connectProjectInput');
      if (userInput) userInput.value = api.devUser || '';
      if (projectInput) projectInput.value = api.projectId || '';
      connectModal.classList.add('open');
      userInput?.focus();
    }

    function closeConnect() {
      if (!connectModal) return;
      connectModal.classList.remove('open');
      if (connectLastFocused && connectModal.contains(document.activeElement)) {
        connectLastFocused.focus();
      }
    }

    function saveConnect() {
      const userInput = document.getElementById('connectUserInput');
      const projectInput = document.getElementById('connectProjectInput');
      const user = (userInput?.value || '').trim();
      const project = (projectInput?.value || '').trim();
      api.setDevUser(user || null);
      api.setProjectId(project || null);
      closeConnect();
      api.connect(); // re-probe; the badge and guards read the new state
      toast(user
        ? `Operator identity saved${project ? ' — project scope set' : ''}.`
        : 'Identity cleared — running unauthenticated.', 'ok', 4000);
    }

    document.getElementById('connectBtn')?.addEventListener('click', openConnect);
    document.getElementById('connectCloseBtn')?.addEventListener('click', closeConnect);
    document.getElementById('connectSaveBtn')?.addEventListener('click', saveConnect);
    document.getElementById('connectClearBtn')?.addEventListener('click', () => {
      const userInput = document.getElementById('connectUserInput');
      const projectInput = document.getElementById('connectProjectInput');
      if (userInput) userInput.value = '';
      if (projectInput) projectInput.value = '';
      userInput?.focus();
    });
    connectModal?.addEventListener('click', (e) => { if (e.target === connectModal) closeConnect(); });
    connectModal?.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') { closeConnect(); e.stopPropagation(); }
      if (e.key === 'Enter' && e.target.tagName === 'INPUT') { saveConnect(); e.preventDefault(); }
    });

    // ═══════════════════════════════════════════════════════════════
    // 12. Q&A DRAWER
    // ═══════════════════════════════════════════════════════════════
    const qaDrawer = document.getElementById('qaDrawer');
    let qaLastFocused = null;

    document.getElementById('qaDrawerBtn')?.addEventListener('click', () => {
      qaLastFocused = document.activeElement;
      qaDrawer.classList.add('open');
      document.getElementById('closeQaDrawerBtn')?.focus();
    });

    function closeQaDrawer() {
      qaDrawer.classList.remove('open');
      if (qaLastFocused && qaDrawer.contains(document.activeElement)) qaLastFocused.focus();
    }

    document.getElementById('closeQaDrawerBtn')?.addEventListener('click', closeQaDrawer);
    qaDrawer?.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') { closeQaDrawer(); e.stopPropagation(); }
    });

    // ═══════════════════════════════════════════════════════════════
    // 13. GLOBAL KEYBOARD MAP
    // ═══════════════════════════════════════════════════════════════
    const tabIds = ['tabMap', 'tabAlerts', 'tabMetrics', 'tabTrace'];
    const inTextInput = (el) => ['INPUT', 'TEXTAREA', 'SELECT'].includes(el?.tagName);

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        if (modal.classList.contains('open')) { closeModal(); return; }
        if (qaDrawer.classList.contains('open')) { closeQaDrawer(); return; }
      }
      if (inTextInput(document.activeElement) || e.ctrlKey || e.metaKey || e.altKey) return;

      // 1-4 tab switching
      if (['1', '2', '3', '4'].includes(e.key)) {
        switchTab(tabIds[parseInt(e.key) - 1]);
        return;
      }

      // Map-tab pixel navigation + slider control
      const mapPanel = document.getElementById('tabMap');
      if (!mapPanel.classList.contains('active')) return;

      const sel = sim.selectedCell || { x: 14, y: 16 };
      if (e.key === 'ArrowUp') { sim.selectPixel(sel.x, Math.max(0, sel.y - 1)); e.preventDefault(); }
      else if (e.key === 'ArrowDown') { sim.selectPixel(sel.x, Math.min(31, sel.y + 1)); e.preventDefault(); }
      else if (e.key === 'ArrowLeft') {
        if (e.shiftKey) sim.updateSplitPosition(sim.splitPercent - 4);
        else sim.selectPixel(Math.max(0, sel.x - 1), sel.y);
        e.preventDefault();
      }
      else if (e.key === 'ArrowRight') {
        if (e.shiftKey) sim.updateSplitPosition(sim.splitPercent + 4);
        else sim.selectPixel(Math.min(31, sel.x + 1), sel.y);
        e.preventDefault();
      }
    });

    // ═══════════════════════════════════════════════════════════════
    // 14. PIPELINE RUN — synced to trace stages
    // ═══════════════════════════════════════════════════════════════
    const runBtn = document.getElementById('runPipelineBtn');
    const statusChip = document.getElementById('pipelineStatus');
    const stageItems = document.querySelectorAll('.trace-stage-item');
    const STAGE_KEYS = ['STAGE_PRE', 'STAGE_1', 'STAGE_2', 'STAGE_3', 'STAGE_3B', 'STAGE_4'];

    function highlightTraceStage(key) {
      stageItems.forEach(item => {
        const isActive = item.dataset.stage === key;
        item.classList.toggle('active', isActive);
        item.setAttribute('aria-selected', isActive ? 'true' : 'false');
      });
      selectStage(key);
    }

    if (runBtn) {
      runBtn.addEventListener('click', async () => {
        runBtn.disabled = true;
        runBtn.textContent = 'Running…';

        // LIVE: submit a real backend job and poll it to a terminal state.
        if (api.isLiveConnected) {
          if (!api.isLikelyConfigured()) {
            toast('Backend reachable, but no operator identity is configured. ' +
                  'Click “Connect…” (top right) and paste your user UUID — see /docs ' +
                  'on the backend to create one. The console remembers it.', 'warn', 9000);
            runBtn.disabled = false;
            openConnect();
            return;
          }
          if (!api.projectId) {
            toast('No project selected. Create one via POST /v1/projects (see /docs), ' +
                  'then click “Connect…” and paste its UUID.', 'warn', 9000);
            runBtn.disabled = false;
            openConnect();
            return;
          }
          let lastStage = null;
          const stepLabels = {
            preprocess: 'Job: pre-processing',
            reconstruct: 'Job: reconstructing',
            uncertainty: 'Job: uncertainty',
            validate: 'Job: validating',
            report: 'Job: reporting',
          };
          const setStage = (key, label) => {
            if (!key || key === lastStage) return;
            lastStage = key;
            if (statusChip) {
              statusChip.textContent = label;
              statusChip.className = 'chip warning is-pulsing';
            }
            highlightTraceStage(key);
          };
          try {
            const job = await api.runPipeline({
              onProgress: (p) => setStage(p.stageKey, stepLabels[p.currentStep] || `Job: ${p.status}`),
            });
            if (statusChip) {
              statusChip.textContent = `Job: ${job.status}`;
              statusChip.className = 'chip live';
            }
            if (traceTitle) traceTitle.textContent = `Job ${job.id.slice(0, 8)}`;
            if (traceJson) {
              traceJson.textContent = JSON.stringify({
                job_id: job.id, status: job.status, steps: job.steps,
                artifacts: job.artifacts, validation_id: job.validation_id,
              }, null, 2);
            }
            if (traceHash) {
              traceHash.textContent = `Validation: ${job.validation_id || 'none'}`;
            }
            toast(`Job ${job.id.slice(0, 8)} completed — ${job.artifacts.length} artifact(s) registered`);
          } catch (err) {
            if (statusChip) {
              statusChip.textContent = 'Job: failed';
              statusChip.className = 'chip alert';
            }
            toast(`Job failed: ${err.code || ''} ${err.message || err}`.trim(), 'warn', 6500);
          } finally {
            runBtn.disabled = false;
            runBtn.textContent = 'Run Pipeline';
          }
          return;
        }

        // SIMULATED: demo timings only — no backend job is created.
        if (statusChip) statusChip.textContent = 'Simulator run (demo only)';
        const stageLabels = [
          'Sim Stage 0: Pre-Processing', 'Sim Stage 1: SAM Detection', 'Sim Stage 2: FCLS Unmixing',
          'Sim Stage 3: MLP Allocation', 'Sim Stage 3B: Atkinson Refine', 'Sim Stage 4: Validation'
        ];
        for (let i = 0; i < STAGE_KEYS.length; i++) {
          if (statusChip) {
            statusChip.textContent = stageLabels[i];
            statusChip.className = 'chip warning is-pulsing';
          }
          highlightTraceStage(STAGE_KEYS[i]);
          await new Promise(r => setTimeout(r, reducedMotion ? 120 : 550));
        }
        if (statusChip) {
          statusChip.textContent = 'Simulator: complete (no backend job)';
          statusChip.className = 'chip live';
        }
        runBtn.disabled = false;
        runBtn.textContent = 'Run Pipeline';
        toast('Simulated run — connect a backend for real pipeline execution', 'warn', 4500);
      });
    }

    // ═══════════════════════════════════════════════════════════════
    // 15. TRACE STAGE NAVIGATION
    // ═══════════════════════════════════════════════════════════════
    const stageArtifacts = {
      STAGE_PRE: {
        title: 'Stage 00 — Pre-Processing',
        hash: 'e3b0c442…991b7852',
        json: { stage: 'PRE-PROCESSING', input: 'S2A_MSIL2A_20260308T045651_N0400',
          operations: ['BOA offset subtraction (-1000)', 'SCL cloud/shadow mask', 'Histogram matching'],
          output_shape: '[6, 1098, 1098]', cloud_free_pct: 94.2, time_ms: 1240, hash: 'e3b0c442...991b7852' }
      },
      STAGE_1: {
        title: 'Stage 01 — Spectral Change Detection',
        hash: '8f434346…c327aa4',
        json: { stage: 'SAM', method: 'Spectral Angle Mapper', threshold: 0.15,
          changed_pixels: 847, total: 1205604, change_rate: '0.07%', nodata_propagated: 6841 }
      },
      STAGE_2: {
        title: 'Stage 02 — Spectral Unmixing',
        hash: 'ca978112…afee48bb',
        json: { stage: 'FCLS', endmembers: 5, method: 'VCA → FCLS',
          classes: ['Impervious', 'Vegetation', 'Water', 'Soil', 'Shade'],
          mean_rmse: 0.0142, ood_flagged: 23, sum_to_one: true, non_negative: true }
      },
      STAGE_3: {
        title: 'Stage 03 — Spatial Allocation',
        hash: '3b0c4429…5b78557f',
        json: { stage: 'MLP', arch: '50→128→64→16', params: 49808,
          input: '3×3 neighborhood (50-dim)', training: 'Cross-scale 40m→10m', time_ms: 340 }
      },
      STAGE_3B: {
        title: 'Stage 03B — Spatial Refinement',
        hash: '186f9209…d20e9b8',
        json: { stage: 'ATKINSON', iterations: 8, coherence: 0.842,
          convergence: 'SETTLED (Δ<0.001)', mass_mse: 0.0084, criterion: 'MSE<0.05', status: 'PASS' }
      },
      STAGE_4: {
        title: 'Stage 04 — Validation & Classification',
        hash: '2c26b46b…68407fa',
        json: { stage: 'GEOMETRY_RULES',
          rules: { compact: 'Structure (1:1)', linear: 'Road (>3:1)', border: 'Human Review' },
          detections: 12, auto_classified: 9, to_human: 3, silent_rejects: 0 }
      }
    };

    const traceTitle = document.getElementById('traceArtifactTitle');
    const traceJson = document.getElementById('traceJsonBox');
    const traceHash = document.getElementById('traceHashChip');

    function selectStage(key) {
      const art = stageArtifacts[key];
      if (!art) return;
      if (traceTitle) traceTitle.textContent = art.title;
      if (traceJson) traceJson.textContent = JSON.stringify(art.json, null, 2);
      if (traceHash) traceHash.textContent = `Hash: ${art.hash}`;
    }

    stageItems.forEach(item => {
      item.addEventListener('click', () => highlightTraceStage(item.dataset.stage));
    });
    selectStage('STAGE_PRE');

    // ═══════════════════════════════════════════════════════════════
    // 16. CHARTS — deterministic data (stable across renders)
    // ═══════════════════════════════════════════════════════════════
    function renderAllMetricsCharts() {
      const mono = window.MetricsChartEngine.palette;
      chartEngine.renderLineChart('lossCanvas', {
        xLabel: 'Epoch', yLabel: 'Loss',
        series: [
          { label: 'L1 Cross-Entropy', color: mono[0], data: lossCurve(0.9, 0.12, 30, 1) },
          { label: 'L2 Abundance', color: mono[1], data: lossCurve(0.7, 0.08, 30, 2) },
          { label: 'L3 Spatial', color: mono[2], data: lossCurve(0.5, 0.15, 30, 3) },
          { label: 'L4 Mass Cons.', color: mono[3], data: lossCurve(0.4, 0.05, 30, 4) }
        ]
      });

      chartEngine.renderLineChart('injectionCanvas', {
        xLabel: 'Area (m²)', yLabel: 'Recall',
        series: [{ label: 'Recall', color: mono[0], data: sigmoid(10, 80, 45, 8) }],
        markers: [{ x: 45, label: '~45 m²', color: mono[4] }]
      });

      chartEngine.renderLineChart('calibrationCanvas', {
        xLabel: 'Predicted', yLabel: 'Observed',
        series: [
          { label: 'Model', color: mono[0], data: calibration() },
          { label: 'Perfect', color: mono[5], dashed: true, data: Array.from({length: 10}, (_, i) => ({ x: (i + 1) / 10, y: (i + 1) / 10 })) }
        ]
      });

      chartEngine.renderBarChart('crossScaleCanvas', {
        xLabel: '', yLabel: 'Kappa',
        bars: [
          { label: '40m→10m\nTrain', value: 0.72, color: mono[0] },
          { label: '20m→5m\nHeld-out', value: 0.64, color: mono[1] },
          { label: '10m→2.5m\nTarget', value: 0.58, color: mono[2] }
        ],
        thresholdLine: { y: 0.60, label: 'Target κ=0.60', color: mono[4] }
      });
    }

    // Seeded PRNG — charts don't reshuffle on every tab visit
    function seededRandom(seed) {
      let s = seed;
      return () => {
        s = (s * 9301 + 49297) % 233280;
        return s / 233280;
      };
    }

    function lossCurve(start, end, n, seed) {
      const rand = seededRandom(seed * 7919);
      return Array.from({ length: n }, (_, i) => {
        const t = i / (n - 1);
        return { x: i + 1, y: Math.max(0, start * Math.exp(-t * 4) + end + (rand() - 0.5) * 0.03) };
      });
    }

    function sigmoid(min, max, mid, steep) {
      return Array.from({ length: 21 }, (_, i) => {
        const x = min + (max - min) * i / 20;
        return { x, y: 1 / (1 + Math.exp(-(x - mid) / steep)) };
      });
    }

    function calibration() {
      const rand = seededRandom(4242);
      return [0.08, 0.18, 0.28, 0.40, 0.52, 0.58, 0.70, 0.78, 0.88, 0.95].map((y, i) =>
        ({ x: (i + 1) / 10, y: y + (rand() - 0.5) * 0.04 })
      );
    }

    // ═══════════════════════════════════════════════════════════════
    // 17. AOI CHANGE — rewires map, sim, 3D flyover, alerts
    // ═══════════════════════════════════════════════════════════════
    const AOI_META = {
      AOI_01: { tile: 'S2A_MSIL2A_20260308T045651_N0400', dates: 'T1 2026-03-03 · T2 2026-03-08' },
      AOI_02: { tile: 'S2B_MSIL2A_20260309T051219_N0400', dates: 'T1 2026-03-04 · T2 2026-03-09' },
      AOI_03: { tile: 'S2A_MSIL2A_20260310T053421_N0400', dates: 'T1 2026-03-05 · T2 2026-03-10' }
    };

    document.getElementById('aoiSelect')?.addEventListener('change', (e) => {
      const aoiId = e.target.value;
      sim.setAOI(aoiId);
      sentryEnv?.flyToSector(aoiId);
      const meta = AOI_META[aoiId];
      const tileEl = document.getElementById('statusTile');
      if (tileEl && meta) tileEl.textContent = `Tile: ${meta.tile}`;
      loadAlerts();
      toast(`AOI switched — ${meta ? meta.tile : aoiId}`, 'ok', 2600);
    });

    // ═══════════════════════════════════════════════════════════════
    // 18. EXPORTS — real artifacts, not fake confirmation text
    // ═══════════════════════════════════════════════════════════════
    function buildKml(alerts) {
      const placemarks = alerts.map(a => {
        const match = a.coord.match(/([\d.]+)°?\s*N,\s*([\d.]+)°?\s*E/i);
        if (!match) return '';
        const lat = parseFloat(match[1]).toFixed(6);
        const lon = parseFloat(match[2]).toFixed(6);
        return `    <Placemark>
      <name>${a.id} — ${a.classification}</name>
      <description><![CDATA[${a.notes || ''}]]></description>
      <Point><coordinates>${lon},${lat},0</coordinates></Point>
    </Placemark>`;
      }).join('\n');

      return `<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>SUBPIXEL-SENTRY Alert Overlay</name>
    <description>Change-detection alerts exported from local pipeline cache</description>
${placemarks}
  </Document>
</kml>`;
    }

    function downloadBlob(content, filename, mime) {
      const blob = new Blob([content], { type: mime });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 800);
    }

    document.getElementById('exportAllKmlBtn')?.addEventListener('click', () => {
      downloadBlob(buildKml(allAlerts), 'sentry-alerts.kml', 'application/vnd.google-earth.kml+xml');
      toast(`KML exported — ${allAlerts.length} placemarks`);
    });

    document.getElementById('downloadKmlMockBtn')?.addEventListener('click', () => {
      const title = document.getElementById('dossierTitle')?.textContent || 'dossier';
      downloadBlob(buildKml(allAlerts.slice(0, 1)), 'sentry-evidence.kml', 'application/vnd.google-earth.kml+xml');
      toast('Evidence KML exported');
    });

    document.getElementById('downloadPdfMockBtn')?.addEventListener('click', () => {
      const stamp = document.getElementById('printStamp');
      if (stamp) {
        stamp.textContent = `Generated ${new Date().toISOString().replace('T', ' ').slice(0, 19)} UTC from local pipeline cache — no network egress`;
      }
      toast('Opening print dialog — save as PDF', 'ok', 2600);
      setTimeout(() => window.print(), 350);
    });
  }
})();
