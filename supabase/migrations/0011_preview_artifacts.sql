-- 0011_preview_artifacts.sql
-- SIH26142 "Sentry" - comparison-view preview artifacts.
--
-- Why: the split comparison view has to show OBSERVED pixels on one side and
-- model-inferred pixels on the other. Until now only the reconstruction had a
-- PNG preview, so the observed side of the slider had nothing real to render.
-- Rather than fill it with a stand-in image, the pipeline now writes previews
-- for the observation, the uncertainty raster and the scale-back residual.
--
-- All three are visualizations. They carry a caption strip, are never used as
-- inputs to any metric, and the uncertainty/residual previews reuse the exact
-- documented operators the validation engine uses, so what the picture shows and
-- what the report measures are the same quantity.

-- Deployments that ran 0009 may hold rows under the old 'reference_grid'
-- name; fold them into 'reference' before the tighter CHECK below, so the
-- ALTER never fails on legacy data this codebase no longer writes.
update public.raster_artifacts
    set artifact_type = 'reference'
    where artifact_type = 'reference_grid';

alter table public.raster_artifacts
    drop constraint if exists raster_artifacts_artifact_type_check;

alter table public.raster_artifacts
    add constraint raster_artifacts_artifact_type_check
    check (artifact_type in (
        -- inputs / intermediates
        'observation', 'preprocessed_tiles', 'manifest', 'reference',
        -- scientific products
        'sr_output', 'uncertainty',
        -- previews (visualization only; never data)
        'preview_rgb', 'preview_false_color', 'preview_observation',
        'preview_uncertainty', 'preview_residual',
        -- reporting
        'report_file', 'run_metadata', 'benchmark_output'
    ));

comment on column public.raster_artifacts.artifact_type is
    'Scientific products (sr_output, uncertainty) are data. preview_* are PNG '
    'visualizations and must never be consumed as measurements.';
