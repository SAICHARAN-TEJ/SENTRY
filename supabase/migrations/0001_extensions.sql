-- 0001_extensions.sql
-- SIH26142 "Sentry" - required PostgreSQL extensions.
-- postgis:  geometry columns (aois.geom, scenes.footprint, raster_artifacts.bounds, ...).
-- pgcrypto: gen_random_uuid() for UUID primary key defaults.
-- NOTE: uuid-ossp is intentionally NOT installed; all UUIDs come from gen_random_uuid().

create extension if not exists postgis;
create extension if not exists pgcrypto;
