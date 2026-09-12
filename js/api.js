/**
 * SUBPIXEL-SENTRY // BACKEND INTEGRATION API CLIENT
 * Architecture: Clean decoupling layer between UI and Python / PyTorch backend.
 * When BACKEND_URL is null or unreachable, seamlessly operates in 100% offline air-gapped simulation mode.
 */

class SentryAPIClient {
  constructor() {
    // Configurable backend URL. To connect live backend, call api.setBackendUrl('http://127.0.0.1:8000')
    this.backendUrl = localStorage.getItem('SENTRY_BACKEND_URL') || null;
    this.isLiveConnected = false;
  }

  setBackendUrl(url) {
    this.backendUrl = url;
    if (url) {
      localStorage.setItem('SENTRY_BACKEND_URL', url);
    } else {
      localStorage.removeItem('SENTRY_BACKEND_URL');
    }
  }

  /**
   * Fetch list of pre-cached Areas of Interest (AOIs)
   * Future Backend Route: GET /api/v1/aoi
   */
  async getAOIList() {
    if (this.backendUrl) {
      try {
        const res = await fetch(`${this.backendUrl}/api/v1/aoi`);
        if (res.ok) return await res.json();
      } catch (err) {
        console.warn('Backend unavailable, falling back to offline AOIs', err);
      }
    }
    return [
      {
        id: "AOI_01",
        name: "SECTOR TAWANG // LAC FORWARD AREA",
        center: [27.5861, 91.8594],
        bands: ["B2", "B3", "B4", "B8", "B11", "B12"],
        tileId: "S2A_MSIL2A_20260308T045651_N0400_R019",
        dates: ["2026-03-03", "2026-03-08"],
        resolution: "10m -> 2.5m SRM",
        status: "READY"
      },
      {
        id: "AOI_02",
        name: "SECTOR PANGONG // NORTH FINGER RIDGE",
        center: [33.7297, 78.5882],
        bands: ["B2", "B3", "B4", "B8", "B11", "B12"],
        tileId: "S2B_MSIL2A_20260309T051219_N0400_R076",
        dates: ["2026-03-04", "2026-03-09"],
        resolution: "10m -> 2.5m SRM",
        status: "READY"
      },
      {
        id: "AOI_03",
        name: "SECTOR DBO // CARAVAN DEPOT",
        center: [35.2912, 77.9288],
        bands: ["B2", "B3", "B4", "B8", "B11", "B12"],
        tileId: "S2A_MSIL2A_20260310T053421_N0400_R033",
        dates: ["2026-03-05", "2026-03-10"],
        resolution: "10m -> 2.5m SRM",
        status: "READY"
      }
    ];
  }

