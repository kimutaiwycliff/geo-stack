<script lang="ts">
  import { onMount } from 'svelte';

  // ── Types ─────────────────────────────────────────────────────────────────
  interface DetectedLayer {
    name: string;
    geometry_type: string;
    feature_count: number;
    zip_member: string | null;
  }

  interface UploadResult {
    job_id: string;
    file_name: string;
    file_size_bytes: number;
    layers: DetectedLayer[];
  }

  interface JobProgress {
    status: string;
    pct: number;
    rows_inserted: number;
    error: string | null;
  }

  interface JobRecord {
    job_id: string;
    file_name: string;
    file_size_mb: number | null;
    target_table: string | null;
    source_layer: string | null;
    status: string;
    pct: number;
    rows_inserted: number;
    error: string | null;
    created_at: string | null;
  }

  // ── State ─────────────────────────────────────────────────────────────────
  type Phase =
    | 'idle'
    | 'uploading'
    | 'ready'
    | 'processing'
    | 'done'
    | 'error';

  let phase: Phase = 'idle';
  let dragging = false;
  let apiUrl = 'http://localhost:8000';

  // Upload phase
  let uploadPct = 0;
  let uploadResult: UploadResult | null = null;
  let uploadError = '';

  // Config phase
  let selectedLayer = '';
  let targetTable = '';
  let overwrite = false;

  // Processing phase
  let jobProgress: JobProgress | null = null;
  let jobEventSource: EventSource | null = null;

  // Job history
  let recentJobs: JobRecord[] = [];
  let loadingJobs = false;

  // ── Lifecycle ─────────────────────────────────────────────────────────────
  onMount(async () => {
    try {
      const r = await fetch('/api/config');
      if (r.ok) {
        const cfg = await r.json();
        apiUrl = cfg.apiUrl ?? apiUrl;
      }
    } catch { /* fallback */ }
    loadJobs();
  });

  // ── Drag & drop ───────────────────────────────────────────────────────────
  function onDragOver(e: DragEvent) { e.preventDefault(); dragging = true; }
  function onDragLeave() { dragging = false; }
  async function onDrop(e: DragEvent) {
    e.preventDefault(); dragging = false;
    const f = e.dataTransfer?.files[0];
    if (f) uploadFile(f);
  }
  async function onFileInput(e: Event) {
    const f = (e.target as HTMLInputElement).files?.[0];
    if (f) uploadFile(f);
  }

  // ── Upload ────────────────────────────────────────────────────────────────
  function uploadFile(file: File) {
    phase = 'uploading';
    uploadPct = 0;
    uploadError = '';
    uploadResult = null;

    // Auto-suggest table name from file name
    if (!targetTable) {
      targetTable = 'staging.' + file.name
        .replace(/\.[^.]+$/, '')
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, '_')
        .slice(0, 40);
    }

    const form = new FormData();
    form.append('file', file);

    const xhr = new XMLHttpRequest();
    xhr.upload.addEventListener('progress', (e) => {
      if (e.lengthComputable) uploadPct = Math.round((e.loaded / e.total) * 100);
    });

    xhr.addEventListener('load', () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          uploadResult = JSON.parse(xhr.responseText) as UploadResult;
          // Auto-select the only layer for single-layer files
          if (uploadResult.layers.length === 1) {
            selectedLayer = uploadResult.layers[0].name;
          }
          phase = 'ready';
        } catch {
          uploadError = 'Unexpected server response.';
          phase = 'error';
        }
      } else {
        try {
          const body = JSON.parse(xhr.responseText);
          uploadError = body.detail ?? `Server error ${xhr.status}`;
        } catch {
          uploadError = `Server error ${xhr.status}`;
        }
        phase = 'error';
      }
    });

    xhr.addEventListener('error', () => {
      uploadError = 'Network error — could not reach the API.';
      phase = 'error';
    });

    xhr.open('POST', `${apiUrl}/ingest/upload`);
    xhr.send(form);
  }

  // ── Process ───────────────────────────────────────────────────────────────
  async function startProcessing() {
    if (!uploadResult || !targetTable || !selectedLayer) return;
    phase = 'processing';
    jobProgress = null;

    try {
      const res = await fetch(`${apiUrl}/ingest/process`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          job_id: uploadResult.job_id,
          target_table: targetTable,
          source_layer: selectedLayer,
          overwrite,
        }),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
        phase = 'error';
        uploadError = body.detail ?? 'Failed to start processing';
        return;
      }

      // Open SSE stream for progress
      jobEventSource = new EventSource(`${apiUrl}/ingest/job/${uploadResult.job_id}`);
      jobEventSource.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data) as JobProgress;
          jobProgress = data;
          if (data.status === 'done') {
            phase = 'done';
            jobEventSource?.close();
            loadJobs();
          } else if (data.status === 'error') {
            phase = 'error';
            uploadError = data.error ?? 'Processing failed';
            jobEventSource?.close();
            loadJobs();
          }
        } catch { /* ignore */ }
      };
      jobEventSource.onerror = () => {
        if (phase === 'processing') {
          uploadError = 'Lost connection to progress stream.';
          phase = 'error';
        }
        jobEventSource?.close();
      };
    } catch (err) {
      uploadError = err instanceof Error ? err.message : String(err);
      phase = 'error';
    }
  }

  // ── Helpers ───────────────────────────────────────────────────────────────
  function reset() {
    phase = 'idle';
    uploadPct = 0;
    uploadResult = null;
    uploadError = '';
    selectedLayer = '';
    targetTable = '';
    overwrite = false;
    jobProgress = null;
    jobEventSource?.close();
    jobEventSource = null;
  }

  async function loadJobs() {
    loadingJobs = true;
    try {
      const r = await fetch(`${apiUrl}/ingest/jobs`);
      if (r.ok) recentJobs = await r.json();
    } catch { /* ignore */ }
    finally { loadingJobs = false; }
  }

  async function deleteJob(job_id: string) {
    await fetch(`${apiUrl}/ingest/job/${job_id}`, { method: 'DELETE' });
    loadJobs();
  }

  function fmtSize(bytes: number | null) {
    if (!bytes) return '—';
    return bytes > 1_048_576
      ? `${(bytes / 1_048_576).toFixed(1)} MB`
      : `${(bytes / 1024).toFixed(0)} KB`;
  }

  function statusColour(s: string) {
    return s === 'done' ? 'green' : s === 'error' ? 'red' : s === 'processing' ? 'blue' : 'grey';
  }
