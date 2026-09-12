/**
 * SENTRY // BACKEND API CLIENT
 *
 * Talks to the real FastAPI control plane (/v1/...). All routes match
 * backend/routers/*.py exactly. Authentication uses a Supabase JWT
 * (Authorization: Bearer) when a token is configured, otherwise the
 * X-Dev-User header when the backend runs with DEV_AUTH=true.
 *
 * Live vs simulated: job submission, job tracking, validations, reports,
 * artifacts, projects, scenes, models and the Copernicus connector are real
 * backend flows. The alerts table, pixel inspector and evidence dossiers have
 * NO backend counterpart yet (no alerts domain in the schema) — those methods
 * are explicitly marked SIMULATED and serve deterministic local data instead
 * of silently pretending the backend answered.
 *
 * Configuration (browser console or another script):
 *   SentryAPI.setBackendUrl('http://127.0.0.1:8000')  // default
 *   SentryAPI.setToken('<supabase jwt>')              // production auth
 *   SentryAPI.setDevUser('<user uuid>')               // dev header (DEV_AUTH=true)
 *   SentryAPI.setProjectId('<project uuid>')          // job submission scope
 *
 * Events: dispatches window event 'sentry-connection' with
 * {detail: {connected: boolean, health?: object, error?: string}} so the UI
 * can show a live/offline badge.
 */

const DEFAULT_BACKEND_URL = 'http://127.0.0.1:8000';
const TERMINAL_JOB_STATES = ['COMPLETED', 'FAILED', 'CANCELLED'];

class SentryApiError extends Error {
  constructor(code, message, status = null, cause = null) {
    super(message);
    this.name = 'SentryApiError';
    this.code = code;     // stable backend code, e.g. AUTH_FORBIDDEN, or NETWORK
    this.status = status; // HTTP status, if any
    this.cause = cause;
  }
}

class SentryAPIClient {
  constructor() {
    this.backendUrl = localStorage.getItem('SENTRY_BACKEND_URL') || DEFAULT_BACKEND_URL;
    this.token = localStorage.getItem('SENTRY_AUTH_TOKEN') || null;
    this.devUser = localStorage.getItem('SENTRY_DEV_USER') || null;
    this.projectId = localStorage.getItem('SENTRY_PROJECT_ID') || null;
    this.isLiveConnected = null; // null unknown, true live, false offline
    this._connecting = null;
  }

  // ---- configuration -------------------------------------------------------

  setBackendUrl(url) {
    this.backendUrl = url || DEFAULT_BACKEND_URL;
    if (url) localStorage.setItem('SENTRY_BACKEND_URL', url);
    else localStorage.removeItem('SENTRY_BACKEND_URL');
    this.isLiveConnected = null; // force re-detection
  }

  setToken(token) {
    this.token = token || null;
    if (token) localStorage.setItem('SENTRY_AUTH_TOKEN', token);
    else localStorage.removeItem('SENTRY_AUTH_TOKEN');
  }

  setDevUser(userId) {
    this.devUser = userId || null;
    if (userId) localStorage.setItem('SENTRY_DEV_USER', userId);
    else localStorage.removeItem('SENTRY_DEV_USER');
  }

  setProjectId(projectId) {
    this.projectId = projectId || null;
    if (projectId) localStorage.setItem('SENTRY_PROJECT_ID', projectId);
    else localStorage.removeItem('SENTRY_PROJECT_ID');
  }

  isLikelyConfigured() {
    return Boolean(this.token || this.devUser);
  }

  // ---- transport -----------------------------------------------------------

  async _request(path, { method = 'GET', body = undefined, query = undefined, auth = true } = {}) {
    let url;
    try {
      url = new URL(path, this.backendUrl + (this.backendUrl.endsWith('/') ? '' : '/'));
      for (const [k, v] of Object.entries(query || {})) {
        if (v !== undefined && v !== null) url.searchParams.set(k, String(v));
      }
    } catch (e) {
      throw new SentryApiError('CONFIG', `invalid backend URL: ${this.backendUrl}`);
    }

    const headers = {};
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    if (auth) {
      if (this.token) headers['Authorization'] = `Bearer ${this.token}`;
      else if (this.devUser) headers['X-Dev-User'] = this.devUser;
    }

    let res;
    try {
      res = await fetch(url.toString(), {
        method,
        headers,
        body: body !== undefined ? JSON.stringify(body) : undefined,
        mode: 'cors',
      });
    } catch (err) {
      // fetch rejects on network failure and on CORS-blocked responses alike.
      throw new SentryApiError('NETWORK',
        `backend unreachable at ${this.backendUrl} (${err.message || err})`, null, err);
    }
    return this._deserialize(res);
  }

