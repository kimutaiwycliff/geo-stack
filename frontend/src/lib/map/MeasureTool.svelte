<script lang="ts">
  import { onDestroy } from 'svelte';
  import maplibregl from 'maplibre-gl';
  import { mapStore, mapLoaded } from '$lib/stores/mapStore';
  import { measureActive, contextMenu } from '$lib/stores/uiStore';

  const SRC   = '__measure';
  const LINE  = '__measure-line';
  const DOTS  = '__measure-dots';

  let points: [number, number][] = [];
  let popup: maplibregl.Popup | null = null;
  let clickAttached = false;

  // ── Distance helpers ────────────────────────────────────────────────────────

  function haversineKm(a: [number, number], b: [number, number]): number {
    const R = 6371;
    const rad = (d: number) => (d * Math.PI) / 180;
    const dLat = rad(b[1] - a[1]);
    const dLng = rad(b[0] - a[0]);
    const h =
      Math.sin(dLat / 2) ** 2 +
      Math.cos(rad(a[1])) * Math.cos(rad(b[1])) * Math.sin(dLng / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(h));
  }

  function fmtDist(km: number): string {
    return km < 1 ? `${Math.round(km * 1000)} m` : `${km.toFixed(2)} km`;
  }

  // ── GeoJSON for the measure layer ──────────────────────────────────────────

  function buildData(): GeoJSON.FeatureCollection {
    const features: GeoJSON.Feature[] = points.map((p) => ({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: p },
      properties: {},
    }));
    if (points.length === 2) {
      features.push({
        type: 'Feature',
        geometry: { type: 'LineString', coordinates: points },
        properties: {},
      });
    }
    return { type: 'FeatureCollection', features };
  }

  // ── Layer setup / teardown ─────────────────────────────────────────────────

  function setupLayers(m: maplibregl.Map): void {
    if (!m.getSource(SRC)) {
      m.addSource(SRC, { type: 'geojson', data: buildData() });
    }
    if (!m.getLayer(LINE)) {
      m.addLayer({
        id: LINE,
        type: 'line',
        source: SRC,
        filter: ['==', '$type', 'LineString'],
        paint: { 'line-color': '#2563eb', 'line-width': 2, 'line-dasharray': [3, 2] },
      });
    }
    if (!m.getLayer(DOTS)) {
      m.addLayer({
        id: DOTS,
        type: 'circle',
        source: SRC,
        filter: ['==', '$type', 'Point'],
        paint: {
          'circle-radius': 6,
          'circle-color': '#2563eb',
          'circle-stroke-width': 2.5,
          'circle-stroke-color': '#ffffff',
        },
      });
    }
    syncLayer(m);
  }

  function removeLayers(m: maplibregl.Map): void {
    try {
      if (m.getLayer(DOTS))  m.removeLayer(DOTS);
      if (m.getLayer(LINE))  m.removeLayer(LINE);
      if (m.getSource(SRC))  m.removeSource(SRC);
    } catch { /* map may already be in a transition */ }
    popup?.remove();
  }

  function syncLayer(m: maplibregl.Map): void {
    (m.getSource(SRC) as maplibregl.GeoJSONSource)?.setData(buildData());

    if (points.length === 2) {
      const dist = fmtDist(haversineKm(points[0], points[1]));
      if (!popup) {
        popup = new maplibregl.Popup({ closeButton: true, closeOnClick: false, offset: 12 });
        popup.on('close', () => { popup = null; });
      }
      popup
        .setLngLat(points[1])
        .setHTML(
          `<div style="font-size:13px;font-weight:600;color:#111827">${dist}</div>` +
          `<div style="font-size:11px;color:#6b7280;margin-top:2px">Click map to measure again</div>`
        )
        .addTo(m);
    } else {
      popup?.remove();
      popup = null;
    }
  }

  // ── Click handler ──────────────────────────────────────────────────────────

  function handleClick(e: maplibregl.MapMouseEvent): void {
    contextMenu.set(null);
    const m = $mapStore;
    if (!m) return;
    const pt: [number, number] = [e.lngLat.lng, e.lngLat.lat];
    points = points.length >= 2 ? [pt] : [...points, pt];
    syncLayer(m);
  }

  // ── Reactive: activate / deactivate / re-init after basemap switch ─────────

  $: {
    const m       = $mapStore;
    const loaded  = $mapLoaded;
    const active  = $measureActive;

    if (!m) break $;

    if (active && loaded) {
      setupLayers(m);
      if (!clickAttached) {
        m.on('click', handleClick);
        clickAttached = true;
      }
      m.getCanvas().style.cursor = 'crosshair';
    } else if (!active && clickAttached) {
      m.off('click', handleClick);
      clickAttached = false;
      removeLayers(m);
      m.getCanvas().style.cursor = '';
      points = [];
    }
  }

  onDestroy(() => {
    const m = $mapStore;
    if (m) {
      if (clickAttached) m.off('click', handleClick);
      try { removeLayers(m); } catch { /* ignore */ }
    }
    popup?.remove();
  });
</script>
