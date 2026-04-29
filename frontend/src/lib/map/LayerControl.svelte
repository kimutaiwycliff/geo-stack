<script lang="ts">
  import maplibregl from 'maplibre-gl';
  import { layers, type LayerConfig } from '$lib/config/layers';
  import {
    layerVisibility, toggleLayer, setLayerVisible,
    layerOrder, moveLayerInOrder,
    layerOpacity, setLayerOpacity,
  } from '$lib/stores/layerStore';
  import { mapStore, mapLoaded } from '$lib/stores/mapStore';
  import { basemapId, BASEMAPS, legendVisible, darkMode } from '$lib/stores/uiStore';

  const isBrowser = typeof window !== 'undefined';
  const layerMap = Object.fromEntries(layers.map((l) => [l.id, l]));

  let collapsed: boolean = isBrowser
    ? (JSON.parse(localStorage.getItem('geo:layers-collapsed') ?? 'false') as boolean)
    : false;

  $: if (isBrowser) localStorage.setItem('geo:layers-collapsed', JSON.stringify(collapsed));

  // ── Drag-and-drop ──────────────────────────────────────────────────────────
  let dragFromIndex: number | null = null;
  let dragOverIndex: number | null = null;

  function onDragStart(index: number): void { dragFromIndex = index; }
  function onDragOver(e: DragEvent, index: number): void { e.preventDefault(); dragOverIndex = index; }
  function onDrop(index: number): void {
    if (dragFromIndex !== null && dragFromIndex !== index) moveLayerInOrder(dragFromIndex, index);
    dragFromIndex = null; dragOverIndex = null;
  }
  function onDragEnd(): void { dragFromIndex = null; dragOverIndex = null; }

  // ── Zoom to layer ──────────────────────────────────────────────────────────
  function zoomToLayer(layer: LayerConfig): void {
    const map = $mapStore;
    if (!map || !$mapLoaded) return;
    if (!$layerVisibility[layer.id]) setLayerVisible(layer.id, true);

    if (layer.bounds) {
      map.fitBounds(layer.bounds as maplibregl.LngLatBoundsLike, { padding: 48, duration: 800, maxZoom: layer.maxzoom ?? 16 });
      return;
    }
    if (layer.type === 'geojson' && map.getSource(layer.id)) {
      const bbox = featureBounds(map.querySourceFeatures(layer.id));
      if (bbox) { map.fitBounds(bbox, { padding: 48, duration: 800 }); return; }
    }
    const bbox = featureBounds(map.queryRenderedFeatures(undefined, { layers: [layer.id] }));
    if (bbox) map.fitBounds(bbox, { padding: 48, duration: 800 });
  }

  function featureBounds(features: maplibregl.MapGeoJSONFeature[]): maplibregl.LngLatBounds | null {
    if (!features.length) return null;
    const bounds = new maplibregl.LngLatBounds();
    for (const f of features) if (f.geometry) extendBounds(bounds, f.geometry);
    return bounds.isEmpty() ? null : bounds;
  }

  function extendBounds(bounds: maplibregl.LngLatBounds, geom: GeoJSON.Geometry): void {
    switch (geom.type) {
      case 'Point': bounds.extend(geom.coordinates as [number, number]); break;
      case 'MultiPoint': case 'LineString':
        for (const c of geom.coordinates) bounds.extend(c as [number, number]); break;
      case 'MultiLineString': case 'Polygon':
        for (const ring of geom.coordinates) for (const c of ring) bounds.extend(c as [number, number]); break;
      case 'MultiPolygon':
        for (const poly of geom.coordinates) for (const ring of poly) for (const c of ring) bounds.extend(c as [number, number]); break;
      case 'GeometryCollection':
        for (const g of geom.geometries) extendBounds(bounds, g); break;
    }
  }

  function onOpacityInput(layerId: string, e: Event): void {
    const val = parseFloat((e.target as HTMLInputElement).value);
    setLayerOpacity(layerId, val);
  }
</script>

