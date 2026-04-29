-- 00_extensions.sql
-- Install all required PostgreSQL extensions.
-- Runs once on first container start (Docker init entrypoint).
-- Order matters: postgis must be installed before postgis_topology.

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;
CREATE EXTENSION IF NOT EXISTS postgis_raster;
CREATE EXTENSION IF NOT EXISTS fuzzystrmatch;          -- needed for postgis_tiger_geocoder
CREATE EXTENSION IF NOT EXISTS address_standardizer;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";            -- UUID generation
CREATE EXTENSION IF NOT EXISTS pg_trgm;                -- trigram text search
CREATE EXTENSION IF NOT EXISTS btree_gist;             -- GiST index on btree types (useful for exclusion constraints)

-- Verify spatial extensions loaded correctly
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'postgis') THEN
        RAISE EXCEPTION 'PostGIS extension failed to load';
    END IF;
    RAISE NOTICE 'PostGIS % loaded successfully', PostGIS_Version();
END
$$;
