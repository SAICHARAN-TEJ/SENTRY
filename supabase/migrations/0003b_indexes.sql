-- 0003b_indexes.sql
-- SIH26142 "Sentry" - spatial (GiST) and lookup (btree) indexes.
-- Depends on: 0002_core_tables.sql.

-- Spatial indexes (GiST)
create index idx_aois_geom on aois using gist (geom);
create index idx_scenes_footprint on scenes using gist (footprint);
create index idx_reference_assets_footprint on reference_assets using gist (footprint);
create index idx_raster_artifacts_bounds on raster_artifacts using gist (bounds);

-- Lookup indexes (btree)
create index idx_scenes_sensing_time on scenes (sensing_time);
create index idx_scenes_dataset_source_id on scenes (dataset_source_id);
create index idx_jobs_status on jobs (status);
create index idx_jobs_project_id on jobs (project_id);
create index idx_job_steps_job_id on job_steps (job_id);
create index idx_job_inputs_job_id on job_inputs (job_id);
create index idx_validation_metrics_validation_run_id on validation_metrics (validation_run_id);
create index idx_validation_runs_job_id on validation_runs (job_id);
create index idx_provenance_events_project_id_created_at on provenance_events (project_id, created_at);

-- Composite job-queue lookup
create index idx_jobs_project_status_priority_created_at on jobs (project_id, status, priority, created_at);
