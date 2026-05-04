<script lang="ts">
  import { onMount, onDestroy } from 'svelte';

  // ── Types ────────────────────────────────────────────────────────────────
  interface ValidationResult {
    valid: boolean;
    featureCount: number;
    geomTypes: string[];
    bbox: [number, number, number, number] | null;
    crs: string | null;
    errors: string[];
    warnings: string[];
  }

  interface ProgressEvent {
    inserted: number;
    total: number;
    pct: number;
    skipped: number;
    elapsed_s: number;
    done?: boolean;
    errors?: string[];
  }

  interface StagingLayer {
    layer_name: string;
    source: string;
    feature_count: number;
    last_imported: string | null;
    bbox: unknown;
  }

  // ── State ────────────────────────────────────────────────────────────────
  let dragging = false;
  let fileName = '';
  let layerName = '';
  let features: unknown[] = [];
  let validation: ValidationResult | null = null;
  let parsing = false;
  let parseError = '';

  let uploading = false;
  let progress: ProgressEvent | null = null;
  let uploadDone = false;
  let uploadErrors: string[] = [];

  let stagingLayers: StagingLayer[] = [];
  let loadingLayers = false;
  let deletingLayer = '';

  let apiUrl = 'http://localhost:8000';

  // ── Lifecycle ────────────────────────────────────────────────────────────
  onMount(async () => {
    try {
      const res = await fetch('/api/config');
      if (res.ok) {
        const cfg = await res.json();
        apiUrl = cfg.apiUrl ?? apiUrl;
      }
    } catch { /* use default */ }
    await loadStagingLayers();
  });

  // ── File handling ────────────────────────────────────────────────────────
  function onDragOver(e: DragEvent) {
    e.preventDefault();
    dragging = true;
  }

  function onDragLeave() {
    dragging = false;
  }

  async function onDrop(e: DragEvent) {
    e.preventDefault();
    dragging = false;
    const file = e.dataTransfer?.files[0];
    if (file) await handleFile(file);
  }

  async function onFileInput(e: Event) {
    const file = (e.target as HTMLInputElement).files?.[0];
    if (file) await handleFile(file);
  }

  async function handleFile(file: File) {
    parsing = true;
    parseError = '';
    validation = null;
    features = [];
    uploadDone = false;
    progress = null;
    uploadErrors = [];
    fileName = file.name;

    // Auto-suggest layer name from filename (strip extension, sanitise)
    if (!layerName) {
      layerName = file.name
        .replace(/\.(zip|geojson|json|kml|gpkg|csv|parquet)$/i, '')
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, '_')
        .slice(0, 64);
    }

    try {
      features = await parseFile(file);
      validation = validateFeatures(features, fileName);
    } catch (err) {
      parseError = err instanceof Error ? err.message : String(err);
    } finally {
      parsing = false;
    }
  }

  async function parseFile(file: File): Promise<unknown[]> {
    const name = file.name.toLowerCase();

    if (name.endsWith('.geojson') || name.endsWith('.json')) {
      return parseGeoJSON(await file.text());
    }

    if (name.endsWith('.kml')) {
      const { kml } = await import('@mapbox/togeojson');
      const dom = new DOMParser().parseFromString(await file.text(), 'text/xml');
      const fc = kml(dom);
      return fc.features ?? [];
    }

    if (name.endsWith('.csv')) {
      const Papa = (await import('papaparse')).default;
      return await new Promise((resolve, reject) => {
        Papa.parse(file, {
          header: true,
          dynamicTyping: true,
          skipEmptyLines: true,
          complete(result) {
            const rows = result.data as Record<string, unknown>[];
            const features = rows.map((row) => csvRowToFeature(row));
            resolve(features.filter(Boolean));
          },
          error: reject,
        });
      });
    }

    if (name.endsWith('.zip') || name.endsWith('.shp')) {
      const shp = (await import('shpjs')).default;
      const buf = await file.arrayBuffer();
      const fc = await shp(buf);
      if (Array.isArray(fc)) return fc.flatMap((f) => f.features ?? []);
      return (fc as GeoJSON.FeatureCollection).features ?? [];
    }

    if (name.endsWith('.gpkg') || name.endsWith('.parquet')) {
      throw new Error(
        `${name.endsWith('.gpkg') ? 'GeoPackage' : 'GeoParquet'} files cannot be parsed in the browser. ` +
          'Use scripts/load_supabase.sh to load this format directly from the command line.'
      );
    }

    throw new Error(
      `Unsupported format: ${file.name}. Supported: GeoJSON, KML, Shapefile ZIP, CSV (with lat/lon columns)`
    );
  }

  function parseGeoJSON(text: string): unknown[] {
    const obj = JSON.parse(text);
    if (obj.type === 'FeatureCollection') return obj.features ?? [];
    if (obj.type === 'Feature') return [obj];
    // Plain geometry — wrap it
    if (obj.type && obj.coordinates !== undefined) {
      return [{ type: 'Feature', geometry: obj, properties: {} }];
    }
    throw new Error('JSON does not appear to be a GeoJSON FeatureCollection, Feature, or Geometry.');
  }

  function csvRowToFeature(row: Record<string, unknown>): unknown {
    const latKey = Object.keys(row).find((k) => /^(lat|latitude|y)$/i.test(k));
    const lonKey = Object.keys(row).find((k) => /^(lon|lng|longitude|x)$/i.test(k));
    if (!latKey || !lonKey) return null;
    const lat = Number(row[latKey]);
    const lon = Number(row[lonKey]);
    if (!isFinite(lat) || !isFinite(lon)) return null;
    const props = { ...row };
    delete props[latKey];
    delete props[lonKey];
    return {
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [lon, lat] },
      properties: props,
    };
  }

  function validateFeatures(feats: unknown[], source: string): ValidationResult {
    const errors: string[] = [];
    const warnings: string[] = [];
    const geomTypes = new Set<string>();
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    let skipped = 0;

    const VALID_TYPES = new Set([
      'Point', 'MultiPoint', 'LineString', 'MultiLineString',
      'Polygon', 'MultiPolygon', 'GeometryCollection',
    ]);

    for (const feat of feats as Record<string, unknown>[]) {
      const geom = feat?.geometry as Record<string, unknown> | null;
      if (!geom || !geom.type) { skipped++; continue; }
      const t = geom.type as string;
      if (!VALID_TYPES.has(t)) { skipped++; continue; }
      geomTypes.add(t);

      // Extract representative coordinate for bbox
      const coords = firstCoord(geom);
      if (coords) {
        if (coords[0] < minX) minX = coords[0];
        if (coords[0] > maxX) maxX = coords[0];
        if (coords[1] < minY) minY = coords[1];
        if (coords[1] > maxY) maxY = coords[1];
        // Sanity check: coordinates look like WGS84
        if (Math.abs(coords[0]) > 180 || Math.abs(coords[1]) > 90) {
          warnings.push('Some coordinates appear to be outside WGS84 range. Ensure data is in EPSG:4326.');
        }
      }
    }

    if (feats.length === 0) errors.push('No features found in file.');
    if (feats.length > 100_000) {
      errors.push(`Too many features (${feats.length.toLocaleString()}). Max 100,000. Use scripts/load_supabase.sh for larger datasets.`);
    }
    if (skipped > 0) warnings.push(`${skipped} feature(s) have null or invalid geometry and will be skipped.`);

    // Detect likely non-WGS84 (coordinates outside ±180/±90)
    const bbox: [number, number, number, number] | null =
      isFinite(minX) ? [minX, minY, maxX, maxY] : null;

    return {
      valid: errors.length === 0,
      featureCount: feats.length,
      geomTypes: [...geomTypes],
      bbox,
      crs: 'EPSG:4326 (assumed)',
      errors,
      warnings,
    };
  }

  function firstCoord(geom: Record<string, unknown>): [number, number] | null {
    const c = geom.coordinates as unknown;
    if (!Array.isArray(c) || c.length === 0) return null;
    // Drill down to a flat [x, y] pair
    let cur: unknown = c;
    while (Array.isArray(cur) && Array.isArray(cur[0])) cur = cur[0];
    if (Array.isArray(cur) && typeof cur[0] === 'number' && typeof cur[1] === 'number') {
      return [cur[0] as number, cur[1] as number];
    }
    return null;
  }

  // ── Upload ───────────────────────────────────────────────────────────────
  async function startUpload() {
    if (!features.length || !layerName) return;
    uploading = true;
    uploadDone = false;
    uploadErrors = [];
    progress = null;

    const clean = layerName.toLowerCase().replace(/[^a-z0-9]+/g, '_').slice(0, 64);

    try {
      const res = await fetch(`${apiUrl}/ingest/features`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source: fileName, layer_name: clean, features }),
      });

      if (!res.ok) {
        const detail = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(detail.detail ?? `HTTP ${res.status}`);
      }

      // Read SSE stream
      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let buf = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split('\n\n');
        buf = lines.pop() ?? '';
        for (const chunk of lines) {
          const data = chunk.replace(/^data:\s*/, '').trim();
          if (!data) continue;
          try {
            const evt = JSON.parse(data) as ProgressEvent;
            progress = evt;
            if (evt.done) {
              uploadDone = true;
              uploadErrors = evt.errors ?? [];
            }
          } catch { /* ignore parse error on SSE chunk */ }
        }
      }
    } catch (err) {
      uploadErrors = [err instanceof Error ? err.message : String(err)];
    } finally {
      uploading = false;
      await loadStagingLayers();
    }
  }

  // ── Staging layers list ──────────────────────────────────────────────────
  async function loadStagingLayers() {
    loadingLayers = true;
    try {
      const res = await fetch(`${apiUrl}/ingest/layers`);
      if (res.ok) stagingLayers = await res.json();
    } catch { /* ignore */ }
    finally { loadingLayers = false; }
  }

  async function deleteLayer(name: string) {
    if (!confirm(`Delete all features in layer "${name}"? This cannot be undone.`)) return;
    deletingLayer = name;
    try {
      await fetch(`${apiUrl}/ingest/layer/${encodeURIComponent(name)}`, { method: 'DELETE' });
      await loadStagingLayers();
    } finally {
      deletingLayer = '';
    }
  }

  function reset() {
    fileName = '';
    layerName = '';
    features = [];
    validation = null;
    parseError = '';
    progress = null;
    uploadDone = false;
    uploadErrors = [];
  }
