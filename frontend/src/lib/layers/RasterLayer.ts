/**
 * RasterLayer.ts — Add raster tiles from TiTiler to MapLibre.
 *
 * TiTiler reads Cloud-Optimized GeoTIFFs (COGs) and serves them as XYZ tiles.
 * The COG can be a local file or on R2/S3 (accessed via GDAL's VSI driver).
 *
 * TiTiler tile URL format:
 *   {TITILER_URL}/cog/tiles/{z}/{x}/{y}.png?url={cog_url}&colormap_name=ndvi
 */

import type { Map } from 'maplibre-gl';
import type { LayerConfig } from '$lib/config/layers';

export function addRasterLayer(map: Map, config: LayerConfig): void {
  const sourceId = config.id;

  if (map.getSource(sourceId)) return;

  map.addSource(sourceId, {
    type: 'raster',
    tiles: [config.url],
    tileSize: 256,
    minzoom: config.minzoom ?? 0,
    maxzoom: config.maxzoom ?? 22,
  });

  map.addLayer({
    id: sourceId,
    type: 'raster',
    source: sourceId,
    paint: {
      'raster-opacity': (config.paint?.['raster-opacity'] as number | undefined) ?? 0.8,
      ...(config.paint as Record<string, unknown> ?? {}),
    },
    layout: {
      visibility: config.visible ? 'visible' : 'none',
    },
    minzoom: config.minzoom ?? 0,
    maxzoom: config.maxzoom ?? 22,
  });
}