  async _deserialize(res) {
    let data = null;
    try { data = await res.json(); } catch (e) { /* 204s and empty bodies */ }
    if (!res.ok) {
      const code = data && data.error && data.error.code ? data.error.code : `HTTP_${res.status}`;
      const message = data && data.error && data.error.message ? data.error.message : res.statusText;
      throw new SentryApiError(code, message, res.status);
    }
    return data;
  }

  // ---- connection ----------------------------------------------------------

  async checkHealth() {
    // Health is intentionally unauthenticated.
    return this._request('/v1/health', { auth: false });
  }

  /** Probe the backend once and broadcast the result on 'sentry-connection'. */
  async connect() {
    if (this._connecting) return this._connecting;
    this._connecting = (async () => {
      try {
        const health = await this.checkHealth();
        this.isLiveConnected = true;
        window.dispatchEvent(new CustomEvent('sentry-connection',
          { detail: { connected: true, health } }));
        return health;
      } catch (err) {
        this.isLiveConnected = false;
        window.dispatchEvent(new CustomEvent('sentry-connection',
          { detail: { connected: false, error: err.message || String(err) } }));
        return null;
      } finally {
        this._connecting = null;
      }
    })();
    return this._connecting;
  }

  // ---- jobs (real) -----------------------------------------------------------

  /**
   * Submit a job (POST /v1/jobs) and poll it to a terminal state.
   * Mirrors JobCreate in backend/schemas.py. Returns the final JobOut view
   * (id, project_id, job_type, status, progress, steps[], artifacts[],
   * validation_id, error).
   */
  async runPipeline({
    projectId = this.projectId,
    aoiId = null,
    sceneIds = [],
    model = 'custom_mf_sr',
    mode = 'reconstruct_validate',
    referenceId = null,
    configId = null,
    validationProtocol = null,
    idempotencyKey = null,
    onProgress = null,
    pollMs = 2000,
  } = {}) {
    if (!projectId) {
      throw new SentryApiError('CONFIG',
        'no project configured: call SentryAPI.setProjectId("<project uuid>") first');
    }
    const job = await this.createJob({
      project_id: projectId,
      aoi_id: aoiId,
      scene_ids: sceneIds,
      mode,
      model,
      reference_id: referenceId,
      config_id: configId,
      validation_protocol: validationProtocol,
      idempotency_key: idempotencyKey ||
        `ui-${crypto.randomUUID()}`, // client-generated; safe to retry
    });
    if (onProgress) onProgress(this._jobProgressView(job));
    return this.watchJob(job.id, { onProgress, pollMs });
  }

  /** POST /v1/jobs — returns 201 for a new job, 200 for an idempotent replay. */
  async createJob(payload) {
    return this._request('/v1/jobs', { method: 'POST', body: payload });
  }

  /** GET /v1/jobs/{id} — current JobOut view. */
  async getJob(jobId) {
    return this._request(`/v1/jobs/${encodeURIComponent(jobId)}`);
  }

  /** POST /v1/jobs/{id}/cancel. */
  async cancelJob(jobId) {
    return this._request(`/v1/jobs/${encodeURIComponent(jobId)}/cancel`, { method: 'POST' });
  }

  /**
   * Poll GET /v1/jobs/{id} until the job reaches COMPLETED, FAILED or
   * CANCELLED. onProgress receives a UI view on every poll; resolves with the
   * final job view. Rejects with the job's error envelope on FAILED.
   */
  async watchJob(jobId, { onProgress = null, pollMs = 2000, signal = null } = {}) {
    for (;;) {
      if (signal && signal.aborted) throw new SentryApiError('CANCELLED', 'job watch aborted');
      const job = await this.getJob(jobId);
      if (onProgress) onProgress(this._jobProgressView(job));
      if (TERMINAL_JOB_STATES.includes(job.status)) {
        if (job.status === 'FAILED') {
          throw new SentryApiError(
            (job.error && job.error.code) || 'JOB_FAILED',
            (job.error && job.error.message) || 'job failed', null, job);
        }
        return job;
      }
      await new Promise((resolve) => setTimeout(resolve, pollMs));
    }
  }

  /**
   * Map a backend JobOut to the console's trace UI. The backend steps
   * (preprocess/reconstruct/uncertainty/validate/report) do not correspond
   * one-to-one with the simulator-era stage keys, so stageKey is an honest
   * approximation; `steps` always carries the real data.
   */
  _jobProgressView(job) {
    const STEP_TO_STAGE = {
      preprocess: 'STAGE_PRE',
      reconstruct: 'STAGE_2',
      uncertainty: 'STAGE_3',
      validate: 'STAGE_4',
      report: 'STAGE_4',
    };
    const steps = job.steps || [];
    const running = steps.find((s) => s.status === 'RUNNING');
    const currentStep = running ? running.name
      : steps.find((s) => s.status === 'QUEUED')?.name
      || (TERMINAL_JOB_STATES.includes(job.status) ? null : 'preprocess');
    return {
      jobId: job.id,
      status: job.status,
      progress: job.progress,
      currentStep,
      stageKey: currentStep ? (STEP_TO_STAGE[currentStep] || null) : null,
      steps,
      error: job.error,
      validationId: job.validation_id,
    };
  }

