-- 0009_output_schema.sql
-- SIH26142 "Sentry" - PRD §11 output-schema artifacts.
--
-- Adds the three PRD Table 9 outputs that were missing:
--   preview_rgb.png          true-color visualization of the SR product
--   preview_false_color.png  NIR/R/G visualization
--   run_metadata.json        traceability: input product IDs, sensing times,
--                            model version, git commit, config hash, sampling
--                            steps, runtime, device
-- Previews are registered as artifacts so the Export screen can sign and
-- download them like every other output; run_metadata.json carries the
-- traceability fields the PRD requires on every deliverable.

alter table public.raster_artifacts
    drop constraint raster_artifacts_artifact_type_check;

alter table public.raster_artifacts
    add constraint raster_artifacts_artifact_type_check
    check (artifact_type in ('sr_output', 'uncertainty', 'preprocessed_tiles',
                             'benchmark_output', 'reference_grid', 'report_file',
                             'manifest', 'observation',
                             'preview_rgb', 'preview_false_color',
                             'run_metadata'));