<div class="panel layer-control" class:collapsed>

  <!-- ── Panel header ────────────────────────────────────────────────────── -->
  <div class="panel-header">
    <h2>Layers</h2>
    <div class="header-actions">
      <!-- Dark / light mode toggle -->
      <button
        class="icon-btn"
        title={$darkMode ? 'Switch to light mode' : 'Switch to dark mode'}
        aria-label={$darkMode ? 'Switch to light mode' : 'Switch to dark mode'}
        on:click={() => darkMode.update((v) => !v)}
      >
        {#if $darkMode}
          <!-- Sun icon — click to go light -->
          <svg viewBox="0 0 16 16" width="13" height="13" fill="none" stroke="currentColor"
               stroke-width="1.6" stroke-linecap="round">
            <circle cx="8" cy="8" r="3"/>
            <line x1="8" y1="1"   x2="8"   y2="3.2"/>
            <line x1="8" y1="12.8" x2="8"  y2="15"/>
            <line x1="1"   y1="8" x2="3.2" y2="8"/>
            <line x1="12.8" y1="8" x2="15" y2="8"/>
            <line x1="3.4" y1="3.4" x2="5"   y2="5"/>
            <line x1="11"  y1="11"  x2="12.6" y2="12.6"/>
            <line x1="3.4" y1="12.6" x2="5"   y2="11"/>
            <line x1="11"  y1="5"    x2="12.6" y2="3.4"/>
          </svg>
        {:else}
          <!-- Moon icon — click to go dark -->
          <svg viewBox="0 0 16 16" width="13" height="13" fill="currentColor">
            <path d="M7.5 1.5a6.5 6.5 0 1 0 7 7 5 5 0 0 1-7-7z"/>
          </svg>
        {/if}
      </button>

      <!-- Collapse toggle -->
      <button
        class="icon-btn"
        title={collapsed ? 'Expand panel' : 'Collapse panel'}
        on:click={() => (collapsed = !collapsed)}
        aria-label={collapsed ? 'Expand panel' : 'Collapse panel'}
      >
        <svg
          viewBox="0 0 12 12" width="12" height="12" fill="none"
          stroke="currentColor" stroke-width="2" stroke-linecap="round"
          style="transform: rotate({collapsed ? '-90deg' : '0deg'}); transition: transform 0.2s"
        >
          <path d="M2 4l4 4 4-4"/>
        </svg>
      </button>
    </div>
  </div>

  {#if !collapsed}

    <!-- ── Basemap selector ──────────────────────────────────────────────── -->
    <div class="basemap-section">
      <span class="section-label">Basemap</span>
      <div class="basemap-pills">
        {#each BASEMAPS as bm}
          <button
            class="pill"
            class:active={$basemapId === bm.id}
            on:click={() => basemapId.set(bm.id)}
          >{bm.label}</button>
        {/each}
      </div>
    </div>

    <div class="divider" />

    <!-- ── Layer list (ordered by layerOrder store) ──────────────────────── -->
    {#each $layerOrder as layerId, index}
      {@const layer = layerMap[layerId]}
      {#if layer}
        <div
          class="layer-item"
          class:drag-over={dragOverIndex === index && dragFromIndex !== index}
          draggable="true"
          on:dragstart={() => onDragStart(index)}
          on:dragover={(e) => onDragOver(e, index)}
          on:drop={() => onDrop(index)}
          on:dragend={onDragEnd}
          role="listitem"
        >
          <!-- Row 1: handle | checkbox | label | zoom -->
          <div class="layer-row">
            <span class="drag-handle" aria-hidden="true">
              <svg viewBox="0 0 8 12" width="8" height="12">
                <circle cx="2" cy="2"  r="1" fill="currentColor"/>
                <circle cx="6" cy="2"  r="1" fill="currentColor"/>
                <circle cx="2" cy="6"  r="1" fill="currentColor"/>
                <circle cx="6" cy="6"  r="1" fill="currentColor"/>
                <circle cx="2" cy="10" r="1" fill="currentColor"/>
                <circle cx="6" cy="10" r="1" fill="currentColor"/>
              </svg>
            </span>

            <label class="layer-toggle">
              <input
                type="checkbox"
                checked={$layerVisibility[layerId] ?? false}
                on:change={() => toggleLayer(layerId)}
              />
              <span class="layer-label">{layer.label}</span>
            </label>

            <button
              class="icon-btn"
              title="Zoom to {layer.label}"
              disabled={!$mapLoaded}
              on:click={() => zoomToLayer(layer)}
              aria-label="Zoom to {layer.label}"
            >
              <svg viewBox="0 0 16 16" width="13" height="13" fill="none"
                   stroke="currentColor" stroke-width="1.6" stroke-linecap="round">
                <circle cx="8" cy="8" r="4.5"/>
                <line x1="8" y1="1"    x2="8"  y2="3.5"/>
                <line x1="8" y1="12.5" x2="8"  y2="15"/>
                <line x1="1" y1="8"    x2="3.5" y2="8"/>
                <line x1="12.5" y1="8" x2="15" y2="8"/>
              </svg>
            </button>
          </div>

          <!-- Row 2: opacity slider -->
          <div class="opacity-row">
            <span class="opacity-label">Opacity</span>
            <input
              type="range"
              min="0" max="1" step="0.01"
              value={$layerOpacity[layerId] ?? 1}
              on:input={(e) => onOpacityInput(layerId, e)}
              class="opacity-slider"
              aria-label="Opacity for {layer.label}"
            />
            <span class="opacity-pct">{Math.round(($layerOpacity[layerId] ?? 1) * 100)}%</span>
          </div>
        </div>
      {/if}
    {/each}

    <div class="divider" />

    <!-- ── Legend toggle ─────────────────────────────────────────────────── -->
    <label class="legend-toggle">
      <input type="checkbox" bind:checked={$legendVisible} />
      <span>Show Legend</span>
    </label>

  {/if}
</div>

<style>
  .panel-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
  }

  .panel-header h2 { margin-bottom: 0; }

  .header-actions {
    display: flex;
    align-items: center;
    gap: 2px;
    flex-shrink: 0;
  }

  .layer-control.collapsed { min-width: 0; }

  /* ── Basemap ────────────────────────────────────────────────────────────── */
  .basemap-section {
    margin-top: 8px;
    margin-bottom: 8px;
  }

  .section-label {
    display: block;
    font-size: 11px;
    font-weight: 600;
    color: #9ca3af;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin-bottom: 5px;
  }

  .basemap-pills {
    display: flex;
    gap: 4px;
    flex-wrap: wrap;
  }

  .pill {
    font-size: 11px;
    padding: 2px 8px;
    border-radius: 999px;
    border: 1px solid #d1d5db;
    background: #f9fafb;
    color: #374151;
    cursor: pointer;
    transition: background 0.15s, border-color 0.15s, color 0.15s;
    white-space: nowrap;
  }
  .pill:hover { background: #eff6ff; border-color: #93c5fd; color: #1d4ed8; }
  .pill.active { background: #2563eb; border-color: #2563eb; color: #fff; }

  /* ── Divider ────────────────────────────────────────────────────────────── */
  .divider { height: 1px; background: #e5e7eb; margin: 6px -4px; }

  /* ── Layer item (wraps row + opacity) ───────────────────────────────────── */
  .layer-item {
    border-top: 2px solid transparent;
    border-radius: 2px;
    transition: border-color 0.1s;
    padding: 2px 0;
  }
  .layer-item.drag-over { border-top-color: #2563eb; }

  /* ── Layer rows ─────────────────────────────────────────────────────────── */
  .layer-row {
    display: flex;
    align-items: center;
    gap: 3px;
  }

  .drag-handle {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 16px;
    height: 20px;
    color: #d1d5db;
    cursor: grab;
    transition: color 0.15s;
  }
  .drag-handle:hover { color: #9ca3af; }
  .drag-handle:active { cursor: grabbing; }

  .layer-toggle {
    display: flex;
    align-items: center;
    gap: 7px;
    flex: 1;
    cursor: pointer;
    user-select: none;
    min-width: 0;
  }
  .layer-toggle:hover .layer-label { color: #1d4ed8; }

  .layer-label {
    font-size: 13px;
    color: #374151;
    transition: color 0.15s;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  input[type='checkbox'] {
    flex-shrink: 0;
    width: 14px;
    height: 14px;
    accent-color: #2563eb;
    cursor: pointer;
  }

  /* ── Opacity row ────────────────────────────────────────────────────────── */
  .opacity-row {
    display: flex;
    align-items: center;
    gap: 5px;
    padding-left: 19px; /* align with label, past drag-handle */
    margin-top: 2px;
    margin-bottom: 3px;
  }

  .opacity-label {
    font-size: 10px;
    color: #9ca3af;
    flex-shrink: 0;
    width: 38px;
  }

  .opacity-slider {
    flex: 1;
    height: 3px;
    accent-color: #2563eb;
    cursor: pointer;
    min-width: 0;
  }

  .opacity-pct {
    font-size: 10px;
    color: #9ca3af;
    width: 28px;
    text-align: right;
    flex-shrink: 0;
  }

  /* ── Legend toggle row ──────────────────────────────────────────────────── */
  .legend-toggle {
    display: flex;
    align-items: center;
    gap: 7px;
    margin-top: 4px;
    cursor: pointer;
    user-select: none;
    font-size: 12px;
    color: #6b7280;
  }
  .legend-toggle:hover { color: #374151; }

  /* ── Icon buttons ───────────────────────────────────────────────────────── */
  .icon-btn {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 22px;
    height: 22px;
    padding: 0;
    border: 1px solid transparent;
    border-radius: 4px;
    background: none;
    color: #9ca3af;
    cursor: pointer;
    transition: color 0.15s, background 0.15s, border-color 0.15s;
  }
  .icon-btn:hover:not(:disabled) { color: #2563eb; background: #eff6ff; border-color: #bfdbfe; }
  .icon-btn:active:not(:disabled) { background: #dbeafe; }
  .icon-btn:disabled { opacity: 0.35; cursor: default; }

  /* ── Touch-friendly tap targets ─────────────────────────────────────────── */
  @media (pointer: coarse) {
    .icon-btn { width: 36px; height: 36px; }
    .drag-handle { width: 24px; height: 28px; }
    .opacity-slider { height: 6px; }
    .pill { padding: 4px 12px; font-size: 12px; }
  }

  /* ── Mobile: slide up from bottom ──────────────────────────────────────── */
  @media (max-width: 640px) {
    .layer-control {
      top: auto;
      bottom: 48px;
      left: 0;
      right: 0;
      max-width: 100%;
      border-radius: 14px 14px 0 0;
      max-height: 60vh;
      overflow-y: auto;
    }
  }

  /* ── Dark mode (html.dark class) ───────────────────────────────────────── */
  :global(html.dark) .section-label { color: #6b7280; }
  :global(html.dark) .pill {
    background: #1f2937;
    border-color: #374151;
    color: #d1d5db;
  }
  :global(html.dark) .pill:hover { background: #1e3a5f; border-color: #3b82f6; color: #93c5fd; }
  :global(html.dark) .pill.active { background: #2563eb; border-color: #2563eb; color: #fff; }
  :global(html.dark) .divider { background: #374151; }
  :global(html.dark) .layer-label { color: #d1d5db; }
  :global(html.dark) .layer-toggle:hover .layer-label { color: #93c5fd; }
  :global(html.dark) .opacity-label,
  :global(html.dark) .opacity-pct { color: #6b7280; }
  :global(html.dark) .legend-toggle { color: #6b7280; }
  :global(html.dark) .legend-toggle:hover { color: #d1d5db; }
  :global(html.dark) .icon-btn { color: #6b7280; }
  :global(html.dark) .icon-btn:hover:not(:disabled) { color: #3b82f6; background: #1e3a5f; border-color: #3b82f6; }
  :global(html.dark) .icon-btn:active:not(:disabled) { background: #1d4ed8; }
</style>