  // ---- validations, reports, artifacts (real) --------------------------------

  /** POST /v1/validations — queue a validation run for a COMPLETED job. */
  async createValidation({ jobId, referenceId = null, evaluationGridM = 2.5 }) {
    return this._request('/v1/validations', {
      method: 'POST',
      body: { job_id: jobId, reference_id: referenceId, evaluation_grid_m: evaluationGridM },
    });
  }

  /** GET /v1/validations/{id} — status, score, metric rows, uncertainty summary. */
  async getValidation(validationId) {
    return this._request(`/v1/validations/${encodeURIComponent(validationId)}`);
  }

  /** GET /v1/reports/{id} — validation report JSON summary. */
  async getReport(reportId) {
    return this._request(`/v1/reports/${encodeURIComponent(reportId)}`);
  }

  /** POST /v1/artifacts/{id}/signed-url — short-lived download URL. */
  async signArtifact(artifactId) {
    return this._request(`/v1/artifacts/${encodeURIComponent(artifactId)}/signed-url`,
      { method: 'POST' });
  }

  /** Fetch an artifact blob via a signed URL (e.g. sr.tif, report.json). */
  async downloadArtifact(artifactId) {
    const { url } = await this.signArtifact(artifactId);
    const res = await fetch(url);
    if (!res.ok) throw new SentryApiError('HTTP_' + res.status, 'artifact download failed');
    return res.blob();
  }

  // ---- projects, scenes, models, copernicus (real) ----------------------------

  /** GET /v1/projects — projects the authenticated user belongs to. */
  async listProjects() {
    return this._request('/v1/projects');
  }

  /** POST /v1/projects — creates the project; caller becomes owner. */
  async createProject(name) {
    return this._request('/v1/projects', { method: 'POST', body: { name } });
  }

  /** GET /v1/scenes/search — registered scenes intersecting an AOI. */
  async searchScenes({ projectId, aoiId, start = null, end = null, maxCloud = null, limit = 50 }) {
    return this._request('/v1/scenes/search', {
      query: {
        project_id: projectId, aoi_id: aoiId, start, end, max_cloud: maxCloud, limit,
      },
    });
  }

  /** GET /v1/models — approved model registry. */
  async listModels() {
    return this._request('/v1/models');
  }

  /** POST /v1/copernicus/search — anonymous catalogue search over a registered AOI. */
  async copernicusSearch({ projectId, aoiId, start, end, maxCloud = null, top = 20 }) {
    return this._request('/v1/copernicus/search', {
      method: 'POST',
      body: {
        project_id: projectId, aoi_id: aoiId, start, end, max_cloud: maxCloud, top,
      },
    });
  }

  /** POST /v1/copernicus/ingest — download + verify + stage + register (owner/operator). */
  async copernicusIngest({ projectId, aoiId, start, end, maxCloud = null, top = 5, download = true }) {
    return this._request('/v1/copernicus/ingest', {
      method: 'POST',
      body: {
        project_id: projectId, aoi_id: aoiId, start, end, max_cloud: maxCloud,
        top, download,
      },
    });
  }

  // ---- SIMULATED domains (no backend endpoint exists) ------------------------
  //
  // The console's alerts / pixel-inspector / dossier features describe a
  // sub-pixel change-detection domain (FCLS unmixing, Atkinson refinement,
  // alert triage) that the backend does not implement. These methods always
  // return deterministic local data. They NEVER touch the network, so they
  // cannot be mistaken for live results.

  /** SIMULATED: no backend AOI listing endpoint; UI ships its own AOI set. */
  async getAOIList() {
    console.warn('[SentryAPI] getAOIList: simulated data (backend has no AOI list endpoint)');
    return [
      { id: 'AOI_01', name: 'SECTOR TAWANG // LAC FORWARD AREA', center: [27.5861, 91.8594] },
      { id: 'AOI_02', name: 'SECTOR PANGONG // NORTH FINGER RIDGE', center: [33.7297, 78.5882] },
      { id: 'AOI_03', name: 'SECTOR DBO // CARAVAN DEPOT', center: [35.2912, 77.9288] },
    ];
  }

