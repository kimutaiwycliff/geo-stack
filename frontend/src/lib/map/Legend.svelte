<script lang="ts">
  import { layers } from '$lib/config/layers';
  import { layerVisibility } from '$lib/stores/layerStore';
  import { legendVisible } from '$lib/stores/uiStore';

  interface LegendEntry { color: string; label?: string; }
  interface LegendLayer { id: string; label: string; entries: LegendEntry[]; }

  // Parse a MapLibre paint object and extract color swatches.
  // Handles: plain string, ['match', ...] expressions. Falls back to #6b7280.
  function parseLegendEntries(paint: Record<string, unknown>): LegendEntry[] {
    const raw = paint['fill-color'] ?? paint['circle-color'] ?? paint['line-color'];

    if (typeof raw === 'string') return [{ color: raw }];

    if (Array.isArray(raw) && raw[0] === 'match') {
      // ['match', ['get', field], val1, color1, val2, color2, ..., fallback]
      const entries: LegendEntry[] = [];
      let i = 2; // skip 'match' and the input expression
      while (i < raw.length - 1) {
        const label = raw[i];
        const color = raw[i + 1];
        if (typeof color === 'string') entries.push({ color, label: String(label) });
        i += 2;
      }
      const fallback = raw[raw.length - 1];
      if (entries.length > 0 && typeof fallback === 'string') {
        entries.push({ color: fallback, label: 'Other' });
      }
      return entries.length > 0 ? entries : [{ color: '#6b7280' }];
    }

    return [{ color: '#6b7280' }];
  }

  // Get the geometry type indicator for a layer (used as swatch shape)
  function swatchShape(layerType: string, paint: Record<string, unknown>): 'circle' | 'line' | 'square' {
    if (layerType === 'geojson') {
      const keys = Object.keys(paint);
      if (keys.some(k => k.startsWith('circle-'))) return 'circle';
      if (keys.some(k => k.startsWith('line-'))) return 'line';
    }
    if (layerType === 'mvt' || layerType === 'pmtiles') {
      const keys = Object.keys(paint);
      if (keys.some(k => k.startsWith('line-'))) return 'line';
      if (keys.some(k => k.startsWith('fill-'))) return 'square';
    }
    return 'square';
  }

  $: legendLayers = layers
    .filter((l) => $layerVisibility[l.id] && l.paint)
    .map((l): LegendLayer => ({
      id: l.id,
      label: l.label,
      entries: parseLegendEntries(l.paint ?? {}),
    }));
</script>

{#if $legendVisible && legendLayers.length > 0}
  <div class="panel legend">
    <h2>Legend</h2>
    {#each legendLayers as layer}
      <div class="legend-layer">
        {#if layer.entries.length > 1}
          <!-- Categorical layer: show group header + per-category swatches -->
          <div class="legend-group-label">{layer.label}</div>
          {#each layer.entries as entry}
            <div class="legend-row indent">
              <span class="swatch" style="background: {entry.color};" />
              <span class="legend-label">{entry.label ?? ''}</span>
            </div>
          {/each}
        {:else}
          <!-- Single-color layer: swatch + layer name on one line -->
          <div class="legend-row">
            <span class="swatch" style="background: {layer.entries[0].color};" />
            <span class="legend-label">{layer.label}</span>
          </div>
        {/if}
      </div>
    {/each}
  </div>
{/if}

<style>
  .legend { bottom: 48px; left: 16px; }

  .legend-layer { margin-bottom: 6px; }
  .legend-layer:last-child { margin-bottom: 0; }

  .legend-group-label {
    font-size: 11px;
    font-weight: 600;
    color: #374151;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    margin-bottom: 3px;
  }

  .legend-row {
    display: flex;
    align-items: center;
    gap: 7px;
    padding: 1px 0;
  }

  .legend-row.indent { padding-left: 4px; }

  .swatch {
    flex-shrink: 0;
    width: 13px;
    height: 13px;
    border-radius: 3px;
    border: 1px solid rgba(0, 0, 0, 0.1);
  }

  .legend-label {
    font-size: 12px;
    color: #374151;
    text-transform: capitalize;
  }

  /* ── Mobile: move to bottom-right so it doesn't clash with bottom panel ─── */
  @media (max-width: 640px) {
    .legend {
      bottom: auto;
      top: 16px;
      left: auto;
      right: 16px;
      max-width: 44vw;
    }
  }

  /* ── Dark mode (html.dark class) ───────────────────────────────────────── */
  :global(html.dark) .legend-group-label { color: #9ca3af; }
  :global(html.dark) .legend-label { color: #d1d5db; }
  :global(html.dark) .swatch { border-color: rgba(255,255,255,0.12); }
</style>
