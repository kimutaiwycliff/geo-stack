<script lang="ts">
  import { onMount } from 'svelte';
  import MapLibre from '$lib/map/MapLibre.svelte';
  import LayerControl from '$lib/map/LayerControl.svelte';
  import Legend from '$lib/map/Legend.svelte';
  import SearchControl from '$lib/map/SearchControl.svelte';
  import MeasureTool from '$lib/map/MeasureTool.svelte';
  import ContextMenu from '$lib/map/ContextMenu.svelte';
  import { mapLoaded } from '$lib/stores/mapStore';
  import { darkMode } from '$lib/stores/uiStore';

  $: if (typeof document !== 'undefined') {
    document.documentElement.classList.toggle('dark', $darkMode);
  }

  let configLoaded = false;

  onMount(async () => {
    try {
      const res = await fetch('/api/config');
      if (res.ok) {
        const config = await res.json();
        (window as Window & { __GEO_CONFIG__?: unknown }).__GEO_CONFIG__ = config;
      }
    } catch {
      // Fall back to env-var defaults in layers.ts
    }
    configLoaded = true;
  });
</script>

<svelte:head>
  <title>geo-stack — Spatial Data Explorer</title>
</svelte:head>

<!-- Loading overlay: always in DOM, fades out when map is ready -->
<div class="loading-overlay" class:map-ready={$mapLoaded}>
  <div class="geo-loader">
    <div class="pin-wrap">
      <svg class="loader-pin" viewBox="0 0 48 64" width="52" height="68" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M24 2C13.51 2 5 10.51 5 21C5 35.25 24 62 24 62C24 62 43 35.25 43 21C43 10.51 34.49 2 24 2Z" fill="#2563eb"/>
        <path d="M24 2C13.51 2 5 10.51 5 21C5 24.8 6.1 28.35 8 31.3C10.5 14.5 18 6.5 24 4.5C30 6.5 37.5 14.5 40 31.3C41.9 28.35 43 24.8 43 21C43 10.51 34.49 2 24 2Z" fill="#3b82f6" opacity="0.5"/>
        <circle cx="24" cy="21" r="7" fill="white"/>
        <circle cx="24" cy="21" r="4" fill="#2563eb"/>
      </svg>
      <div class="loader-ripple"></div>
    </div>
    <p class="loader-label">Loading map</p>
    <div class="loader-dots">
      <span></span><span></span><span></span>
    </div>
  </div>
</div>

{#if configLoaded}
  <MapLibre />
  <LayerControl />
  <Legend />
  <SearchControl />
  <MeasureTool />
  <ContextMenu />
{/if}
