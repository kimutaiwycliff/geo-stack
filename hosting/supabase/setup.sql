-- =============================================================================
-- Supabase new project setup
-- =============================================================================
-- Run this in Supabase SQL Editor after creating a new project.
-- Run each block separately if you hit errors (SQL Editor runs one block at a time).
--
-- Supabase quirks vs plain PostGIS Docker:
--   1. PostGIS lives in the 'extensions' schema (not 'public')
--   2. search_path must be set on roles so Martin can discover geometry columns
--   3. postgis_raster and postgis_tiger_geocoder are not on free tier — skip them
--   4. The database name is always 'postgres', not 'geodata'
--   5. Direct connections use port 5432; connection pooler uses 6543
--      Martin and FastAPI must use the POOLER URL (port 6543) on Render free tier
--
-- After this script: copy-paste db/init/02_tables.sql, 03_indexes.sql,
-- 04_functions.sql, and 05_sample_data.sql into the SQL Editor.
-- Or use the Supabase CLI: supabase db push --db-url "$SUPABASE_DATABASE_URL"
-- =============================================================================

-- Step 1: Enable extensions
-- Supabase pre-installs PostGIS in the 'extensions' schema.
-- These CREATE EXTENSION calls are idempotent.
CREATE EXTENSION IF NOT EXISTS postgis WITH SCHEMA extensions;
CREATE EXTENSION IF NOT EXISTS postgis_topology WITH SCHEMA extensions;
CREATE EXTENSION IF NOT EXISTS fuzzystrmatch WITH SCHEMA extensions;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA extensions;
CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA extensions;
CREATE EXTENSION IF NOT EXISTS btree_gist WITH SCHEMA extensions;
-- Note: postgis_raster and address_standardizer are not available on Supabase free tier.

-- Step 2: Fix search_path so PostGIS functions are accessible without schema prefix
-- Martin queries 'geometry_columns' and calls ST_* functions — it needs extensions
-- in its search path or it will get "function st_asmvt does not exist" errors.
-- These ALTER ROLE statements persist across connections.
ALTER ROLE authenticator SET search_path TO public, extensions;
ALTER ROLE anon SET search_path TO public, extensions;
ALTER ROLE authenticated SET search_path TO public, extensions;
ALTER ROLE service_role SET search_path TO public, extensions;
ALTER ROLE postgres SET search_path TO public, extensions, geo, staging, audit;

-- Step 3: Create project schemas
CREATE SCHEMA IF NOT EXISTS geo;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS audit;

-- Step 4: Grant Martin read access to the geo schema
-- Martin connects as the postgres user. Grant read on current and future tables.
GRANT USAGE ON SCHEMA geo TO postgres;
GRANT SELECT ON ALL TABLES IN SCHEMA geo TO postgres;
ALTER DEFAULT PRIVILEGES IN SCHEMA geo GRANT SELECT ON TABLES TO postgres;

-- Also grant to service_role so the Supabase client and edge functions can read
GRANT USAGE ON SCHEMA geo TO service_role;
GRANT SELECT ON ALL TABLES IN SCHEMA geo TO service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA geo GRANT SELECT ON TABLES TO service_role;

-- Step 5: Verify PostGIS is accessible
-- This will error if search_path is wrong — fix the ALTER ROLE statements and
-- start a new connection (Supabase SQL Editor starts fresh each run).
SELECT extensions.PostGIS_Version() AS postgis_version;

-- Expected output: something like "3.4.0 USE_GEOS=1 USE_PROJ=1 USE_STATS=1"
-- If you get "function postgis_version() does not exist", the search_path fix
-- hasn't taken effect yet — try disconnecting and reconnecting.

-- =============================================================================
-- Next: run db/init/02_tables.sql in SQL Editor to create your spatial tables.
-- The tables reference geo.* so the schema must exist first (done above).
-- =============================================================================
