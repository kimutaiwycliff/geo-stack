<script lang="ts">
  import { get } from 'svelte/store';
  import { mapStore, mapLoaded } from '$lib/stores/mapStore';

  interface NominatimResult {
    place_id: number;
    display_name: string;
    lat: string;
    lon: string;
    boundingbox: [string, string, string, string]; // [south, north, west, east]
  }

  const isBrowser = typeof window !== 'undefined';
  let collapsed: boolean = isBrowser
    ? (JSON.parse(localStorage.getItem('geo:search-collapsed') ?? 'false') as boolean)
    : false;

  $: if (isBrowser) localStorage.setItem('geo:search-collapsed', JSON.stringify(collapsed));
  let query = '';
  let results: NominatimResult[] = [];
  let loading = false;
  let inputEl: HTMLInputElement;
  let searchTimeout: ReturnType<typeof setTimeout> | null = null;

  function onInput() {
    if (searchTimeout) clearTimeout(searchTimeout);
    results = [];
    if (!query.trim()) return;
    searchTimeout = setTimeout(doSearch, 400);
  }

  async function doSearch() {
    loading = true;
    try {
      const res = await fetch(
        `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(query.trim())}&format=json&limit=6&addressdetails=0`,
        { headers: { 'Accept-Language': 'en' } }
      );
      results = await res.json();
    } catch {
      results = [];
    } finally {
      loading = false;
    }
  }

  function onKeyDown(e: KeyboardEvent) {
    if (e.key === 'Enter') {
      if (searchTimeout) { clearTimeout(searchTimeout); searchTimeout = null; }
      doSearch();
    }
    if (e.key === 'Escape') { results = []; query = ''; }
  }

  function selectResult(r: NominatimResult) {
    const map = get(mapStore);
    if (!map) return;
    const [south, north, west, east] = r.boundingbox.map(Number);
    map.fitBounds([[west, south], [east, north]], { padding: 48, duration: 800, maxZoom: 16 });
    // Show the short name in the input
    query = r.display_name.split(',')[0].trim();
    results = [];
  }

  function expand() {
    collapsed = false;
    // Focus input after Svelte re-renders
    setTimeout(() => inputEl?.focus(), 50);
  }
</script>

