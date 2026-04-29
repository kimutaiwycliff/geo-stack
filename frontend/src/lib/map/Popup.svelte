<script lang="ts">
  /**
   * Popup.svelte — Feature click popup.
   * Renders a MapLibre GL popup at the clicked coordinates,
   * showing only the fields specified in LayerConfig.popupFields.
   */

  import { onMount, onDestroy, createEventDispatcher } from 'svelte';
  import maplibregl from 'maplibre-gl';
  import type { Map } from 'maplibre-gl';
  import type { LayerConfig } from '$lib/config/layers';

  export let feature: Record<string, unknown>;
  export let config: LayerConfig;
  export let lngLat: [number, number];
  export let map: Map;

  const dispatch = createEventDispatcher<{ close: void }>();
  let popup: maplibregl.Popup;

  function formatValue(val: unknown): string {
    if (val === null || val === undefined) return '—';
    if (typeof val === 'object') return JSON.stringify(val);
    return String(val);
  }

  // First field with a 'name' key, or first popupField value, as the popup title
  $: title = (() => {
    const nameField = config.popupFields?.find((f) => f.toLowerCase().includes('name'));
    if (nameField && feature[nameField]) return formatValue(feature[nameField]);
    if (config.popupFields?.[0]) return formatValue(feature[config.popupFields[0]]);
    return config.label;
  })();

  $: rows = (config.popupFields ?? [])
    .filter((field) => feature[field] !== undefined)
    .map((field) => ({
      key: field.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()),
      value: formatValue(feature[field]),
    }));

  onMount(() => {
    popup = new maplibregl.Popup({ closeButton: true, maxWidth: '300px' })
      .setLngLat(lngLat)
      .setHTML('<div id="popup-content"></div>')
      .addTo(map);

    popup.on('close', () => dispatch('close'));

    // Inject content into MapLibre's popup DOM node
    const el = document.getElementById('popup-content');
    if (el) {
      el.innerHTML = `
        <div class="popup-title">${title}</div>
        ${rows.map((r) => `
          <div class="popup-row">
            <span class="popup-key">${r.key}</span>
            <span class="popup-value">${r.value}</span>
          </div>
        `).join('')}
      `;
    }
  });

  onDestroy(() => {
    popup?.remove();
  });
</script>
