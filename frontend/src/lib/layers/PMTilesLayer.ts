/**
 * PMTilesLayer.ts — Add a PMTiles source to MapLibre GL.
 *
 * PMTiles is a single-file archive of vector tiles served via HTTP range requests.
 * No tile server needed — just a URL to the .pmtiles file on R2 or any static host.
 *
 * The pmtiles JS library hooks into MapLibre's protocol system so the standard
 * addSource API works with 'pmtiles://' URLs.
 *
 * Setup (called once at app init in MapLibre.svelte):
 *   import { Protocol } from 'pmtiles';
 *   const protocol = new Protocol();
 *   maplibregl.addProtocol('pmtiles', protocol.tile.bind(protocol));
 */

import type { Map } from 'maplibre-gl';
import type { LayerConfig } from '$lib/config/layers';

export function addPMTilesLayer(map: Map, config: LayerConfig): void {
  const sourceId = config.id;

  if (map.getSource(sourceId)) return;

  // pmtiles:// protocol is registered globally by MapLibre.svelte on init
  const pmtilesUrl = config.url.startsWith('pmtiles://')
    ? config.url
    : `pmtiles://${config.url}`;

  map.addSource(sourceId, {
    type: 'vector',
    url: pmtilesUrl,
    minzoom: config.minzoom ?? 0,
    maxzoom: config.maxzoom ?? 22,
  });

  const paintKeys = Object.keys(config.paint ?? {});
  let layerType: 'fill' | 'line' | 'circle' = 'fill';
  if (paintKeys.some((k) => k.startsWith('circle-'))) layerType = 'circle';
  else if (paintKeys.some((k) => k.startsWith('line-'))) layerType = 'line';

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
