import { writable, derived } from 'svelte/store';
import { layers, type LayerConfig } from '$lib/config/layers';

const isBrowser = typeof window !== 'undefined';

// ── Layer visibility ────────────────────────────────────────────────────────

const defaultVisibility = Object.fromEntries(
  layers.map((l) => [l.id, l.visible ?? false])
);

function loadVisibility(): Record<string, boolean> {
  if (!isBrowser) return defaultVisibility;
  try {
    const raw = localStorage.getItem('geo:layer-vis');
    if (!raw) return defaultVisibility;
    const stored = JSON.parse(raw) as Record<string, boolean>;
    return Object.fromEntries(
      Object.entries(defaultVisibility).map(([id, def]) => [id, stored[id] ?? def])
    );
  } catch {
    return defaultVisibility;
  }
}

export const layerVisibility = writable<Record<string, boolean>>(loadVisibility());

if (isBrowser) {
  layerVisibility.subscribe((vis) => {
    try { localStorage.setItem('geo:layer-vis', JSON.stringify(vis)); } catch { /* ignore */ }
  });
}

export const visibleLayerIds = derived(layerVisibility, ($vis) =>
  Object.entries($vis).filter(([, v]) => v).map(([id]) => id)
);

// ── Layer opacity ───────────────────────────────────────────────────────────

function getConfigOpacity(config: LayerConfig): number {
  const paint = config.paint ?? {};
  for (const key of ['fill-opacity', 'circle-opacity', 'line-opacity', 'raster-opacity']) {
    const val = paint[key];
    if (typeof val === 'number') return val;
  }
  return 1;
}

const defaultOpacity = Object.fromEntries(layers.map((l) => [l.id, getConfigOpacity(l)]));

function loadOpacity(): Record<string, number> {
  if (!isBrowser) return defaultOpacity;
  try {
    const raw = localStorage.getItem('geo:layer-opacity');
    if (!raw) return defaultOpacity;
    const stored = JSON.parse(raw) as Record<string, number>;
    return Object.fromEntries(
      Object.entries(defaultOpacity).map(([id, def]) => [id, stored[id] ?? def])
    );
  } catch {
    return defaultOpacity;
  }
}

export const layerOpacity = writable<Record<string, number>>(loadOpacity());

if (isBrowser) {
  layerOpacity.subscribe((op) => {
    try { localStorage.setItem('geo:layer-opacity', JSON.stringify(op)); } catch { /* ignore */ }
  });
}

// ── Layer order ─────────────────────────────────────────────────────────────

export const layerOrder = writable<string[]>(layers.map((l) => l.id));

// Per-layer hover popup — config-only (no runtime toggle)
export const hoverPopupLayers = writable<Record<string, boolean>>(
  Object.fromEntries(layers.map((l) => [l.id, l.hoverPopup ?? false]))
);

// ── Mutation helpers ────────────────────────────────────────────────────────

export function toggleLayer(id: string): void {
  layerVisibility.update((vis) => ({ ...vis, [id]: !vis[id] }));
}

export function setLayerVisible(id: string, visible: boolean): void {
  layerVisibility.update((vis) => ({ ...vis, [id]: visible }));
}

export function setLayerOpacity(id: string, opacity: number): void {
  layerOpacity.update((op) => ({ ...op, [id]: opacity }));
}

export function moveLayerInOrder(fromIndex: number, toIndex: number): void {
  layerOrder.update((order) => {
    const next = [...order];
    const [removed] = next.splice(fromIndex, 1);
    next.splice(toIndex, 0, removed);
    return next;
  });
}