{#if collapsed}
  <button class="search-collapsed" on:click={expand} title="Search location" aria-label="Search location">
    <svg viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor"
         stroke-width="1.8" stroke-linecap="round">
      <circle cx="7" cy="7" r="4.5"/>
      <line x1="10.5" y1="10.5" x2="14" y2="14"/>
    </svg>
  </button>
{:else}
  <div class="search-wrap">
    <div class="panel search-panel">
      <div class="search-row">
        <svg class="search-icon" viewBox="0 0 16 16" width="14" height="14" fill="none"
             stroke="#9ca3af" stroke-width="1.8" stroke-linecap="round">
          <circle cx="7" cy="7" r="4.5"/>
          <line x1="10.5" y1="10.5" x2="14" y2="14"/>
        </svg>
        <input
          bind:this={inputEl}
          bind:value={query}
          on:input={onInput}
          on:keydown={onKeyDown}
          type="text"
          placeholder="Search location…"
          class="search-input"
          aria-label="Search location"
          autocomplete="off"
          spellcheck="false"
        />
        {#if loading}
          <span class="spinner" aria-hidden="true" />
        {:else if query}
          <button class="clear-btn" on:click={() => { query = ''; results = []; inputEl?.focus(); }} aria-label="Clear search">
            <svg viewBox="0 0 12 12" width="10" height="10" stroke="currentColor" stroke-width="2" stroke-linecap="round">
              <line x1="1" y1="1" x2="11" y2="11"/>
              <line x1="11" y1="1" x2="1" y2="11"/>
            </svg>
          </button>
        {/if}
        <button class="collapse-btn" on:click={() => { collapsed = true; results = []; }} aria-label="Close search">
          <svg viewBox="0 0 12 12" width="11" height="11" fill="none" stroke="currentColor"
               stroke-width="2" stroke-linecap="round">
            <path d="M2 4l4 4 4-4"/>
          </svg>
        </button>
      </div>

      {#if results.length > 0}
        <ul class="results" role="listbox">
          {#each results as r (r.place_id)}
            <li
              role="option"
              aria-selected="false"
              class="result-item"
              on:click={() => selectResult(r)}
              on:keydown={(e) => e.key === 'Enter' && selectResult(r)}
              tabindex="0"
            >
              <svg class="result-icon" viewBox="0 0 12 16" width="10" height="13" fill="#9ca3af">
                <path d="M6 0C3.24 0 1 2.24 1 5c0 3.75 5 11 5 11s5-7.25 5-11c0-2.76-2.24-5-5-5zm0 7.5C4.62 7.5 3.5 6.38 3.5 5s1.12-2.5 2.5-2.5S8.5 3.62 8.5 5 7.38 7.5 6 7.5z"/>
              </svg>
              <span class="result-name">{r.display_name}</span>
            </li>
          {/each}
        </ul>
      {:else if !loading && query && results.length === 0 && !searchTimeout}
        <p class="no-results">No results found</p>
      {/if}
    </div>
  </div>
{/if}

<style>
  /* Collapsed state: small floating pill at top-center */
  .search-collapsed {
    position: absolute;
    top: 16px;
    left: 50%;
    transform: translateX(-50%);
    z-index: 10;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 36px;
    height: 36px;
    border-radius: 8px;
    border: none;
    background: rgba(255, 255, 255, 0.95);
    backdrop-filter: blur(8px);
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.2);
    cursor: pointer;
    color: #374151;
    transition: background 0.15s;
  }
  .search-collapsed:hover { background: #f0f4ff; }

  /* Expanded state wrapper */
  .search-wrap {
    position: absolute;
    top: 16px;
    left: 50%;
    transform: translateX(-50%);
    z-index: 10;
    width: 340px;
    max-width: calc(100vw - 200px); /* room for left/right controls */
  }

  .search-panel {
    position: relative; /* override absolute from .panel in app.css */
    padding: 8px 10px;
  }

  .search-row {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .search-icon { flex-shrink: 0; }

  .search-input {
    flex: 1;
    border: none;
    outline: none;
    background: transparent;
    font-size: 13px;
    color: #111827;
    min-width: 0;
  }

  .search-input::placeholder { color: #9ca3af; }

  .clear-btn, .collapse-btn {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 20px;
    height: 20px;
    border: none;
    border-radius: 4px;
    background: none;
    color: #9ca3af;
    cursor: pointer;
    padding: 0;
    transition: color 0.15s, background 0.15s;
  }
  .clear-btn:hover, .collapse-btn:hover { color: #374151; background: #f3f4f6; }

  /* Results dropdown */
  .results {
    list-style: none;
    margin: 6px 0 0;
    padding: 0;
    border-top: 1px solid #e5e7eb;
    max-height: 220px;
    overflow-y: auto;
  }

  .result-item {
    display: flex;
    align-items: flex-start;
    gap: 7px;
    padding: 7px 2px;
    cursor: pointer;
    border-radius: 4px;
    transition: background 0.1s;
    border-bottom: 1px solid #f3f4f6;
  }
  .result-item:last-child { border-bottom: none; }
  .result-item:hover, .result-item:focus { background: #eff6ff; outline: none; }

  .result-icon { flex-shrink: 0; margin-top: 1px; }

  .result-name {
    font-size: 12px;
    color: #374151;
    line-height: 1.4;
    word-break: break-word;
  }

  .no-results {
    font-size: 12px;
    color: #9ca3af;
    text-align: center;
    padding: 8px 0 2px;
  }

  /* Loading spinner */
  .spinner {
    flex-shrink: 0;
    width: 13px;
    height: 13px;
    border: 2px solid #e5e7eb;
    border-top-color: #2563eb;
    border-radius: 50%;
    animation: spin 0.7s linear infinite;
  }

  @keyframes spin { to { transform: rotate(360deg); } }

  /* ── Touch-friendly tap targets ─────────────────────────────────────────── */
  @media (pointer: coarse) {
    .search-collapsed { width: 44px; height: 44px; }
    .clear-btn, .collapse-btn { width: 28px; height: 28px; }
    .result-item { padding: 10px 4px; }
  }

  /* ── Mobile: full-width search ──────────────────────────────────────────── */
  @media (max-width: 640px) {
    .search-wrap {
      width: calc(100vw - 32px);
      max-width: none;
    }
  }

  /* ── Dark mode (html.dark class) ───────────────────────────────────────── */
  :global(html.dark) .search-collapsed {
    background: rgba(17, 24, 39, 0.97);
    color: #d1d5db;
    box-shadow: 0 2px 12px rgba(0,0,0,0.5);
  }
  :global(html.dark) .search-collapsed:hover { background: rgba(30, 58, 95, 0.97); }
  :global(html.dark) .search-input { color: #f3f4f6; }
  :global(html.dark) .search-input::placeholder { color: #4b5563; }
  :global(html.dark) .clear-btn,
  :global(html.dark) .collapse-btn { color: #6b7280; }
  :global(html.dark) .clear-btn:hover,
  :global(html.dark) .collapse-btn:hover { color: #d1d5db; background: rgba(255,255,255,0.08); }
  :global(html.dark) .results { border-color: #374151; }
  :global(html.dark) .result-item { border-color: #1f2937; color: #d1d5db; }
  :global(html.dark) .result-item:hover,
  :global(html.dark) .result-item:focus { background: #1e3a5f; }
  :global(html.dark) .result-name { color: #d1d5db; }
  :global(html.dark) .no-results { color: #4b5563; }
  :global(html.dark) .spinner { border-color: #374151; border-top-color: #3b82f6; }
</style>
