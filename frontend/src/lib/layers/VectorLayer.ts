/**
 * VectorLayer.ts — Add an MVT source from Martin to a MapLibre map.
 *
 * Martin serves tiles directly from PostGIS at:
 *   {MARTIN_URL}/{schema}.{table}/{z}/{x}/{y}
 *
 * The tile URL template is stored in LayerConfig.url.
 * Geometry type determines which MapLibre layer type to use (fill, line, circle, symbol).
 */

import type { Map } from 'maplibre-gl';
import type { LayerConfig } from '$lib/config/layers';

export function addVectorLayer(map: Map, config: LayerConfig): void {
  const sourceId = config.id;

  if (map.getSource(sourceId)) return;  // Already added (e.g. on re-mount)

  map.addSource(sourceId, {
    type: 'vector',
    tiles: [config.url],
    minzoom: config.minzoom ?? 0,
    maxzoom: config.maxzoom ?? 22,
  });

  // Detect geometry type from paint keys to choose the right layer type
  const paintKeys = Object.keys(config.paint ?? {});
  let layerType: 'fill' | 'line' | 'circle' | 'symbol' = 'fill';
  if (paintKeys.some((k) => k.startsWith('circle-'))) layerType = 'circle';
  else if (paintKeys.some((k) => k.startsWith('line-'))) layerType = 'line';
  else if (paintKeys.some((k) => k.startsWith('text-') || k.startsWith('icon-'))) layerType = 'symbol';

  map.addLayer({
    id: sourceId,
    type: layerType as never,
    source: sourceId,
    'source-layer': config.sourceLayer ?? config.id,
    paint: (config.paint ?? {}) as never,
    layout: {
      ...(config.layout ?? {}),
      visibility: config.visible ? 'visible' : 'none',
    } as never,
    minzoom: config.minzoom ?? 0,
    maxzoom: config.maxzoom ?? 22,
  });
}

export function setVectorLayerVisibility(map: Map, id: string, visible: boolean): void {
  if (map.getLayer(id)) {
    map.setLayoutProperty(id, 'visibility', visible ? 'visible' : 'none');
  }
}