</script>

<svelte:head>
  <title>Upload Data — geo-stack</title>
</svelte:head>

<div class="upload-page">
  <!-- Header -->
  <header class="page-header">
    <a href="/" class="back-link">← Map</a>
    <h1>Data Upload</h1>
    <p class="subtitle">Import GeoJSON, Shapefile (ZIP), KML, or CSV into the staging database</p>
  </header>

  <div class="layout">
    <!-- Left: Upload form -->
    <section class="upload-section">

      <!-- Drop zone -->
      {#if !features.length && !parsing}
        <div
          class="drop-zone"
          class:dragging
          role="button"
          tabindex="0"
          on:dragover={onDragOver}
          on:dragleave={onDragLeave}
          on:drop={onDrop}
          on:keydown={(e) => { if (e.key === 'Enter') document.getElementById('file-input')?.click(); }}
        >
          <svg class="drop-icon" viewBox="0 0 48 48" fill="none">
            <circle cx="24" cy="24" r="22" stroke="currentColor" stroke-width="2" stroke-dasharray="4 3"/>
            <path d="M24 32V18M18 24l6-6 6 6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
          <p class="drop-text">Drag &amp; drop a file here</p>
          <p class="drop-hint">GeoJSON · KML · Shapefile ZIP · CSV</p>
          <label class="btn btn-primary" for="file-input">Browse file</label>
          <input
            id="file-input"
            type="file"
            accept=".geojson,.json,.kml,.zip,.shp,.csv,.gpkg,.parquet"
            on:change={onFileInput}
            style="display:none"
          />
        </div>

        <div class="cli-note">
          <strong>Large datasets or GeoPackage/GeoParquet?</strong>
          Use the CLI loader instead:<br/>
          <code>./scripts/load_supabase.sh data/file.gpkg staging.layer_name</code>
        </div>
      {/if}

      <!-- Parsing spinner -->
      {#if parsing}
        <div class="status-box info">
          <span class="spinner"></span> Parsing <strong>{fileName}</strong>…
        </div>
      {/if}

      <!-- Parse error -->
      {#if parseError}
        <div class="status-box error">
          <strong>Parse error:</strong> {parseError}
          <button class="btn btn-sm btn-ghost" on:click={reset}>Try another file</button>
        </div>
      {/if}

      <!-- Validation results -->
      {#if validation}
        <div class="file-summary">
          <div class="file-name-row">
            <span class="file-icon">📄</span>
            <strong>{fileName}</strong>
            <button class="btn btn-sm btn-ghost" on:click={reset}>Change</button>
          </div>

          <div class="stats-grid">
            <div class="stat">
              <span class="stat-label">Features</span>
              <span class="stat-value">{validation.featureCount.toLocaleString()}</span>
            </div>
            <div class="stat">
              <span class="stat-label">Geometry</span>
              <span class="stat-value">{validation.geomTypes.join(', ') || '—'}</span>
            </div>
            <div class="stat">
              <span class="stat-label">CRS</span>
              <span class="stat-value">{validation.crs}</span>
            </div>
            {#if validation.bbox}
              <div class="stat">
                <span class="stat-label">Extent</span>
                <span class="stat-value mono">
                  [{validation.bbox.map((n) => n.toFixed(3)).join(', ')}]
                </span>
              </div>
            {/if}
          </div>

          {#if validation.errors.length}
            <div class="status-box error">
              {#each validation.errors as e}<div>✗ {e}</div>{/each}
            </div>
          {/if}

          {#if validation.warnings.length}
            <div class="status-box warning">
              {#each validation.warnings as w}<div>⚠ {w}</div>{/each}
            </div>
          {/if}
        </div>

        <!-- Layer name + upload -->
        {#if validation.valid}
          <div class="upload-form">
            <label class="field-label" for="layer-name">
              Layer name <span class="hint">(lowercase letters, numbers, underscores)</span>
            </label>
            <input
              id="layer-name"
              class="text-input"
              bind:value={layerName}
              placeholder="e.g. kenya_admin"
              pattern="[a-z0-9_]+"
              maxlength="64"
              disabled={uploading}
            />

            {#if !uploading && !uploadDone}
              <button
                class="btn btn-primary btn-upload"
                disabled={!layerName || uploading}
                on:click={startUpload}
              >
                Upload {validation.featureCount.toLocaleString()} features
              </button>
            {/if}
          </div>
        {/if}
      {/if}

      <!-- Upload progress -->
      {#if uploading || uploadDone}
        <div class="progress-section">
          {#if progress}
            <div class="progress-header">
              <span>{progress.done ? 'Complete' : 'Uploading…'}</span>
              <span>{progress.inserted.toLocaleString()} / {progress.total.toLocaleString()} ({progress.pct}%)</span>
            </div>
            <div class="progress-bar-track">
              <div class="progress-bar-fill" style="width: {progress.pct}%"></div>
            </div>
            <div class="progress-meta">
              {#if progress.skipped > 0}
                <span class="warn-text">Skipped: {progress.skipped}</span>
              {/if}
              <span>Elapsed: {progress.elapsed_s}s</span>
            </div>
          {:else}
            <div class="status-box info"><span class="spinner"></span> Connecting…</div>
          {/if}

          {#if uploadDone}
            <div class="status-box success">
              ✓ Inserted {progress?.inserted.toLocaleString()} features into staging layer <strong>{layerName}</strong>
            </div>
            {#if uploadErrors.length}
              <div class="status-box error">
                <strong>Batch errors ({uploadErrors.length}):</strong>
                {#each uploadErrors as e}<div class="mono small">{e}</div>{/each}
              </div>
            {/if}
            <button class="btn btn-primary" on:click={reset}>Upload another file</button>
          {/if}
        </div>
      {/if}
    </section>

    <!-- Right: Staging layers -->
    <aside class="layers-aside">
      <div class="aside-header">
        <h2>Staging layers</h2>
        <button class="btn btn-sm btn-ghost" on:click={loadStagingLayers} disabled={loadingLayers}>
          {loadingLayers ? '…' : 'Refresh'}
        </button>
      </div>

      {#if stagingLayers.length === 0 && !loadingLayers}
        <p class="empty-msg">No layers yet. Upload a file to get started.</p>
      {/if}

      {#each stagingLayers as layer}
        <div class="layer-card">
          <div class="layer-info">
            <span class="layer-name">{layer.layer_name}</span>
            <span class="layer-count">{layer.feature_count.toLocaleString()} features</span>
            <span class="layer-source">{layer.source}</span>
            {#if layer.last_imported}
              <span class="layer-date">{new Date(layer.last_imported).toLocaleString()}</span>
            {/if}
          </div>
          <button
            class="btn btn-sm btn-danger"
            disabled={deletingLayer === layer.layer_name}
            on:click={() => deleteLayer(layer.layer_name)}
          >
            {deletingLayer === layer.layer_name ? '…' : 'Delete'}
          </button>
        </div>
      {/each}
    </aside>
  </div>
</div>

<style>
  .upload-page {
    min-height: 100vh;
    background: #0f0f23;
    color: #e2e8f0;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    font-size: 14px;
    padding: 0 0 64px;
  }

  .page-header {
    background: rgba(255,255,255,0.04);
    border-bottom: 1px solid rgba(255,255,255,0.08);
    padding: 16px 32px;
    display: flex;
    align-items: center;
    gap: 16px;
  }

  .back-link {
    color: #60a5fa;
    text-decoration: none;
    font-size: 13px;
    white-space: nowrap;
  }
  .back-link:hover { text-decoration: underline; }

  h1 {
    font-size: 18px;
    font-weight: 600;
    color: #f1f5f9;
  }

  .subtitle {
    font-size: 13px;
    color: #94a3b8;
    margin-left: auto;
  }

  .layout {
    display: grid;
    grid-template-columns: 1fr 360px;
    gap: 32px;
    max-width: 1100px;
    margin: 32px auto;
    padding: 0 32px;
  }

  @media (max-width: 768px) {
    .layout { grid-template-columns: 1fr; }
    .subtitle { display: none; }
    .page-header { padding: 12px 16px; }
    .layout { padding: 0 16px; }
  }

  /* Drop zone */
  .drop-zone {
    border: 2px dashed rgba(96, 165, 250, 0.4);
    border-radius: 12px;
    padding: 48px 32px;
    text-align: center;
    cursor: pointer;
    transition: border-color 0.2s, background 0.2s;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 10px;
    background: rgba(255,255,255,0.02);
  }

  .drop-zone:hover, .drop-zone.dragging {
    border-color: #60a5fa;
    background: rgba(96, 165, 250, 0.06);
  }

  .drop-icon {
    width: 48px;
    height: 48px;
    color: #60a5fa;
    margin-bottom: 4px;
  }

  .drop-text { font-size: 16px; font-weight: 500; color: #cbd5e1; }
  .drop-hint { font-size: 12px; color: #64748b; margin-bottom: 8px; }

  .cli-note {
    margin-top: 16px;
    padding: 12px 16px;
    background: rgba(255,255,255,0.04);
    border-radius: 8px;
    font-size: 13px;
    color: #94a3b8;
    line-height: 1.7;
  }

  /* Buttons */
  .btn {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 8px 16px;
    border-radius: 6px;
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
    border: none;
    transition: background 0.15s, opacity 0.15s;
  }
  .btn:disabled { opacity: 0.5; cursor: not-allowed; }

  .btn-primary {
    background: #2563eb;
    color: #fff;
  }
  .btn-primary:hover:not(:disabled) { background: #1d4ed8; }

  .btn-ghost {
    background: rgba(255,255,255,0.06);
    color: #94a3b8;
  }
  .btn-ghost:hover:not(:disabled) { background: rgba(255,255,255,0.1); }

  .btn-danger {
    background: rgba(239,68,68,0.15);
    color: #f87171;
    border: 1px solid rgba(239,68,68,0.25);
  }
  .btn-danger:hover:not(:disabled) { background: rgba(239,68,68,0.25); }

  .btn-sm { padding: 4px 10px; font-size: 12px; }
  .btn-upload { width: 100%; justify-content: center; padding: 12px; font-size: 14px; margin-top: 8px; }

  /* Status boxes */
  .status-box {
    border-radius: 8px;
    padding: 12px 16px;
    margin: 12px 0;
    font-size: 13px;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .status-box.info { background: rgba(96,165,250,0.1); border: 1px solid rgba(96,165,250,0.2); color: #93c5fd; flex-direction: row; align-items: center; gap: 10px; }
  .status-box.error { background: rgba(239,68,68,0.1); border: 1px solid rgba(239,68,68,0.2); color: #fca5a5; }
  .status-box.warning { background: rgba(234,179,8,0.1); border: 1px solid rgba(234,179,8,0.2); color: #fde68a; }
  .status-box.success { background: rgba(34,197,94,0.1); border: 1px solid rgba(34,197,94,0.2); color: #86efac; }

  /* Spinner */
  .spinner {
    display: inline-block;
    width: 14px;
    height: 14px;
    border: 2px solid rgba(255,255,255,0.2);
    border-top-color: #60a5fa;
    border-radius: 50%;
    animation: spin 0.7s linear infinite;
    flex-shrink: 0;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  /* File summary */
  .file-summary {
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 10px;
    padding: 16px;
    margin-bottom: 16px;
  }

  .file-name-row {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 14px;
    font-weight: 500;
    color: #f1f5f9;
  }
  .file-icon { font-size: 16px; }

  .stats-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
  }

  .stat {
    background: rgba(255,255,255,0.03);
    border-radius: 6px;
    padding: 8px 12px;
  }
  .stat-label { display: block; font-size: 11px; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 2px; }
  .stat-value { font-size: 13px; color: #cbd5e1; font-weight: 500; }
  .mono { font-family: 'SF Mono', 'Fira Code', monospace; font-size: 12px; }
  .small { font-size: 12px; }

  /* Upload form */
  .upload-form { margin-top: 4px; }

  .field-label {
    display: block;
    font-size: 12px;
    font-weight: 500;
    color: #94a3b8;
    margin-bottom: 6px;
  }
  .hint { color: #64748b; font-weight: 400; }

  .text-input {
    width: 100%;
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 6px;
    padding: 8px 12px;
    color: #f1f5f9;
    font-size: 14px;
    outline: none;
    transition: border-color 0.15s;
  }
  .text-input:focus { border-color: #3b82f6; }
  .text-input:disabled { opacity: 0.5; }

  /* Progress */
  .progress-section {
    margin-top: 8px;
  }

  .progress-header {
    display: flex;
    justify-content: space-between;
    font-size: 13px;
    color: #94a3b8;
    margin-bottom: 6px;
  }

  .progress-bar-track {
    height: 6px;
    background: rgba(255,255,255,0.08);
    border-radius: 3px;
    overflow: hidden;
  }

  .progress-bar-fill {
    height: 100%;
    background: linear-gradient(90deg, #2563eb, #3b82f6);
    border-radius: 3px;
    transition: width 0.3s ease;
  }

  .progress-meta {
    display: flex;
    gap: 16px;
    font-size: 12px;
    color: #64748b;
    margin-top: 6px;
  }
  .warn-text { color: #fbbf24; }

  /* Aside */
  .layers-aside {
    background: rgba(255,255,255,0.02);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 12px;
    padding: 20px;
    align-self: start;
  }

  .aside-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
  }

  h2 {
    font-size: 14px;
    font-weight: 600;
    color: #f1f5f9;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .empty-msg {
    color: #475569;
    font-size: 13px;
    text-align: center;
    padding: 24px 0;
  }

  .layer-card {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 12px;
    padding: 12px;
    border-radius: 8px;
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.06);
    margin-bottom: 8px;
  }

  .layer-info {
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
  }

  .layer-name {
    font-weight: 600;
    font-size: 13px;
    color: #e2e8f0;
    font-family: 'SF Mono', monospace;
  }
  .layer-count { font-size: 12px; color: #60a5fa; }
  .layer-source { font-size: 11px; color: #475569; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .layer-date { font-size: 11px; color: #475569; }

  code {
    background: rgba(255,255,255,0.06);
    padding: 2px 6px;
    border-radius: 4px;
    font-family: 'SF Mono', 'Fira Code', monospace;
    font-size: 12px;
  }
</style>
