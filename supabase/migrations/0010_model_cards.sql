-- 0010_model_cards.sql
-- SIH26142 "Sentry" - honest model capability records.
--
-- Problem: the seed rows described `custom_mf_sr` as the "team multi-frame
-- model", which reads as a learned temporal super-resolution network. It is not
-- one: it is a deterministic heuristic (sharpest-frame selection, bicubic
-- upsampling, temporal high-frequency modulation). `opensr_ldsrs2` likewise had
-- no pinned checkpoint hash, so a validation report could not prove which
-- weights produced the output.
--
-- This migration replaces the four rows with capability cards that state, in
-- the database, exactly what each model is and what it needs:
--   framework      the pinned upstream release
--   checksum       the SHA-256 of the exact checkpoint file
--   model_card     status / learned / visual_only / bands / resolutions /
--                  license / uncertainty_kind / provenance
--
-- The worker re-verifies the checkpoint bytes against this hash on every load
-- (worker/opensr.py), so the row cannot silently drift from the artifact.
-- Records are never rewritten in place by later runs: a report stamps
-- summary_json.model.sha256, so changing a row invalidates the claim.

-- 1. Pin the real checkpoint hash + framework on the published baseline.
update public.model_versions
   set framework = 'opensr-model v1.1.1 (PyTorch Lightning latent diffusion)',
       checksum  = 'e2621e3912eb7c14867c3d20c9029607ba941be8e166dc09621860fcac27dc3a',
       checkpoint_object_key = 'opensr/opensr-ldsrs2_v1_0_0.ckpt',
       model_card = '{
         "display_name": "ESA OpenSR LDSR-S2 (latent diffusion)",
         "role": "primary published scientific baseline",
         "status": "published",
         "learned": true,
         "visual_only": false,
         "deterministic": false,
         "bands": ["B02", "B03", "B04", "B08"],
         "model_band_order": ["B04", "B03", "B02", "B08"],
         "input_resolution_m": 10.0,
         "output_resolution_m": 2.5,
         "scale": 4,
         "native_lr_window_px": 128,
         "uncertainty_kind": "stochastic_sampling_std",
         "license": "MIT (code); checkpoint released for research use by ESA OpenSR",
         "dataset": "OpenSR LDSR-S2 checkpoint, simon-donike/RS-SR-LTDF (Hugging Face)",
         "repo": "https://github.com/ESAOpenSR/opensr-model",
         "requires": "torch",
         "paper": "Donike et al., JSTARS 2025, doi:10.1109/JSTARS.2025.3542220"
       }'::jsonb
 where name = 'opensr_ldsrs2';

-- 2. Correct the experimental path's description so the UI cannot overclaim.
update public.model_versions
   set model_card = '{
         "display_name": "SENTRY experimental multi-frame fusion (heuristic)",
         "role": "experimental deterministic multi-frame fusion heuristic: sharpest-frame selection, bicubic upsampling and temporal high-frequency modulation. NOT a learned temporal super-resolution network.",
         "status": "experimental",
         "learned": false,
         "visual_only": false,
         "deterministic": true,
         "bands": ["B02", "B03", "B04", "B08"],
         "input_resolution_m": 10.0,
         "output_resolution_m": 2.5,
         "scale": 4,
         "uncertainty_kind": "auxiliary_gradient_indicator",
         "license": "n/a (in-repo algorithm)",
         "requires_training": true,
         "note": "Kept as a research reference path. Temporal frames pass through quality-aware selection with a scene-change safeguard before fusion."
       }'::jsonb
 where name = 'custom_mf_sr';

-- 3. Label the interpolation lower bound and its non-probabilistic indicator.
update public.model_versions
   set model_card = '{
         "display_name": "Bicubic 4x (no-learning lower bound)",
         "role": "deterministic interpolation baseline",
         "status": "baseline",
         "learned": false,
         "visual_only": false,
         "deterministic": true,
         "bands": ["B02", "B03", "B04", "B08"],
         "input_resolution_m": 10.0,
         "output_resolution_m": 2.5,
         "scale": 4,
         "uncertainty_kind": "auxiliary_gradient_indicator",
         "license": "n/a (scikit-image resampling)"
       }'::jsonb
 where name = 'bicubic_4x';

-- 4. Keep Real-ESRGAN explicitly out of every scientific comparison.
update public.model_versions
   set model_card = '{
         "display_name": "Real-ESRGAN (RGB visual comparator)",
         "role": "visual-only auxiliary",
         "status": "visual_only",
         "learned": true,
         "visual_only": true,
         "deterministic": false,
         "bands": ["B04", "B03", "B02"],
         "uncertainty_kind": null,
         "license": "BSD-3-Clause (Real-ESRGAN)",
         "note": "Not a multispectral scientific baseline: 3-channel RGB only, never used as a comparator in benchmark tables."
       }'::jsonb
 where name = 'realesrgan_optional';

-- 5. Provenance for the model rows themselves.
alter table public.model_versions
    add column if not exists status text not null default 'experimental',
    add column if not exists verified_at timestamptz;

alter table public.model_versions
    drop constraint if exists model_versions_status_check;
alter table public.model_versions
    add constraint model_versions_status_check
    check (status in ('baseline', 'published', 'experimental', 'visual_only'));

update public.model_versions
   set status = coalesce(nullif(model_card ->> 'status', ''), 'experimental'),
       verified_at = case
           when checksum = 'e2621e3912eb7c14867c3d20c9029607ba941be8e166dc09621860fcac27dc3a'
           then now() else verified_at end;

-- A model that claims READY must actually declare how it is run.
alter table public.model_versions
    drop constraint if exists model_versions_experimental_has_no_claim;
alter table public.model_versions
    add constraint model_versions_experimental_has_no_claim
    check (
        status <> 'published'
        or (checksum is not null and checksum <> '')
    );
