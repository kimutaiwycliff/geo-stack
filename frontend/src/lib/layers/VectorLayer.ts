/**
 * VectorLayer.ts — Add an MVT source from Martin to a MapLibre map.
 *
 * For polygon layers styled with line- paint (boundary outlines), we add an
 * invisible fill layer with id `${id}__hit` beneath the line layer so that
 * hover/click events fire anywhere inside the polygon, not just on the border.
 */

import type { Map } from 'maplibre-gl';
import type { LayerConfig } from '$lib/config/layers';

/** Strip the hit-layer suffix to recover the original config id. */
export function configIdFromLayerId(layerId: string): string {
  return layerId.endsWith('__hit') ? layerId.slice(0, -5) : layerId;
}

/** True when this layer id belongs to an invisible hit layer. */
export function isHitLayer(layerId: string): boolean {
  return layerId.endsWith('__hit');
}

export function addVectorLayer(map: Map, config: LayerConfig): void {
  const sourceId = config.id;

  if (map.getSource(sourceId)) return;

  map.addSource(sourceId, {
    type: 'vector',
    tiles: [config.url],
    minzoom: config.minzoom ?? 0,
    maxzoom: config.maxzoom ?? 22,
  });

  const paintKeys = Object.keys(config.paint ?? {});
  let layerType: 'fill' | 'line' | 'circle' | 'symbol' = 'fill';
  if (paintKeys.some((k) => k.startsWith('circle-'))) layerType = 'circle';
  else if (paintKeys.some((k) => k.startsWith('line-'))) layerType = 'line';
  else if (paintKeys.some((k) => k.startsWith('text-') || k.startsWith('icon-'))) layerType = 'symbol';

  // For polygon data styled as line (boundary outlines), add an invisible fill
  // layer first so that queryRenderedFeatures hits the whole polygon interior,
  // not just the stroke pixels. For true line geometry this is a no-op.
  if (layerType === 'line') {
    map.addLayer({
      id: `${sourceId}__hit`,
      type: 'fill',
      source: sourceId,
      'source-layer': config.sourceLayer ?? config.id,
      paint: { 'fill-opacity': 0 },
      layout: { visibility: config.visible ? 'visible' : 'none' },
      minzoom: config.minzoom ?? 0,
      maxzoom: config.maxzoom ?? 22,
    });
  }

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
  const hitId = `${id}__hit`;
  if (map.getLayer(hitId)) {
    map.setLayoutProperty(hitId, 'visibility', visible ? 'visible' : 'none');
  }
}
