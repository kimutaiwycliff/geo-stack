import { writable } from 'svelte/store';
import type { StyleSpecification } from 'maplibre-gl';

const isBrowser = typeof window !== 'undefined';

// ESRI World Imagery — free raster satellite tiles, no API key required
const SATELLITE_STYLE: StyleSpecification = {
  version: 8,
  sources: {
    sat: {
      type: 'raster',
      tiles: [
        'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
      ],
      tileSize: 256,
      maxzoom: 19,
      attribution: 'Tiles &copy; Esri &mdash; Esri, USGS, AEX, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community',
    },
  },
  layers: [{ id: 'sat', type: 'raster', source: 'sat' }],
};

export interface BasemapEntry {
  id: string;
  label: string;
  style: string | StyleSpecification;
}

export const BASEMAPS: BasemapEntry[] = [
  {
    id: 'street',
    label: 'Street',
    // OpenFreeMap Liberty — vector style with near-3D building extrusions
    style: 'https://tiles.openfreemap.org/styles/liberty',
  },
  {
    id: 'satellite',
    label: 'Satellite',
    style: SATELLITE_STYLE,
  },
  {
    id: 'dark',
    label: 'Dark',
    style: 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json',
  },
];

export type BasemapId = 'street' | 'satellite' | 'dark';

// ── Persistence helpers ────────────────────────────────────────────────────

function loadBasemapId(): BasemapId {
  if (!isBrowser) return 'street';
  try {
    const raw = localStorage.getItem('geo:basemap');
    if (raw) {
      const id = JSON.parse(raw) as string;
      // Validate that the stored ID still exists in BASEMAPS (handles config changes)
      if (BASEMAPS.some((b) => b.id === id)) return id as BasemapId;
    }
  } catch { /* ignore */ }
  return 'street';
}

function loadBool(key: string, def: boolean): boolean {
  if (!isBrowser) return def;
  try {
    const raw = localStorage.getItem(key);
    if (raw !== null) return JSON.parse(raw) as boolean;
  } catch { /* ignore */ }
  return def;
}

// ── Stores ─────────────────────────────────────────────────────────────────

export const basemapId = writable<BasemapId>(loadBasemapId());
export const legendVisible = writable<boolean>(loadBool('geo:legend', true));
export const darkMode = writable<boolean>(loadBool('geo:dark', false));
export const measureActive = writable<boolean>(false);

export interface ContextMenuState { x: number; y: number; lngLat: [number, number]; }
export const contextMenu = writable<ContextMenuState | null>(null);

// Persist every change back to localStorage
if (isBrowser) {
  basemapId.subscribe((id) => {
    try { localStorage.setItem('geo:basemap', JSON.stringify(id)); } catch { /* ignore */ }
  });
  legendVisible.subscribe((v) => {
    try { localStorage.setItem('geo:legend', JSON.stringify(v)); } catch { /* ignore */ }
  });
  darkMode.subscribe((v) => {
    try { localStorage.setItem('geo:dark', JSON.stringify(v)); } catch { /* ignore */ }
  });
}
