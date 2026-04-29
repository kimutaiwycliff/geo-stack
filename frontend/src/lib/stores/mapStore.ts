/**
 * mapStore.ts — MapLibre GL instance store.
 *
 * Components subscribe to this store to access the map instance.
 * The map is initialised in MapLibre.svelte and set here once ready.
 */

import { writable } from 'svelte/store';
import type { Map } from 'maplibre-gl';

export const mapStore = writable<Map | null>(null);
export const mapLoaded = writable<boolean>(false);
