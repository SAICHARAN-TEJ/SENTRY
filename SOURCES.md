# Source Lock — SIH26142 (PRD Phase 0)

Recorded for the "all source artifacts checksummed and cited" gate. Values below were
fetched and verified against the authoritative endpoints on 2026-09-12. When the
archives are downloaded, run `python scripts/fetch_sources.py --verify-only` after each
download: it enforces these exact hashes and fails loudly on mismatch.

## 1. SIH Problem Statement PS 26142

- Authority for scope/deliverables (NTRO / Software / Space Technology; deadline 2026-09-30).
- **Status: NOT YET ARCHIVED (human step).** Save the page as PDF/HTML, record SHA-256 here.
- URL: https://sih.gov.in/sih2026PS

## 2. WorldStrat v1.1 (Zenodo record 15382551, DOI 10.5281/zenodo.15382551)

- Title: "The WorldStrat Dataset: Open High-Resolution Satellite Imagery With Paired
  Multi-Temporal Low-Resolution" — Cornebise, Oršolić, Kalaitzis. NeurIPS 2022 (Datasets).
- Version v1.1, published 2025-06. ESA "Query Planet" grant 4000124792/18/I-BG CCN3.
- Licenses (verified from record metadata):
  - High-resolution Airbus SPOT 6/7 imagery: **CC BY-NC 4.0** (non-commercial only)
  - Labels, Sentinel-2 imagery, trained weights: **CC BY 4.0**
  - Source code (github.com/worldstrat/worldstrat): **BSD 3-Clause**

| File | Size (bytes) | MD5 | Tier |
|---|---|---|---|
| `LICENSE.txt` | 39,298 | `d97b8d86da83f7e51f2d3205509e4a7b` | required |
| `metadata.csv` | 18,434,289 | `1a66ac42b9a688be18debd0d95633fa1` | required |
| `stratified_train_val_test_split.csv` | 306,901 | `874612b59bbf7987f7de7edd48a30c70` | required |
| `hr_dataset.zip` | 40,829,062,202 (~38.0 GiB) | `5ae09bb3557ce131242a133d9758d9e7` | required |
| `lr_dataset_l2a.zip` | 25,493,197,186 (~23.7 GiB) | `7aa1878a37d22a6c7c4b84b022a14ad7` | required |
| `lr_dataset_l1c.zip` | 26,372,239,589 (~24.6 GiB) | `e90ecfa4bf838ace0b51dea1031b5ed1` | optional (robustness) |
| `hr_dataset_raw.zip` | 11,387,407,107 (~10.6 GiB) | `515f38e333bf06e79ac523fb2eab588d` | optional (raw verification) |

Download (initial set ≈ 62 GiB):
```bash
python scripts/fetch_sources.py            # downloads + verifies everything marked "required"
python scripts/fetch_sources.py --with-optional
python scripts/fetch_sources.py --verify-only   # re-check hashes without downloading
```
License/attribution note: repository outputs supervised on WorldStrat HR imagery must not
claim unrestricted commercial deployment (CC BY-NC 4.0). Retain LICENSE.txt alongside data.

## 3. ESA OpenSR — LDSR-S2 model (opensr-model)

- Repository: https://github.com/ESAOpenSR/opensr-model
- **Pinned release: v1.1.1 (published 2026-05-08)** — the version to record in provenance
  (`model_versions.framework` / model card) and in `run_metadata.json`.
- Tarball: https://api.github.com/repos/ESAOpenSR/opensr-model/tarball/v1.1.1
- Checkpoint weights: fetched by the package's own downloader (Hugging Face-hosted).
  **Status: NOT YET DOWNLOADED (human/GPU step).** After download, record the checkpoint
  SHA-256 in the `model_versions.checksum` column — `backend.schemas.ModelOut` already
  exposes it and validation reports stamp it into every `summary_json.model.sha256`.
- Companion repo (PRD Table 3 reference for tiling/stitching):
  https://github.com/ESAOpenSR/opensr-utils — record its version pin after cloning.

## 4. Copernicus Data Space Ecosystem — production S2 input source

- Catalog (OData, verified live & anonymously queryable):
  https://catalogue.dataspace.copernicus.eu/odata/v1/Products
  Verified filter shape: `Collection/Name eq 'SENTINEL-2' and contains(Name,'MSIL2A')
  and OData.CSC.Intersects(area=geography'SRID=4326;POLYGON((...))')` + `ContentDate/Start`.
  Products return MD5 + BLAKE3 checksums, footprints, Online/offline flags.
- Product download (S3) requires a **free registered account** — token human step, not
  yet provisioned. `backend/copernicus.py` implements search/ingest unauthenticated and
  download optionally authenticated via `COPERNICUS_USERNAME` / `COPERNICUS_PASSWORD`.
- Connector in repo: `backend/copernicus.py` + `/v1/copernicus/*` endpoints.

## 5. Reference papers (jury package; optional PDFs)

| Paper | Source |
|---|---|
| WorldStrat (NeurIPS 2022) | arXiv:2207.06418 |
| Trustworthy SR of Multispectral Sentinel-2 With Latent Diffusion (JSTARS 2025) | doi:10.1109/JSTARS.2025.3542220 |
| PIUnet (permutation-invariant multi-frame SR + uncertainty) | github.com/diegovalsesia/piunet |
| HighRes-Net (recursive multi-frame fusion) | arXiv:2002.06460 |

## 6. Fetch ledger (update as items complete)

| Item | Status | Owner |
|---|---|---|
| WorldStrat identifiers + MD5 manifest | ✅ verified 2026-09-12 | recorded here |
| OpenSR opensr-model version pin (v1.1.1) | ✅ verified 2026-09-12 | recorded here |
| Copernicus OData endpoint + filter shape | ✅ verified live 2026-09-12 | connector implemented |
| SIH PS 26142 archive (PDF + SHA-256) | ⬜ pending | human |
| WorldStrat archive downloads (~62 GiB initial) | ⬜ pending | human (`fetch_sources.py`) |
| OpenSR checkpoint weights + SHA-256 | ⬜ pending | human/GPU |
| Copernicus account + token | ⬜ pending | human |
| One real S2 L2A product staged end-to-end | ⬜ pending | after connector + account |
