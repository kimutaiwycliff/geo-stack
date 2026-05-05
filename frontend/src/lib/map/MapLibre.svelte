<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { get } from 'svelte/store';
  import maplibregl from 'maplibre-gl';
  import { Protocol } from 'pmtiles';
  import { mapStore, mapLoaded } from '$lib/stores/mapStore';
  import { layerVisibility, layerOrder, hoverPopupLayers, layerOpacity } from '$lib/stores/layerStore';
  import { basemapId, BASEMAPS, measureActive, contextMenu } from '$lib/stores/uiStore';
  import type { BasemapId } from '$lib/stores/uiStore';
  import { layers, type LayerConfig } from '$lib/config/layers';
  import { addVectorLayer, configIdFromLayerId } from '$lib/layers/VectorLayer';
  import { addPMTilesLayer } from '$lib/layers/PMTilesLayer';
  import { addGeoJSONLayer, refreshGeoJSONWithBBox } from '$lib/layers/GeoJSONLayer';
  import { addRasterLayer } from '$lib/layers/RasterLayer';
  import Popup from './Popup.svelte';

  let mapContainer: HTMLDivElement;
  let map: maplibregl.Map;

  let clickPopupFeature: Record<string, unknown> | null = null;
  let clickPopupConfig: LayerConfig | null = null;
  let clickPopupLngLat: [number, number] | null = null;

  let hoverPopup: maplibregl.Popup;
  let hoverLayersSnap: Record<string, boolean> = {};

  let unsubVis: () => void;
  let unsubOrder: () => void;
  let unsubHoverLayers: () => void;
  let unsubBasemap: () => void;
  let unsubOpacity: () => void;
  let fsCleanup: (() => void) | null = null;
  let measureBtnCleanup: (() => void) | null = null;

  const protocol = new Protocol();
  maplibregl.addProtocol('pmtiles', protocol.tile.bind(protocol));

  // ── URL hash: #zoom/lat/lng/basemapId ────────────────────────────────────

  function readHash(): { center: [number, number]; zoom: number; basemap?: BasemapId } | null {
    if (typeof window === 'undefined') return null;
    const h = window.location.hash.slice(1);
    if (!h) return null;
    const [z, lat, lng, bm] = h.split('/');
    const zoom = parseFloat(z);
    const la   = parseFloat(lat);
    const ln   = parseFloat(lng);
    if (isNaN(zoom) || isNaN(la) || isNaN(ln)) return null;
    const basemap = BASEMAPS.some((b) => b.id === bm) ? (bm as BasemapId) : undefined;
    return { center: [ln, la], zoom, basemap };
  }

  function writeHash(m: maplibregl.Map, bm: string): void {
    const c = m.getCenter();
    history.replaceState(
      null, '',
      `#${m.getZoom().toFixed(2)}/${c.lat.toFixed(5)}/${c.lng.toFixed(5)}/${bm}`
    );
  }

  // ── Paint-property helpers ────────────────────────────────────────────────

  function opacityProp(config: LayerConfig): string {
    if (config.type === 'raster') return 'raster-opacity';
    const keys = Object.keys(config.paint ?? {});
    if (keys.some((k) => k.startsWith('circle-'))) return 'circle-opacity';
    if (keys.some((k) => k.startsWith('line-')))   return 'line-opacity';
    return 'fill-opacity';
  }

  function addLayerToMap(m: maplibregl.Map, config: LayerConfig): void {
    switch (config.type) {
      case 'mvt':     addVectorLayer(m, config);  break;
      case 'pmtiles': addPMTilesLayer(m, config); break;
      case 'geojson': addGeoJSONLayer(m, config); break;
      case 'raster':  addRasterLayer(m, config);  break;
    }
  }

  function applyLayerOrder(order: string[]): void {
    for (let i = order.length - 1; i >= 0; i--) {
      const id = order[i];
      if (map.getLayer(id)) map.moveLayer(id);
    }
  }

  function applyAllOpacities(): void {
    const opacities = get(layerOpacity);
    layers.forEach((config) => {
      if (map.getLayer(config.id)) {
        map.setPaintProperty(config.id, opacityProp(config), opacities[config.id] ?? 1);
      }
    });
  }

  function setupMapLayers(): void {
    const vis   = get(layerVisibility);
    const order = get(layerOrder);
    layers.forEach((config) => addLayerToMap(map, config));
    layers.forEach((config) => {
      const v = vis[config.id] ? 'visible' : 'none';
      if (map.getLayer(config.id)) map.setLayoutProperty(config.id, 'visibility', v);
      const hitId = `${config.id}__hit`;
      if (map.getLayer(hitId)) map.setLayoutProperty(hitId, 'visibility', v);
    });
    applyLayerOrder(order);
    applyAllOpacities();
  }

  function buildHoverHTML(props: Record<string, unknown>, config: LayerConfig): string {
    const fields    = config.popupFields ?? [];
    const nameField = fields.find((f) => f.toLowerCase().includes('name'));
    const rawTitle  = (nameField && props[nameField] != null) ? props[nameField] : (props[fields[0]] ?? config.label);
    const title     = String(rawTitle);
    const rows = fields
      .filter((f) => props[f] != null)
      .map((f) => {
        const key = f.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
        return `<div class="popup-row">
          <span class="popup-key">${key}</span>
          <span class="popup-value">${String(props[f])}</span>
        </div>`;
      })
      .join('');
    return `<div class="popup-title">${title}</div>${rows}`;
  }

  onMount(() => {
    // ── Apply URL hash (if present) before creating map ──────────────────────
    const hashState = readHash();
    if (hashState?.basemap) basemapId.set(hashState.basemap);

    const initialBm    = BASEMAPS.find((b) => b.id === get(basemapId)) ?? BASEMAPS[0];
    const initialStyle = initialBm.style as maplibregl.StyleSpecification;

    map = new maplibregl.Map({
      container: mapContainer,
      style: initialStyle,
      center: hashState?.center ?? [36.82, -1.29],
      zoom:   hashState?.zoom   ?? 10,
    });

    mapStore.set(map);

    // ── Standard MapLibre controls ──────────────────────────────────────────
    map.addControl(new maplibregl.NavigationControl(), 'top-right');
    map.addControl(new maplibregl.ScaleControl({ unit: 'metric' }), 'bottom-right');
    map.addControl(
      new maplibregl.GeolocateControl({ positionOptions: { enableHighAccuracy: true } }),
      'top-right'
    );

    // ── Custom controls group ───────────────────────────────────────────────
    map.addControl({
      onAdd(m: maplibregl.Map) {
        const el = document.createElement('div');
        el.className = 'maplibregl-ctrl maplibregl-ctrl-group';
        el.style.cssText = 'display:flex;flex-direction:column;';

        // --- Measure distance button ---
        const measureBtn = document.createElement('button');
        measureBtn.title = 'Measure distance';
        measureBtn.setAttribute('aria-label', 'Measure distance');
        measureBtn.style.cssText = 'display:flex;align-items:center;justify-content:center;padding:0;width:29px;height:29px;';
        measureBtn.innerHTML = `<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="1" y="5" width="14" height="6" rx="1"/><line x1="4" y1="8" x2="4" y2="11"/><line x1="7" y1="8" x2="7" y2="10"/><line x1="10" y1="8" x2="10" y2="11"/><line x1="13" y1="8" x2="13" y2="10"/></svg>`;
        measureBtn.addEventListener('click', () => {
          measureActive.update((v) => !v);
        });

        // Sync button appearance with measureActive store
        const unsubMeasure = measureActive.subscribe((active) => {
          measureBtn.style.background   = active ? '#eff6ff' : '';
          measureBtn.style.color        = active ? '#2563eb' : '';
          measureBtn.title              = active ? 'Stop measuring' : 'Measure distance';
          measureBtn.setAttribute('aria-label', measureBtn.title);
        });
        measureBtnCleanup = unsubMeasure;

        // --- Fullscreen button ---
        const fsBtn = document.createElement('button');
        fsBtn.style.cssText = 'display:flex;align-items:center;justify-content:center;padding:0;width:29px;height:29px;';

        const EXPAND_ICON   = `<svg viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><polyline points="1,5 1,1 5,1"/><polyline points="11,1 15,1 15,5"/><polyline points="15,11 15,15 11,15"/><polyline points="5,15 1,15 1,11"/></svg>`;
        const COMPRESS_ICON = `<svg viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><polyline points="5,1 5,5 1,5"/><polyline points="11,1 11,5 15,5"/><polyline points="15,11 11,11 11,15"/><polyline points="1,11 5,11 5,15"/></svg>`;

        const syncFsIcon = () => {
          const isFs = !!document.fullscreenElement;
          fsBtn.title = isFs ? 'Exit fullscreen' : 'Enter fullscreen';
          fsBtn.setAttribute('aria-label', fsBtn.title);
          fsBtn.innerHTML = isFs ? COMPRESS_ICON : EXPAND_ICON;
        };
        syncFsIcon();
        fsBtn.addEventListener('click', () => {
          if (document.fullscreenElement) document.exitFullscreen();
          else document.documentElement.requestFullscreen();
        });
        document.addEventListener('fullscreenchange', syncFsIcon);
        fsCleanup = () => document.removeEventListener('fullscreenchange', syncFsIcon);

        el.appendChild(measureBtn);
        el.appendChild(fsBtn);
        return el;
      },
      onRemove() {
        fsCleanup?.();       fsCleanup       = null;
        measureBtnCleanup?.(); measureBtnCleanup = null;
      },
    }, 'top-right');

    // ── Hover popup instance ────────────────────────────────────────────────
    hoverPopup = new maplibregl.Popup({
      closeButton: false,
      closeOnClick: false,
      maxWidth: '280px',
      offset: 12,
    });

    // ── Initial layer setup ─────────────────────────────────────────────────
    map.on('load', () => {
      setupMapLayers();
      mapLoaded.set(true);
      writeHash(map, get(basemapId));
    });

    // Fires synchronously for inline styles and after every setStyle() call.
    // The gate prevents double-setup on initial load (where 'load' is primary).
    map.on('style.load', () => {
      if (get(mapLoaded)) return;
      setupMapLayers();
      mapLoaded.set(true);
      writeHash(map, get(basemapId));
    });

    // ── Persistent map event handlers ───────────────────────────────────────

    map.on('click', (e) => {
      contextMenu.set(null);
      if (get(measureActive)) return; // MeasureTool handles clicks in measure mode

      // Include __hit fill layers so polygon interiors are clickable, not just borders.
      const activeIds = layers
        .flatMap((l) => [l.id, `${l.id}__hit`])
        .filter((id) => map.getLayer(id));
      if (!activeIds.length) return;
      const features = map.queryRenderedFeatures(e.point, { layers: activeIds });
      if (!features.length) { clickPopupFeature = null; return; }

      const feature = features[0];
      const config  = layers.find((l) => l.id === configIdFromLayerId(feature.layer.id));
      if (!config?.popupFields?.length) { clickPopupFeature = null; return; }

      clickPopupFeature = feature.properties as Record<string, unknown>;
      clickPopupConfig  = config;
      clickPopupLngLat  = [e.lngLat.lng, e.lngLat.lat];
    });

    map.on('contextmenu', (e) => {
      e.preventDefault?.();
      clickPopupFeature = null; // dismiss any open click popup
      contextMenu.set({ x: e.point.x, y: e.point.y, lngLat: [e.lngLat.lng, e.lngLat.lat] });
    });

    map.on('mousemove', (e) => {
      if (get(measureActive)) return; // keep crosshair cursor during measure

      const activeIds = layers
        .flatMap((l) => [l.id, `${l.id}__hit`])
        .filter((id) => map.getLayer(id));
      if (!activeIds.length) { map.getCanvas().style.cursor = ''; return; }

      const features = map.queryRenderedFeatures(e.point, { layers: activeIds });
      map.getCanvas().style.cursor = features.length ? 'pointer' : '';

      // hoverLayersSnap is keyed by config.id; strip __hit suffix to match.
      const hoverFeature = features.find((f) => hoverLayersSnap[configIdFromLayerId(f.layer.id)]);
      if (!hoverFeature) { hoverPopup.remove(); return; }

      const config = layers.find((l) => l.id === configIdFromLayerId(hoverFeature.layer.id));
      if (!config?.popupFields?.length) { hoverPopup.remove(); return; }

      hoverPopup
        .setLngLat(e.lngLat)
        .setHTML(buildHoverHTML(hoverFeature.properties as Record<string, unknown>, config))
        .addTo(map);
    });

    map.on('mouseout', () => {
      if (get(measureActive)) return;
      hoverPopup.remove();
      map.getCanvas().style.cursor = '';
    });

    map.on('movestart', () => { contextMenu.set(null); });

    map.on('moveend', () => {
      layers.filter((l) => l.type === 'geojson').forEach((l) => refreshGeoJSONWithBBox(map, l));
      if (get(mapLoaded)) writeHash(map, get(basemapId));
    });

    // ── Store subscriptions ─────────────────────────────────────────────────

    unsubVis = layerVisibility.subscribe((vis) => {
      if (!get(mapLoaded)) return;
      layers.forEach((config) => {
        const v = vis[config.id] ? 'visible' : 'none';
        if (map.getLayer(config.id)) map.setLayoutProperty(config.id, 'visibility', v);
        const hitId = `${config.id}__hit`;
        if (map.getLayer(hitId)) map.setLayoutProperty(hitId, 'visibility', v);
      });
    });

    let firstOrderFire = true;
    unsubOrder = layerOrder.subscribe((order) => {
      if (firstOrderFire) { firstOrderFire = false; return; }
      if (get(mapLoaded)) applyLayerOrder(order);
    });

    unsubHoverLayers = hoverPopupLayers.subscribe((val) => { hoverLayersSnap = val; });

    unsubOpacity = layerOpacity.subscribe((opacities) => {
      if (!get(mapLoaded)) return;
      layers.forEach((config) => {
        if (map.getLayer(config.id)) {
          map.setPaintProperty(config.id, opacityProp(config), opacities[config.id] ?? 1);
        }
      });
    });

    let firstBasemapFire = true;
    unsubBasemap = basemapId.subscribe((id) => {
      if (firstBasemapFire) { firstBasemapFire = false; return; }

      hoverPopup.remove();
      clickPopupFeature = null;
      contextMenu.set(null);
      mapLoaded.set(false);

      const bm = BASEMAPS.find((b) => b.id === id) ?? BASEMAPS[0];
      map.setStyle(bm.style as maplibregl.StyleSpecification);
      // Layers + opacities are re-applied by the permanent 'style.load' handler.
      // Hash is updated there too once mapLoaded becomes true.
    });
  });

  onDestroy(() => {
    unsubVis?.();
    unsubOrder?.();
    unsubHoverLayers?.();
    unsubBasemap?.();
    unsubOpacity?.();
    fsCleanup?.();
    measureBtnCleanup?.();
    measureActive.set(false);
    contextMenu.set(null);
    hoverPopup?.remove();
    map?.remove();
    mapStore.set(null);
    mapLoaded.set(false);
  });
</script>

<div bind:this={mapContainer} id="map" />

{#if clickPopupFeature && clickPopupConfig && clickPopupLngLat}
  <Popup
    feature={clickPopupFeature}
    config={clickPopupConfig}
    lngLat={clickPopupLngLat}
    {map}
    on:close={() => { clickPopupFeature = null; }}
  />
{/if}
