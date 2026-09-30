# 🛰️ SUBPIXEL-SENTRY
### *Tactical Land-Cover Intelligence & Zero-Trust Super-Resolution*

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.103+-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15.0+-336791.svg?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Three.js](https://img.shields.io/badge/Three.js-r128-black.svg?logo=three.js&logoColor=white)](https://threejs.org/)
[![Playwright](https://img.shields.io/badge/Tested_with-Playwright-2EAD33.svg?logo=playwright&logoColor=white)](https://playwright.dev/)
[![Copernicus](https://img.shields.io/badge/Sentinel--2-MSI_L2A-003399.svg)](https://dataspace.copernicus.eu/)

> **"Trust, but verify the AI."**  
> In tactical geospatial intelligence, synthetic hallucination is catastrophic. SUBPIXEL-SENTRY super-resolves European Space Agency (ESA) Sentinel-2 imagery from **10 m to 2.5 m Ground Sampling Distance (GSD)** across visible and near-infrared bands (B02, B03, B04, B08), then **mathematically interrogates every pixel** against physical sensor observations before any intelligence officer or analyst is allowed to rely upon it.

Built for the **Smart India Hackathon** problem statement **SIH26142** (*National Technical Research Organisation — NTRO, Space Technology*).

---

## 🎬 Tactical Launch Briefing & Action Demo

Experience SUBPIXEL-SENTRY in operation. The 23-second briefing below demonstrates raw 10m L2A acquisition, 2.5m/px neural reconstruction, real-time split-slider interrogation, and automated anomaly detection backed by an auditable Mathematical Evidence Dossier.

[![SUBPIXEL-SENTRY Launch Video](brag-output/brag.gif)](brag-output/brag.mp4)

> 📹 **[▶ Watch Full 1080p Briefing (brag.mp4)](brag-output/brag.mp4)** &nbsp;|&nbsp; 🖼️ **[High-Res Poster Frame](brag-output/brag.jpg)** &nbsp;|&nbsp; 📋 **[Storyboard & Production Plan](brag-output/brag-plan.md)**

### Briefing Breakdown
1. **The Hook (`00:00–00:04`)**: Strategic surveillance sweep across the 3D Himalayan DEM (34°15'N, 77°35'E) establishing the core doctrine: *Trust, but verify.*
2. **The Mission (`00:04–00:09`)**: Tactical console selection of Sentinel-2 L2A multispectral bands (`B02 Blue`, `B03 Green`, `B04 Red`, `B08 NIR`) and pipeline execution.
3. **The Reveal (`00:09–00:15`)**: Interactive split slider wiping across terrain, showing the 4× resolution multiplier transforming 10.0m blur into sharp 2.5m tactical detail.
4. **The Interrogation (`00:15–00:20`)**: Red tactical alert triggers on matched target signature (`99.4% confidence`) with immediate mathematical validation audit (SAM, ERGAS, SSIM).
5. **The Outro (`00:20–00:23`)**: Secure operational lockdown: *"Find the unseen. Prove it's real."*

---

## 🎯 The Core Problem & The Zero-Trust Paradigm

Standard commercial super-resolution relies on generative models (GANs, diffusion) that prioritize perceptual sharpness over physical truth. In military recon and border surveillance, this creates fatal failure modes:
* **Hallucinated Infrastructure**: Diffusion models inventing runways, vehicles, or buildings out of terrain noise.
* **Spectral Drift**: Altering the radiometric reflectance ratios between Red and NIR bands, corrupting vegetation and camouflage detection.
* **Uncalibrated Confidence**: Presenting synthetic artifacts as authoritative satellite observations.

### How SENTRY Solves This
SUBPIXEL-SENTRY enforces a strict **Zero-Trust AI Gatekeeper**:
* **Observation Scale-Back Consistency**: Reconstructed 2.5m rasters are mathematically downsampled back to 10m and compared against raw sensor data using point-spread function (PSF) kernels. Any unexplained spectral divergence triggers an immediate fail.
* **Hard Quarantine (`FAIL` Gate)**: If reconstructed tiles exceed strict physical error bounds, the job is terminated. Unverified rasters are quarantined and never served to analyst viewports.
* **Evidence Dossier Generation**: Every export is sealed with cryptographic provenance and an evidence audit detailing radiometric error, spectral angle mapping, and spatial variance.

---

## ⚡ Key Capabilities

| Capability | Technical Implementation | Operational Advantage |
|---|---|---|
| **4× Super-Resolution** | Multi-frame fusion & ESA LDSR-S2 neural models | Enhances 10m Sentinel-2 bands to **2.5m/px GSD** without expensive commercial tasking. |
| **Spectral Integrity (SAM)** | Multispectral vector dot-product across B02, B03, B04, B08 | Guarantees physical signature preservation with Spectral Angle Mapper `< 0.050 rad`. |
| **Synthesis Error (ERGAS)** | Relative dimensionless global error analysis | Ensures radiometric consistency with ERGAS `< 2.000`. |
| **3D Tactical DEM** | GPU-accelerated Three.js elevation relief with contour shaders | Real-time elevation profiling, line-of-sight checks, and solar azimuth terrain relief. |
| **Automated Alerting** | Target spectral signature matching & spatial anomaly detection | Instantly flags high-confidence anomalies (barracks, airstrips, vehicle staging). |
| **Air-Gapped & SCIF-Ready** | 100% local execution with embedded raster engines | Operates entirely disconnected from external cloud APIs for secure field deployments. |

---

## 🖥️ Operator Console Tour

The console is an instrument-grade, zero-distraction tactical web interface built with vanilla JS and hardware-accelerated WebGL.

### 1. Interactive Split Slider
Compare raw 10m Sentinel-2 inputs directly against 2.5m super-resolved outputs in real time. The smooth bi-directional slider allows analysts to inspect runway margins, building perimeters, and vehicle tracks.

### 2. 3D Tactical DEM Engine
Switches the operational view to a high-fidelity 3D elevation model of the Himalayan sector (`assets/terrain_diffuse/height/normal.jpg`). Operators can rotate the sun vector to reveal shadow-hidden terrain features, inspect topographic contours, and fly directly to sector target coordinates.

### 3. Mathematical Evidence Dossier
A tamper-evident audit modal detailing:
* **Spectral Angle Mapper (SAM)**: `0.0418 rad` (*Pass < 0.050*)
* **Relative Synthesis Error (ERGAS)**: `1.142` (*Pass < 2.000*)
* **Structural Similarity (SSIM)**: `0.968` (*Pass > 0.920*)
* **Synthetic Artifact Index**: `0.00%` (*Zero Hallucination Verified*)

---

## 🚀 Quickstart

### Option A: One-Click Launch (Windows)
Double-click **`Start-SENTRY.bat`**. This automated script:
1. Starts the `sentry-postgres` container.
2. Boots the FastAPI control plane on port `8077`.
3. Serves the static console on port `8080`.
4. Launches your default browser directly into the live console with dev authentication enabled.

To cleanly shut down all services, run **`Stop-SENTRY.bat`**.

---

### Option B: Manual Cross-Platform Setup (Linux / macOS / WSL)

#### 1. Environment & Dependencies
```bash
# Clone the repository
git clone https://github.com/SAICHARAN-TEJ/SENTRY.git
cd SENTRY

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

#### 2. Database Initialization
```bash
# Start PostgreSQL via Docker
docker run -d --name sentry-postgres -p 54322:5432 -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=sentry postgres:15

# Initialize database schema and migrations
python scripts/db_init.py --recreate
```

#### 3. Start Application Services
Open separate terminals (or background jobs):

```bash
# Terminal 1: FastAPI API Backend
export DEV_AUTH=true
export ARTIFACT_STORE=local
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8077

# Terminal 2: Static Console Server
python -m http.server 8080

# Terminal 3: Processing Worker
python -m worker.main
```

Open your browser to:
**`http://127.0.0.1:8080/index.html?backend=http://127.0.0.1:8077`**

---

## ⚙️ Architecture & Pipeline Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          INGESTION & STAGING                                │
│   Copernicus CDSE / L2A Archive ──> SAFE Archive ──> B02, B03, B04, B08     │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                       DISTRIBUTED CLAIM-LEASE QUEUE                         │
│   FastAPI Control Plane ──> PostgreSQL / Jobs Queue ──> Worker Claim        │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                     SUPER-RESOLUTION INFERENCE ENGINE                       │
│   Feathered Tiling ──> SR Model (Bicubic / Multi-Frame / ESA LDSR-S2)       │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                     MATHEMATICAL VERIFICATION SUITE                         │
│   1. Scale-Back Downsampling vs Raw Sentinel-2 (PSF Consistency)            │
│   2. Spectral Angle Mapper (SAM) across all 4 multispectral bands           │
│   3. ERGAS Synthesis Radiometric Validation                                │
│   4. Uncertainty Heatmap & Artifact Bounds Audit                            │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                         ┌─────────────┴─────────────┐
                         │ Verdict Check             │
                         └──────┬─────────────┬──────┘
                                │             │
                        [PASS / CAUTION]    [FAIL]
                                │             │
                                ▼             ▼
                      Operator Console    QUARANTINE
                      & Evidence Dossier  (Run Terminated)
```

---

## 📡 REST API Reference

The FastAPI service exposes interactive OpenAPI documentation at `http://127.0.0.1:8077/docs`.

| Endpoint | Method | Description |
|---|---|---|
| `/v1/health` | `GET` | Health status of API, database connection, and storage subsystems. |
| `/v1/dev/session` | `POST` | Generates a hermetic demo user and project session for local analysis. |
| `/v1/scenes/search` | `GET` | Searches staged L2A multispectral satellite acquisitions by AOI and date. |
| `/v1/jobs` | `POST` | Submits a new super-resolution task specifying scene, bands, and target model. |
| `/v1/jobs/{id}` | `GET` | Streams job execution progress, tiling stages, and completion status. |
| `/v1/validations/{id}` | `GET` | Returns mathematical validation scores, SAM/ERGAS indices, and verdict. |
| `/v1/reports/{id}` | `GET` | Retrieves the cryptographically sealed Evidence Dossier and audit summary. |
| `/v1/alerts` | `GET` | Fetches active anomaly alerts and tactical target signature matches. |
| `/v1/copernicus/ingest` | `POST` | Ingests Sentinel-2 L2A granules from Copernicus Data Space Ecosystem. |

---

## 🔬 Mathematical Verification Metrics

### 1. Spectral Angle Mapper (SAM)
Evaluates physical spectral distortion between the original multispectral vector $\mathbf{x}$ and the reconstructed vector $\mathbf{\hat{x}}$:

$$\text{SAM}(\mathbf{x}, \mathbf{\hat{x}}) = \arccos\left( \frac{\mathbf{x} \cdot \mathbf{\hat{x}}}{\|\mathbf{x}\|_2 \|\mathbf{\hat{x}}\|_2} \right)$$

* **Target Bound**: $\text{SAM} < 0.050 \text{ rad}$. Guarantees that spectral band ratios remain physically accurate for material classification.

### 2. ERGAS (Erreur Relative Globale Adimensionnelle de Synthèse)
Quantifies global radiometric synthesis quality normalized by the super-resolution scaling ratio:

$$\text{ERGAS} = 100 \frac{h}{l} \sqrt{\frac{1}{N} \sum_{i=1}^{N} \frac{\text{RMSE}^2(B_i)}{\mu^2(B_i)}}$$

where $\frac{h}{l} = 0.25$ (10m to 2.5m ratio), $N = 4$ bands, and $\mu(B_i)$ is the mean radiance of band $i$.
* **Target Bound**: $\text{ERGAS} < 2.000$.

### 3. Scale-Back Observation Consistency
The high-resolution prediction $I_{2.5\text{m}}$ is convolved with the Sentinel-2 sensor point spread function and decimated by factor $4\times$:

$$\Delta = \| \mathcal{D}_4(I_{2.5\text{m}} \ast \text{PSF}) - I_{10\text{m}} \|_1$$

* If $\Delta > \epsilon_{\text{threshold}}$, the model has produced details inconsistent with raw sensor physics, triggering an immediate **Hard Fail**.

---

## 📁 Repository Structure

```text
├── backend/            # FastAPI control plane, routers, auth, validation engine
├── worker/             # Claim-execute loop, tiling, inference, GeoTIFF I/O
├── supabase/           # Versioned SQL migrations (0001..0014), RLS policies, seeds
├── js/                 # Console logic, 3D terrain controller, split slider, telemetry
├── css/                # Instrument-grade tactical stylesheets
├── assets/             # 3D terrain DEM textures, local fonts, screenshots, UI assets
├── brag-output/        # Launch video (brag.mp4), preview GIF, poster frame, share copy
├── scripts/            # Database init, smoke tests, ESA weight fetchers, dev runners
├── tests/              # Pytest suite with hermetic fake database and mock providers
├── Start-SENTRY.bat    # One-click Windows launch script
└── Stop-SENTRY.bat     # One-click Windows shutdown script
```

---

## 🧪 Testing & Verification

SENTRY includes a multi-tiered test suite ensuring deterministic reliability:

```bash
# 1. Byte-compile verification
python scripts/compile_check.py

# 2. Fast unit tests (hermetic database, skips network)
python -m pytest -q

# 3. End-to-end pipeline smoke test (full execution cycle)
python scripts/smoke_e2e.py

# 4. End-to-end browser verification (Playwright)
npx playwright test
```

---

## 📜 Citations & Reference Sources

* **Copernicus Sentinel-2**: European Space Agency (ESA) Copernicus Data Space Ecosystem.
* **WorldStrat Dataset**: Multi-temporal satellite imagery benchmark (Zenodo 15382551).
* **OpenSR LDSR-S2**: Latent Diffusion Super-Resolution for Sentinel-2 (ESA OpenSR, v1.1.1).
* See [`SOURCES.md`](SOURCES.md) for full cryptographic SHA-256 hashes and license ledger.

---

### 🛡️ Security & Operational Integrity
SUBPIXEL-SENTRY is built for mission-critical deployments where model opacity is an operational vulnerability. **Every pixel is accountable. Every claim is proven.**