  /**
   * Execute Staged Inference Pipeline (Stages 1 -> 4)
   * Future Backend Route: POST /api/v1/pipeline/run
   */
  async runPipeline(aoiId, onProgress) {
    if (this.backendUrl) {
      try {
        const res = await fetch(`${this.backendUrl}/api/v1/pipeline/run`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ aoi_id: aoiId })
        });
        if (res.ok) return await res.json();
      } catch (err) {
        console.warn('Backend unavailable, running offline pipeline simulator', err);
      }
    }

    // High-fidelity offline staged execution simulator (2-second target)
    const stages = [
      { stage: "PRE_PROCESSING", label: "SCL CLOUD MASKING & 04.00 OFFSET CORRECTION", duration: 250 },
      { stage: "STAGE_1_SAM", label: "SPECTRAL ANGLE MAPPER CHANGE DETECTION", duration: 350 },
      { stage: "STAGE_2_FCLS", label: "BATCHED VECTORIZED FCLS SPECTRAL UNMIXING (CHUNK 4096)", duration: 450 },
      { stage: "STAGE_3_MLP", label: "50K-PARAM MLP SPATIAL ALLOCATION (40M->10M RECON)", duration: 350 },
      { stage: "STAGE_3B_ATKINSON", label: "ATKINSON PIXEL-SWAPPING & MASS CONSERVATION CHECK", duration: 300 },
      { stage: "STAGE_4_VALIDATION", label: "GEOMETRY CLASSIFICATION & HUMAN-REVIEW ROUTING", duration: 200 }
    ];

    for (const step of stages) {
      if (onProgress) onProgress(step);
      await new Promise(r => setTimeout(r, step.duration));
    }

    return {
      status: "COMPLETED",
      aoiId: aoiId,
      executionTimeMs: 1900,
      totalPixels: 65536,
      subpixelsResolved: 1048576,
      fclsMeanRmse: 0.0184,
      massConservationMse: 0.0112,
      alertsCount: 7
    };
  }

  /**
   * Inspect a specific 10m pixel cell: Returns spectral bands, FCLS fractions,
   * 4x4 sub-pixel label grid (16 cells at 2.5m), and Atkinson swap metrics.
   * Future Backend Route: GET /api/v1/pixel/inspect?aoi={aoi}&x={x}&y={y}
   */
  async inspectPixel(aoiId, x, y) {
    if (this.backendUrl) {
      try {
        const res = await fetch(`${this.backendUrl}/api/v1/pixel/inspect?aoi=${aoiId}&x=${x}&y=${y}`);
        if (res.ok) return await res.json();
      } catch (err) {
        // fallback
      }
    }

    // Deterministic pseudo-random synthesis based on coordinates
    const seed = (x * 73856093) ^ (y * 19349663);
    const rand = (mod) => Math.abs((Math.sin(seed * mod) * 10000) % 1);

    // 5 Physical Endmembers
    let imp = rand(1);
    let veg = rand(2);
    let water = rand(3);
    let soil = rand(4);
    let shade = rand(5);

    // Normalize so sum equals 1.000 (Fully Constrained Least Squares requirement)
    const sum = imp + veg + water + soil + shade;
    imp = Number((imp / sum).toFixed(3));
    veg = Number((veg / sum).toFixed(3));
    water = Number((water / sum).toFixed(3));
    soil = Number((soil / sum).toFixed(3));
    shade = Number((1.0 - (imp + veg + water + soil)).toFixed(3));

    // Calculate subpixel counts (out of 16 subpixels)
    const impCount = Math.round(imp * 16);
    const vegCount = Math.round(veg * 16);
    const waterCount = Math.round(water * 16);
    const soilCount = Math.round(soil * 16);
    const shadeCount = Math.max(0, 16 - (impCount + vegCount + waterCount + soilCount));

    // Construct 4x4 discrete sub-pixel grid
    const subpixels = [];
    for (let i = 0; i < impCount; i++) subpixels.push("IMPERVIOUS");
    for (let i = 0; i < vegCount; i++) subpixels.push("VEGETATION");
    for (let i = 0; i < waterCount; i++) subpixels.push("WATER");
    for (let i = 0; i < soilCount; i++) subpixels.push("SOIL");
    while (subpixels.length < 16) subpixels.push("SHADE");

    // Geometry classification
    let geometry = "DIFFUSE VEGETATION";
    let classification = "NATURAL LAND COVER";
    let alertFlag = false;

    if (imp > 0.25) {
      if (imp > 0.40 && (x % 3 === 0)) {
        geometry = "COMPACT (ASPECT 1.1:1)";
        classification = "PROBABLE STRUCTURE (BUILT-UP)";
        alertFlag = true;
      } else if (y % 4 === 0) {
        geometry = "LINEAR (ASPECT 3.8:1)";
        classification = "PROBABLE ACCESS ROAD";
        alertFlag = true;
      } else {
        geometry = "ISOLATED NEAR BORDER";
        classification = "HUMAN REVIEW REQUIRED";
        alertFlag = true;
      }
    }

    return {
      coordinates: {
        x, y,
        lat: (27.5861 + (y - 32) * 0.00009).toFixed(6),
        lon: (91.8594 + (x - 32) * 0.00009).toFixed(6),
        gridRef: `UTM-45N // E:${Math.round(452100 + x * 10)} N:${Math.round(3054100 + y * 10)}`
      },
      reflectanceBands: {
        B2: Number((0.042 + rand(11) * 0.03).toFixed(4)),
        B3: Number((0.068 + rand(12) * 0.04).toFixed(4)),
        B4: Number((0.085 + rand(13) * 0.05).toFixed(4)),
        B8: Number((0.280 + veg * 0.25).toFixed(4)),
        B11: Number((0.190 + imp * 0.22).toFixed(4)),
        B12: Number((0.140 + imp * 0.18).toFixed(4))
      },
      abundances: {
        impervious: imp,
        vegetation: veg,
        water: water,
        soil: soil,
        shade: shade
      },
      fclsRmse: Number((0.012 + rand(21) * 0.015).toFixed(4)),
      oodFlag: rand(22) > 0.95,
      atkinsonIterations: 8,
      spatialCoherenceScore: 0.842,
      massConservationMse: 0.0084,
      geometryClassification: {
        geometry,
        classification,
        alertFlag,
        confidence: Number((0.78 + rand(31) * 0.18).toFixed(2))
      },
      subpixelGrid: subpixels
    };
  }

  /**
   * Fetch real-time change detection alerts (Mode B)
   * Future Backend Route: GET /api/v1/alerts
   */
  async fetchAlerts() {
    if (this.backendUrl) {
      try {
        const res = await fetch(`${this.backendUrl}/api/v1/alerts`);
        if (res.ok) return await res.json();
      } catch (err) {
        // fallback
      }
    }

    return [
      {
        id: "ALT-2026-0391",
        aoi: "AOI_01",
        coord: "27.5874° N, 91.8612° E",
        utm: "45N 452410 3054320",
        materialDelta: "+18.7% Impervious (+75 m²)",
        geometry: "COMPACT (1.12:1)",
        classification: "PROBABLE STRUCTURE",
        confidence: 0.91,
        status: "HUMAN_REVIEW",
        notes: "Isolated new structure detected 240m from forward patrol line. No cloud interference.",
        timestamp: "2026-03-08 04:58:12 UTC",
        provenanceId: "PRV-S2A-20260308-019-B4B8B12"
      },
      {
        id: "ALT-2026-0392",
        aoi: "AOI_01",
        coord: "27.5842° N, 91.8570° E",
        utm: "45N 452120 3053980",
        materialDelta: "+24.1% Impervious (+96 m²)",
        geometry: "LINEAR (4.2:1)",
        classification: "PROBABLE ACCESS ROAD",
        confidence: 0.88,
        status: "CONFIRMED",
        notes: "Linear compaction continuous with known unpaved arterial. Connects to post.",
        timestamp: "2026-03-08 04:58:14 UTC",
        provenanceId: "PRV-S2A-20260308-019-B4B8B12"
      },
      {
        id: "ALT-2026-0393",
        aoi: "AOI_01",
        coord: "27.5910° N, 91.8645° E",
        utm: "45N 452780 3054690",
        materialDelta: "+12.4% Impervious (+50 m²)",
        geometry: "ISOLATED (1.05:1)",
        classification: "BORDER DISCREPANCY",
        confidence: 0.74,
        status: "HUMAN_REVIEW",
        notes: "Sub-pixel change near crest. Border sector flagged for manual photo-analyst validation.",
        timestamp: "2026-03-08 04:58:15 UTC",
        provenanceId: "PRV-S2A-20260308-019-B4B8B12"
      },
      {
        id: "ALT-2026-0394",
        aoi: "AOI_01",
        coord: "27.5815° N, 91.8522° E",
        utm: "45N 451920 3053640",
        materialDelta: "+38.2% Impervious (+152 m²)",
        geometry: "SQUARE SLAB (1.01:1)",
        classification: "REINFORCED HELIPAD",
        confidence: 0.96,
        status: "CONFIRMED",
        notes: "Reinforced concrete surface verified via high B11/B12 SWIR reflectance signature.",
        timestamp: "2026-03-08 04:58:16 UTC",
        provenanceId: "PRV-S2A-20260308-019-B4B8B12"
      },
      {
        id: "ALT-2026-0395",
        aoi: "AOI_01",
        coord: "27.5898° N, 91.8680° E",
        utm: "45N 452900 3054520",
        materialDelta: "+15.5% Impervious (+62 m²)",
        geometry: "COMPACT TOWER (1.0:1)",
        classification: "SENTRY TOWER FOOTING",
        confidence: 0.85,
        status: "HUMAN_REVIEW",
        notes: "Elevated vantage point on rocky promontory. Shadow analysis confirms vertical elevation.",
        timestamp: "2026-03-08 04:58:18 UTC",
        provenanceId: "PRV-S2A-20260308-019-B4B8B12"
      },
      {
        id: "ALT-2026-0401",
        aoi: "AOI_02",
        coord: "33.7312° N, 78.5910° E",
        utm: "43N 462100 3732400",
        materialDelta: "+31.0% Impervious (+124 m²)",
        geometry: "COMPACT CLUSTER",
        classification: "SHELTER COMPOUND",
        confidence: 0.94,
        status: "CONFIRMED",
        notes: "Cluster of 3 contiguous sub-pixel units. FCLS spectral match matches prefabricated shelter roof.",
        timestamp: "2026-03-09 05:14:02 UTC",
        provenanceId: "PRV-S2B-20260309-076-B4B8B12"
      },
      {
        id: "ALT-2026-0402",
        aoi: "AOI_02",
        coord: "33.7285° N, 78.5840° E",
        utm: "43N 461500 3732100",
        materialDelta: "+22.4% Impervious (+90 m²)",
        geometry: "LINEAR SHORE JETTY",
        classification: "FINGER 4 BOAT RAMP",
        confidence: 0.92,
        status: "CONFIRMED",
        notes: "Concrete ramp extension protruding 18m into lake boundary. Highly coherent geometry.",
        timestamp: "2026-03-09 05:14:05 UTC",
        provenanceId: "PRV-S2B-20260309-076-B4B8B12"
      },
      {
        id: "ALT-2026-0403",
        aoi: "AOI_02",
        coord: "33.7340° N, 78.5980° E",
        utm: "43N 462700 3732700",
        materialDelta: "+16.8% Impervious (+67 m²)",
        geometry: "CURVED REVETMENT",
        classification: "RIDGE BERM DEFENSE",
        confidence: 0.79,
        status: "HUMAN_REVIEW",
        notes: "Excavated talus scree trench along crest line. High shadow proportion.",
        timestamp: "2026-03-09 05:14:08 UTC",
        provenanceId: "PRV-S2B-20260309-076-B4B8B12"
      },
      {
        id: "ALT-2026-0411",
        aoi: "AOI_03",
        coord: "35.2934° N, 77.9304° E",
        utm: "43N 402800 3906200",
        materialDelta: "+42.1% Impervious (+168 m²)",
        geometry: "LINEAR APRON",
        classification: "RUNWAY APRON EXPANSION",
        confidence: 0.97,
        status: "CONFIRMED",
        notes: "Major surface stabilization alongside DBO main landing strip. Compacted gravel grade.",
        timestamp: "2026-03-10 05:36:40 UTC",
        provenanceId: "PRV-S2A-20260310-033-B4B8B12"
      },
      {
        id: "ALT-2026-0412",
        aoi: "AOI_03",
        coord: "35.2890° N, 77.9240° E",
        utm: "43N 402200 3905800",
        materialDelta: "+28.4% Impervious (+114 m²)",
        geometry: "BERMED RECTANGLE",
        classification: "FUEL STORAGE BLADDER",
        confidence: 0.89,
        status: "HUMAN_REVIEW",
        notes: "Earthen containment dike around new synthetic membrane installation.",
        timestamp: "2026-03-10 05:36:42 UTC",
        provenanceId: "PRV-S2A-20260310-033-B4B8B12"
      },
      {
        id: "ALT-2026-0413",
        aoi: "AOI_03",
        coord: "35.2965° N, 77.9350° E",
        utm: "43N 403200 3906600",
        materialDelta: "+14.2% Impervious (+57 m²)",
        geometry: "LINEAR TRACK",
        classification: "SURFACE LEVELLING / MORAINE",
        confidence: 0.81,
        status: "DISMISSED",
        notes: "Seasonal glacial melt displacement. Natural sediment deposition verified by multi-date SAM.",
        timestamp: "2026-03-10 05:36:44 UTC",
        provenanceId: "PRV-S2A-20260310-033-B4B8B12"
      }
    ];
  }

  /**
   * Update Alert Status (Human-in-the-loop analyst triage)
   * Future Backend Route: POST /api/v1/alerts/{id}/triage
   */
  async updateAlertStatus(alertId, newStatus, overrideNotes) {
    if (this.backendUrl) {
      try {
        const res = await fetch(`${this.backendUrl}/api/v1/alerts/${alertId}/triage`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ status: newStatus, notes: overrideNotes })
        });
        if (res.ok) return await res.json();
      } catch (err) {
        // fallback
      }
    }

    return {
      success: true,
      alertId,
      newStatus,
      loggedAt: new Date().toISOString(),
      operatorId: "OP-NTRO-4182"
    };
  }

  /**
   * Fetch Scientific Validation Metrics & Baseline Records
   * Future Backend Route: GET /api/v1/metrics/validation
   */
  async getValidationMetrics() {
    if (this.backendUrl) {
      try {
        const res = await fetch(`${this.backendUrl}/api/v1/metrics/validation`);
        if (res.ok) return await res.json();
      } catch (err) {
        // fallback
      }
    }

    return {
      kpis: {
        overallAccuracy: 74.2,
        kappa: 0.64,
        minDetectableSynthetic: 45,
        minDetectableRealWorld: "100-150",
        esaWorldCoverAgreement: 78.6,
        empiricalFpRate: 3.8
      },
      lossHistory: {
        epochs: [1, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50],
        L1_temporal: [0.42, 0.28, 0.19, 0.14, 0.11, 0.09, 0.08, 0.075, 0.072, 0.070, 0.069],
        L2_abundance: [0.38, 0.22, 0.15, 0.11, 0.085, 0.068, 0.054, 0.045, 0.039, 0.035, 0.032],
        L3_smoothness: [0.55, 0.39, 0.29, 0.22, 0.18, 0.15, 0.13, 0.115, 0.105, 0.098, 0.092],
        L4_reconstruction: [0.62, 0.44, 0.32, 0.25, 0.20, 0.17, 0.145, 0.13, 0.12, 0.112, 0.108]
      },
      injectionTestSweep: {
        sizes_m2: [10, 20, 30, 40, 45, 50, 60, 70, 80],
        recall: [0.08, 0.22, 0.44, 0.71, 0.88, 0.94, 0.98, 1.00, 1.00],
        falseAlarmRate: [0.02, 0.025, 0.029, 0.032, 0.035, 0.038, 0.041, 0.042, 0.044]
      },
      confidenceCalibration: {
        predictedBuckets: [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
        observedPrecision: [0.12, 0.19, 0.31, 0.42, 0.51, 0.62, 0.73, 0.82, 0.92, 0.98]
      },
      crossScaleStressTest: {
        domain40mTo10m: { kappa: 0.68, oa: 76.4 },
        heldOut20mTo5m: { kappa: 0.61, oa: 71.8 },
        transferabilityGap: "0.07 Kappa (Framed as conservative lower bound for 10m->2.5m)"
      }
    };
  }

  /**
   * Generate Mode C Intelligence Evidence Sheet Dossier
   * Future Backend Route: GET /api/v1/evidence/{alertId}
   */
  async getEvidenceDossier(alertId) {
    if (this.backendUrl) {
      try {
        const res = await fetch(`${this.backendUrl}/api/v1/evidence/${alertId}`);
        if (res.ok) return await res.json();
      } catch (err) {
        // fallback
      }
    }

    return {
      dossierId: `DOSSIER-NTRO-${alertId}`,
      classification: "SECRET // NATIONAL TECHNICAL RESEARCH ORGANISATION",
      generatedAt: new Date().toUTCString(),
      sourceTile: "S2A_MSIL2A_20260308T045651_N0400_R019_T45RVP",
      acquisitionT1: "2026-03-03 04:56:51 UTC",
      acquisitionT2: "2026-03-08 04:56:51 UTC",
      pipelineVersion: "SUBPIXEL-SENTRY v1.0.4-RELEASE (STAGED_FCLS_MLP)",
      endmemberMatrixId: "EM-VCA-LAC-SECTOR-01 (N=5: IMP, VEG, WAT, SOI, SHA)",
      targetAlert: {
        alertId,
        coordinates: "27.587421° N, 91.861208° E",
        utmGrid: "45N 452410 3054320",
        detectedClass: "PROBABLE STRUCTURE (COMPACT 1.12:1)",
        estimatedFootprintM2: "75 m² (+18.7% subpixel fraction)",
        calibratedConfidence: 0.91,
        fclsResidualRmse: 0.0142,
        massConservationDeltaMse: 0.0081
      },
      externalValidation: {
        esaWorldCoverCrossCheck: "BUILT-UP CLASS CONFIRMED (78.6% baseline concordance)",
        injectionTestReliability: "RECALL > 90% (Threshold for >45 m²)",
        sclCloudShadowExclusion: "PASSED (0.00% cloud probability)"
      },
      provenanceChain: {
        hashAlgorithm: "SHA-256 (MOCK CRYPTOGRAPHIC CHAIN OF CUSTODY)",
        stage1Hash: "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        stage2Hash: "8f434346648f6b96df89dda901c5176b10a6d83961dd3c1ac88b59b2dc327aa4",
        stage3Hash: "ca978112ca1bbdcafac231b39a23dc4da786eff8147c4e72b9807785afee48bb",
        stage4Hash: "3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b8557",
        operatorSignature: "OP-NTRO-4182 // SIGNED BY TACTICAL EXPLOITATION UNIT"
      }
    };
  }
}

// Global API singleton
window.SentryAPI = new SentryAPIClient();