  /** SIMULATED: no /v1/pixel/inspect endpoint exists. */
  async inspectPixel(aoiId, x, y) {
    console.warn('[SentryAPI] inspectPixel: simulated data (no pixel-inspection endpoint)');
    const seed = (x * 73856093) ^ (y * 19349663);
    const rand = (mod) => Math.abs((Math.sin(seed * mod) * 10000) % 1);
    let imp = rand(1), veg = rand(2), water = rand(3), soil = rand(4), shade = rand(5);
    const sum = imp + veg + water + soil + shade;
    imp = Number((imp / sum).toFixed(3));
    veg = Number((veg / sum).toFixed(3));
    water = Number((water / sum).toFixed(3));
    soil = Number((soil / sum).toFixed(3));
    shade = Number((1.0 - (imp + veg + water + soil)).toFixed(3));

    const subpixels = [];
    const push = (label, n) => { for (let i = 0; i < n; i++) subpixels.push(label); };
    const impCount = Math.round(imp * 16);
    const vegCount = Math.round(veg * 16);
    const waterCount = Math.round(water * 16);
    const soilCount = Math.round(soil * 16);
    push('IMPERVIOUS', impCount);
    push('VEGETATION', vegCount);
    push('WATER', waterCount);
    push('SOIL', soilCount);
    while (subpixels.length < 16) subpixels.push('SHADE');

    let geometry = 'DIFFUSE VEGETATION';
    let classification = 'NATURAL LAND COVER';
    let alertFlag = false;
    if (imp > 0.25) {
      if (imp > 0.40 && (x % 3 === 0)) {
        geometry = 'COMPACT (ASPECT 1.1:1)';
        classification = 'PROBABLE STRUCTURE (BUILT-UP)';
        alertFlag = true;
      } else if (y % 4 === 0) {
        geometry = 'LINEAR (ASPECT 3.8:1)';
        classification = 'PROBABLE ACCESS ROAD';
        alertFlag = true;
      } else {
        geometry = 'ISOLATED NEAR BORDER';
        classification = 'HUMAN REVIEW REQUIRED';
        alertFlag = true;
      }
    }

    return {
      simulated: true,
      coordinates: {
        x, y,
        lat: (27.5861 + (y - 32) * 0.00009).toFixed(6),
        lon: (91.8594 + (x - 32) * 0.00009).toFixed(6),
        gridRef: `UTM-45N // E:${Math.round(452100 + x * 10)} N:${Math.round(3054100 + y * 10)}`,
      },
      reflectanceBands: {
        B2: Number((0.042 + rand(11) * 0.03).toFixed(4)),
        B3: Number((0.068 + rand(12) * 0.04).toFixed(4)),
        B4: Number((0.085 + rand(13) * 0.05).toFixed(4)),
        B8: Number((0.280 + veg * 0.25).toFixed(4)),
        B11: Number((0.190 + imp * 0.22).toFixed(4)),
        B12: Number((0.140 + imp * 0.18).toFixed(4)),
      },
      abundances: { impervious: imp, vegetation: veg, water, soil, shade },
      fclsRmse: Number((0.012 + rand(21) * 0.015).toFixed(4)),
      oodFlag: rand(22) > 0.95,
      atkinsonIterations: 8,
      spatialCoherenceScore: 0.842,
      massConservationMse: 0.0084,
      geometryClassification: {
        geometry,
        classification,
        alertFlag,
        confidence: Number((0.78 + rand(31) * 0.18).toFixed(2)),
      },
      subpixelGrid: subpixels,
    };
  }

  /** SIMULATED: the backend has no alerts domain. */
  async fetchAlerts() {
    console.warn('[SentryAPI] fetchAlerts: simulated data (no alerts domain in backend)');
    return [];
  }

  /** SIMULATED: no alert triage endpoint exists. */
  async updateAlertStatus(alertId, newStatus, overrideNotes) {
    console.warn('[SentryAPI] updateAlertStatus: simulated (no alerts domain in backend)');
    return { simulated: true, alertId, newStatus, notes: overrideNotes || null,
      loggedAt: new Date().toISOString() };
  }

  /**
   * SIMULATED metrics: the real per-run numbers live in
   * getValidation(id) / getReport(id); there is no aggregate-metrics endpoint.
   */
  async getValidationMetrics() {
    console.warn('[SentryAPI] getValidationMetrics: simulated (use getValidation(id) for real metrics)');
    return null;
  }

  /**
   * Evidence dossiers: the backend equivalent is a validation report. Live
   * callers should use getReport(reportId); this shim keeps the existing UI
   * contract working with clearly-simulated content.
   */
  async getEvidenceDossier(alertId) {
    console.warn('[SentryAPI] getEvidenceDossier: simulated (use getReport(id) for real reports)');
    return {
      simulated: true,
      dossierId: `DOSSIER-LOCAL-${alertId}`,
      generatedAt: new Date().toISOString(),
      note: 'Simulated dossier. Real reports: SentryAPI.getReport(reportId).',
      targetAlert: { alertId },
    };
  }
}

window.SentryApiError = SentryApiError;
window.SentryAPI = new SentryAPIClient();
