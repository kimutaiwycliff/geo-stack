-- Add GeoParquet export error column to ingest_jobs.
-- Applied 2026-05-05 via Supabase MCP.
ALTER TABLE staging.ingest_jobs ADD COLUMN IF NOT EXISTS parquet_error TEXT;
