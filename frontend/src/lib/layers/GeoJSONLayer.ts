/**
 * GeoJSONLayer.ts — Fetch GeoJSON from FastAPI and add it as a MapLibre source.
 *
 * MapLibre's native 'geojson' source type handles fetching and updating automatically
 * when given a URL. For dynamic filters (bbox, limit), we update the source data
 * on map moveend events.
 *
 * For feature counts above ~5000 visible at once, switch to MVT or PMTiles instead.
 */

import type { Map } from 'maplibre-gl';
import type { LayerConfig } from '$lib/config/layers';

export function addGeoJSONLayer(map: Map, config: LayerConfig): void {
  const sourceId = config.id;

  if (map.getSource(sourceId)) return;

  map.addSource(sourceId, {
    type: 'geojson',
    data: config.url,   // MapLibre fetches this URL and keeps it updated
    generateId: true,   // Assigns unique IDs for feature state (hover highlighting)
  });

  const paintKeys = Object.keys(config.paint ?? {});
  let layerType: 'fill' | 'line' | 'circle' | 'symbol' = 'circle';
  if (paintKeys.some((k) => k.startsWith('fill-'))) layerType = 'fill';
  else if (paintKeys.some((k) => k.startsWith('line-'))) layerType = 'line';
  else if (paintKeys.some((k) => k.startsWith('text-') || k.startsWith('icon-'))) layerType = 'symbol';

  map.addLayer({
    id: sourceId,
    type: layerType as never,
    source: sourceId,
    paint: (config.paint ?? {}) as never,
    layout: {
      ...(config.layout ?? {}),
      visibility: config.visible ? 'visible' : 'none',
    } as never,
    minzoom: config.minzoom ?? 0,
    maxzoom: config.maxzoom ?? 22,
  });
}

/** Re-fetch GeoJSON with a new bbox filter. Called on map pan/zoom. */
export function refreshGeoJSONWithBBox(map: Map, config: LayerConfig): void {
  const source = map.getSource(config.id) as maplibregl.GeoJSONSource | undefined;
  if (!source) return;

  const bounds = map.getBounds();
  const bboxParam = [
    bounds.getWest().toFixed(6),
    bounds.getSouth().toFixed(6),
    bounds.getEast().toFixed(6),
    bounds.getNorth().toFixed(6),
  ].join(',');

  const separator = config.url.includes('?') ? '&' : '?';
  source.setData(`${config.url}${separator}bbox=${bboxParam}`);
}
