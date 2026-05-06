-- Allow 'exporting_parquet' as a valid status in ingest_jobs.
-- Applied 2026-05-05 via Supabase MCP.
ALTER TABLE staging.ingest_jobs DROP CONSTRAINT ingest_jobs_status_check;
ALTER TABLE staging.ingest_jobs ADD CONSTRAINT ingest_jobs_status_check
  CHECK (status = ANY (ARRAY['pending'::text, 'queued'::text, 'restoring'::text, 'processing'::text, 'exporting_parquet'::text, 'done'::text, 'error'::text]));
