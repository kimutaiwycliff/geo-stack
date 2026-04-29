-- 01_schemas.sql
-- Create project schemas. Three-schema architecture keeps data concerns separate:
--   geo     → validated, production spatial data (Martin publishes from here)
--   staging → raw imports before geometry validation and cleaning
--   audit   → change log for all geo table modifications

CREATE SCHEMA IF NOT EXISTS geo;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS audit;

-- Grant Martin's DB user read access to the geo schema.
-- Martin connects as the same POSTGRES_USER, so this is a self-grant (no-op unless
-- you add a dedicated read-only martin user later).
GRANT USAGE ON SCHEMA geo TO CURRENT_USER;
GRANT SELECT ON ALL TABLES IN SCHEMA geo TO CURRENT_USER;
ALTER DEFAULT PRIVILEGES IN SCHEMA geo GRANT SELECT ON TABLES TO CURRENT_USER;

-- Set default search path so bare table names resolve to geo first.
ALTER DATABASE geodata SET search_path TO geo, public;