</script>

<svelte:head>
  <title>Upload Data — geo-stack</title>
</svelte:head>

<div class="page">

  <!-- Header -->
  <header>
    <a href="/" class="back">← Map</a>
    <div>
      <h1>Data Upload</h1>
      <p class="subtitle">Any GDAL format · processed server-side · streamed to Supabase</p>
    </div>
  </header>

  <div class="layout">

    <!-- ── Left: upload flow ─────────────────────────────────────────────── -->
    <main class="main-col">

      <!-- IDLE: drop zone -->
      {#if phase === 'idle'}
        <div
          class="drop-zone"
          class:dragging
          role="button"
          tabindex="0"
          on:dragover={onDragOver}
          on:dragleave={onDragLeave}
          on:drop={onDrop}
          on:keydown={(e) => e.key === 'Enter' && document.getElementById('fi')?.click()}
        >
          <svg class="drop-icon" viewBox="0 0 56 56" fill="none">
            <circle cx="28" cy="28" r="26" stroke="currentColor" stroke-width="1.5" stroke-dasharray="5 4"/>
            <path d="M28 38V22M21 29l7-7 7 7" stroke="currentColor" stroke-width="2"
                  stroke-linecap="round" stroke-linejoin="round"/>
            <path d="M18 40h20" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
          </svg>
          <p class="drop-label">Drag &amp; drop a file here</p>
          <p class="drop-hint">
            GeoJSON · KML · Shapefile ZIP · GeoPackage · GeoParquet · CSV · any GDAL format
          </p>
          <label class="btn primary" for="fi">Browse file</label>
          <input id="fi" type="file" on:change={onFileInput} style="display:none"
                 accept=".geojson,.json,.kml,.zip,.gpkg,.parquet,.csv,.gml,.shp"/>
        </div>

        <div class="info-box">
          <strong>No size limit.</strong> Files are streamed to the server and processed with
          ogr2ogr — no browser memory constraints. Large shapefiles, GeoPackages, and
          GeoParquet files all work.
        </div>
      {/if}

      <!-- UPLOADING -->
      {#if phase === 'uploading'}
        <div class="card">
          <p class="card-title">Uploading file…</p>
          <div class="prog-track"><div class="prog-fill" style="width:{uploadPct}%"></div></div>
          <p class="prog-label">{uploadPct}%</p>
          <p class="hint-text">File is being streamed to the server. Hang tight.</p>
        </div>
      {/if}

      <!-- READY: layer selector + target table -->
      {#if phase === 'ready' && uploadResult}
        <div class="card">
          <div class="file-row">
            <span class="file-icon">📦</span>
            <div>
              <strong>{uploadResult.file_name}</strong>
              <span class="dim">{fmtSize(uploadResult.file_size_bytes)}</span>
            </div>
            <button class="btn ghost sm" on:click={reset}>Change</button>
          </div>

          <!-- Layer selector -->
          <div class="field">
            <label class="label">
              {uploadResult.layers.length === 1 ? 'Layer detected' : `Select a layer (${uploadResult.layers.length} found)`}
            </label>

            {#if uploadResult.layers.length === 1}
              <!-- Single layer: just show it -->
              <div class="single-layer">
                <span class="layer-chip">{uploadResult.layers[0].name}</span>
                <span class="dim">{uploadResult.layers[0].geometry_type}</span>
                {#if uploadResult.layers[0].feature_count > 0}
                  <span class="dim">· {uploadResult.layers[0].feature_count.toLocaleString()} features</span>
                {/if}
              </div>
            {:else}
              <!-- Multiple layers: radio list -->
              <div class="layer-list">
                {#each uploadResult.layers as layer}
                  <label class="layer-row" class:selected={selectedLayer === layer.name}>
                    <input type="radio" bind:group={selectedLayer} value={layer.name}/>
                    <div class="layer-meta">
                      <span class="layer-name">{layer.name}</span>
                      <span class="dim">{layer.geometry_type}</span>
                      {#if layer.feature_count > 0}
                        <span class="dim">· {layer.feature_count.toLocaleString()} features</span>
                      {/if}
                    </div>
                  </label>
                {/each}
              </div>
            {/if}
          </div>

          <!-- Target table -->
          <div class="field">
            <label class="label" for="tt">
              Target table
              <span class="dim">(schema.table_name — will be created if it doesn't exist)</span>
            </label>
            <input id="tt" class="text-input" bind:value={targetTable}
                   placeholder="staging.kenya_roads"/>
          </div>

          <!-- Overwrite toggle -->
          <label class="checkbox-row">
            <input type="checkbox" bind:checked={overwrite}/>
            <span>Overwrite if table already exists</span>
          </label>

          <button
            class="btn primary wide"
            disabled={!selectedLayer || !targetTable}
            on:click={startProcessing}
          >
            Import → {targetTable || '…'}
          </button>
        </div>
      {/if}

      <!-- PROCESSING -->
      {#if phase === 'processing'}
        <div class="card">
          <p class="card-title">Processing with ogr2ogr…</p>

          {#if jobProgress}
            {@const status = jobProgress.status}
            <div class="status-badge" data-colour={statusColour(status)}>{status}</div>
            <div class="prog-track">
              <div class="prog-fill" style="width:{jobProgress.pct}%"></div>
            </div>
            <p class="prog-label">{jobProgress.pct}%</p>
            {#if jobProgress.rows_inserted > 0}
              <p class="hint-text">{jobProgress.rows_inserted.toLocaleString()} rows inserted so far</p>
            {/if}
          {:else}
            <div class="spinner-row"><span class="spinner"></span> Queued — starting…</div>
          {/if}

          <p class="hint-text muted">
            ogr2ogr is running server-side. You can close this tab — the job continues.
            Come back and check <strong>Job history</strong> for the result.
          </p>
        </div>
      {/if}

      <!-- DONE -->
      {#if phase === 'done'}
        <div class="card success">
          <p class="card-title">✓ Import complete</p>
          {#if jobProgress}
            <p class="big-num">{jobProgress.rows_inserted.toLocaleString()}</p>
            <p class="hint-text">rows inserted into <code>{targetTable}</code></p>
          {/if}
          <div class="next-steps">
            <p class="label">Next steps</p>
            <ul>
              <li>Inspect: <code>SELECT * FROM {targetTable} LIMIT 10;</code></li>
              <li>Promote to <code>geo</code> schema so Martin serves tiles:
                <code>ALTER TABLE {targetTable} SET SCHEMA geo;</code>
              </li>
              <li>Then redeploy Martin on Render (Manual Deploy).</li>
            </ul>
          </div>
          <button class="btn primary" on:click={reset}>Upload another file</button>
        </div>
      {/if}

      <!-- ERROR -->
      {#if phase === 'error'}
        <div class="card error-card">
          <p class="card-title">Something went wrong</p>
          <p class="error-msg">{uploadError}</p>
          <button class="btn ghost" on:click={reset}>Try again</button>
        </div>
      {/if}

    </main>

    <!-- ── Right: job history ─────────────────────────────────────────────── -->
    <aside class="aside-col">
      <div class="aside-header">
        <h2>Job history</h2>
        <button class="btn ghost sm" on:click={loadJobs} disabled={loadingJobs}>
          {loadingJobs ? '…' : 'Refresh'}
        </button>
      </div>

      {#if recentJobs.length === 0 && !loadingJobs}
        <p class="empty">No jobs yet.</p>
      {/if}

      {#each recentJobs as job}
        <div class="job-card">
          <div class="job-top">
            <span class="job-file">{job.file_name}</span>
            <span class="status-badge" data-colour={statusColour(job.status)}>{job.status}</span>
          </div>
          {#if job.target_table}
            <p class="job-table">→ {job.target_table}{job.source_layer ? ` (${job.source_layer})` : ''}</p>
          {/if}
          <div class="job-meta">
            {#if job.file_size_mb}<span>{job.file_size_mb} MB</span>{/if}
            {#if job.rows_inserted > 0}<span>{job.rows_inserted.toLocaleString()} rows</span>{/if}
            {#if job.created_at}<span>{new Date(job.created_at).toLocaleString()}</span>{/if}
          </div>
          {#if job.status === 'processing'}
            <div class="prog-track sm"><div class="prog-fill" style="width:{job.pct}%"></div></div>
          {/if}
          {#if job.error}
            <p class="error-msg sm">{job.error}</p>
          {/if}
          <button class="btn ghost sm danger" on:click={() => deleteJob(job.job_id)}>
            Delete
          </button>
        </div>
      {/each}
    </aside>

  </div>
</div>

<style>
  /* ── Page shell ─────────────────────────────────────────────────────────── */
  .page {
    min-height: 100vh;
    background: #0f0f23;
    color: #e2e8f0;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    font-size: 14px;
  }

  header {
    display: flex;
    align-items: center;
    gap: 20px;
    padding: 14px 32px;
    background: rgba(255,255,255,0.03);
    border-bottom: 1px solid rgba(255,255,255,0.07);
  }
  .back { color: #60a5fa; text-decoration: none; font-size: 13px; white-space: nowrap; }
  .back:hover { text-decoration: underline; }
  h1 { font-size: 17px; font-weight: 600; color: #f1f5f9; margin: 0; }
  .subtitle { font-size: 12px; color: #64748b; margin: 2px 0 0; }

  /* ── Layout ─────────────────────────────────────────────────────────────── */
  .layout {
    display: grid;
    grid-template-columns: 1fr 340px;
    gap: 28px;
    max-width: 1080px;
    margin: 28px auto;
    padding: 0 28px;
  }
  @media (max-width: 760px) {
    .layout { grid-template-columns: 1fr; padding: 0 16px; }
    header { padding: 12px 16px; }
  }

  /* ── Drop zone ──────────────────────────────────────────────────────────── */
  .drop-zone {
    border: 2px dashed rgba(96,165,250,0.35);
    border-radius: 14px;
    padding: 52px 32px;
    text-align: center;
    cursor: pointer;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 10px;
    background: rgba(255,255,255,0.015);
    transition: border-color 0.2s, background 0.2s;
  }
  .drop-zone:hover, .drop-zone.dragging {
    border-color: #60a5fa;
    background: rgba(96,165,250,0.05);
  }
  .drop-icon { width: 56px; height: 56px; color: #3b82f6; margin-bottom: 4px; }
  .drop-label { font-size: 16px; font-weight: 500; color: #cbd5e1; }
  .drop-hint { font-size: 12px; color: #475569; margin-bottom: 6px; line-height: 1.6; }

  .info-box {
    margin-top: 14px;
    padding: 12px 16px;
    background: rgba(96,165,250,0.07);
    border: 1px solid rgba(96,165,250,0.15);
    border-radius: 8px;
    font-size: 13px;
    color: #93c5fd;
    line-height: 1.6;
  }

  /* ── Card ───────────────────────────────────────────────────────────────── */
  .card {
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 12px;
    padding: 20px 22px;
    display: flex;
    flex-direction: column;
    gap: 14px;
  }
  .card.success { border-color: rgba(34,197,94,0.25); background: rgba(34,197,94,0.04); }
  .card.error-card { border-color: rgba(239,68,68,0.25); background: rgba(239,68,68,0.04); }
  .card-title { font-size: 15px; font-weight: 600; color: #f1f5f9; margin: 0; }

  .file-row {
    display: flex;
    align-items: center;
    gap: 10px;
    padding-bottom: 10px;
    border-bottom: 1px solid rgba(255,255,255,0.06);
  }
  .file-icon { font-size: 20px; }

  /* ── Progress bar ───────────────────────────────────────────────────────── */
  .prog-track {
    height: 6px;
    background: rgba(255,255,255,0.08);
    border-radius: 3px;
    overflow: hidden;
  }
  .prog-track.sm { height: 4px; }
  .prog-fill {
    height: 100%;
    background: linear-gradient(90deg, #2563eb, #60a5fa);
    border-radius: 3px;
    transition: width 0.4s ease;
  }
  .prog-label { font-size: 13px; color: #94a3b8; text-align: right; margin: -6px 0 0; }

  /* ── Spinner ─────────────────────────────────────────────────────────────── */
  .spinner {
    display: inline-block;
    width: 14px; height: 14px;
    border: 2px solid rgba(255,255,255,0.15);
    border-top-color: #60a5fa;
    border-radius: 50%;
    animation: spin 0.7s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
  .spinner-row { display: flex; align-items: center; gap: 10px; color: #94a3b8; }

  /* ── Layer selector ─────────────────────────────────────────────────────── */
  .field { display: flex; flex-direction: column; gap: 6px; }
  .label { font-size: 12px; font-weight: 500; color: #94a3b8; }

  .single-layer {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px 12px;
    background: rgba(255,255,255,0.04);
    border-radius: 8px;
  }
  .layer-chip {
    background: rgba(37,99,235,0.2);
    border: 1px solid rgba(37,99,235,0.35);
    color: #93c5fd;
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 12px;
    font-family: 'SF Mono', monospace;
  }

  .layer-list {
    display: flex;
    flex-direction: column;
    gap: 4px;
    max-height: 260px;
    overflow-y: auto;
  }
  .layer-row {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 9px 12px;
    border-radius: 8px;
    cursor: pointer;
    border: 1px solid rgba(255,255,255,0.05);
    background: rgba(255,255,255,0.02);
    transition: background 0.15s, border-color 0.15s;
  }
  .layer-row:hover { background: rgba(255,255,255,0.05); }
  .layer-row.selected { background: rgba(37,99,235,0.12); border-color: rgba(37,99,235,0.35); }
  .layer-row input { accent-color: #3b82f6; }
  .layer-meta { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
  .layer-name { font-family: 'SF Mono', monospace; font-size: 13px; color: #e2e8f0; }

  /* ── Form fields ─────────────────────────────────────────────────────────── */
  .text-input {
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 7px;
    padding: 9px 12px;
    color: #f1f5f9;
    font-size: 14px;
    outline: none;
    width: 100%;
    box-sizing: border-box;
    transition: border-color 0.15s;
    font-family: 'SF Mono', monospace;
  }
  .text-input:focus { border-color: #3b82f6; }

  .checkbox-row {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 13px;
    color: #94a3b8;
    cursor: pointer;
  }
  .checkbox-row input { accent-color: #3b82f6; }

  /* ── Success state ───────────────────────────────────────────────────────── */
  .big-num { font-size: 36px; font-weight: 700; color: #86efac; margin: 0; line-height: 1; }
  .next-steps {
    background: rgba(255,255,255,0.03);
    border-radius: 8px;
    padding: 12px 16px;
  }
  .next-steps ul { margin: 8px 0 0 16px; padding: 0; display: flex; flex-direction: column; gap: 6px; }
  .next-steps li { color: #94a3b8; font-size: 12px; line-height: 1.6; }

  /* ── Error ───────────────────────────────────────────────────────────────── */
  .error-msg { color: #fca5a5; font-size: 13px; margin: 0; }
  .error-msg.sm { font-size: 12px; }

  /* ── Buttons ─────────────────────────────────────────────────────────────── */
  .btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    padding: 8px 16px;
    border-radius: 7px;
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
    border: none;
    transition: background 0.15s, opacity 0.15s;
  }
  .btn:disabled { opacity: 0.4; cursor: not-allowed; }
  .btn.primary { background: #2563eb; color: #fff; }
  .btn.primary:hover:not(:disabled) { background: #1d4ed8; }
  .btn.ghost {
    background: rgba(255,255,255,0.06);
    color: #94a3b8;
    border: 1px solid rgba(255,255,255,0.08);
  }
  .btn.ghost:hover:not(:disabled) { background: rgba(255,255,255,0.1); }
  .btn.sm { padding: 4px 10px; font-size: 12px; }
  .btn.wide { width: 100%; padding: 12px; font-size: 14px; }
  .btn.danger { color: #f87171; }

  /* ── Status badge ───────────────────────────────────────────────────────── */
  .status-badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }
  .status-badge[data-colour="green"] { background: rgba(34,197,94,0.15); color: #86efac; }
  .status-badge[data-colour="red"]   { background: rgba(239,68,68,0.15);  color: #fca5a5; }
  .status-badge[data-colour="blue"]  { background: rgba(59,130,246,0.15); color: #93c5fd; }
  .status-badge[data-colour="grey"]  { background: rgba(255,255,255,0.07); color: #94a3b8; }

  /* ── Aside (job history) ─────────────────────────────────────────────────── */
  .aside-col {
    background: rgba(255,255,255,0.02);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 12px;
    padding: 18px;
    align-self: start;
  }
  .aside-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 14px;
  }
  h2 { font-size: 13px; font-weight: 600; color: #f1f5f9; text-transform: uppercase; letter-spacing: 0.05em; margin: 0; }
  .empty { color: #334155; font-size: 13px; text-align: center; padding: 20px 0; }

  .job-card {
    display: flex;
    flex-direction: column;
    gap: 5px;
    padding: 11px 12px;
    border-radius: 8px;
    background: rgba(255,255,255,0.025);
    border: 1px solid rgba(255,255,255,0.05);
    margin-bottom: 7px;
  }
  .job-top { display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; }
  .job-file { font-size: 12px; color: #cbd5e1; font-weight: 500; word-break: break-all; }
  .job-table { font-size: 11px; color: #60a5fa; font-family: 'SF Mono', monospace; margin: 0; }
  .job-meta { display: flex; flex-wrap: wrap; gap: 8px; }
  .job-meta span { font-size: 11px; color: #475569; }

  /* ── Shared utilities ───────────────────────────────────────────────────── */
  .dim   { font-size: 12px; color: #64748b; }
  .muted { color: #475569; font-size: 12px; }
  .hint-text { font-size: 12px; color: #64748b; margin: 0; line-height: 1.6; }

  code {
    background: rgba(255,255,255,0.07);
    padding: 1px 5px;
    border-radius: 4px;
    font-family: 'SF Mono', 'Fira Code', monospace;
    font-size: 12px;
    color: #93c5fd;
    word-break: break-all;
  }
</style>
