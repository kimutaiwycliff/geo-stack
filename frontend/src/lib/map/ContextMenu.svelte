<script lang="ts">
  import { contextMenu } from '$lib/stores/uiStore';

  let copied = false;
  let fetching = false;
  let reverseResult = '';

  // Close when store is cleared externally
  $: if (!$contextMenu) { copied = false; reverseResult = ''; }

  function close(): void { contextMenu.set(null); }

  function onKeyDown(e: KeyboardEvent): void {
    if (e.key === 'Escape') close();
  }

  async function copyCoords(): Promise<void> {
    const cm = $contextMenu;
    if (!cm) return;
    const text = `${cm.lngLat[1].toFixed(6)}, ${cm.lngLat[0].toFixed(6)}`;
    try {
      await navigator.clipboard.writeText(text);
      copied = true;
      setTimeout(() => { copied = false; }, 1800);
    } catch { /* clipboard API may be blocked */ }
  }

  async function whatIsHere(): Promise<void> {
    const cm = $contextMenu;
    if (!cm || fetching) return;
    fetching = true;
    reverseResult = '';
    try {
      const r = await fetch(
        `https://nominatim.openstreetmap.org/reverse?lat=${cm.lngLat[1]}&lon=${cm.lngLat[0]}&format=json`,
        { headers: { 'Accept-Language': 'en' } }
      );
      const data: { display_name?: string } = await r.json();
      if (data.display_name) {
        reverseResult = data.display_name.split(',').slice(0, 3).join(',').trim();
      } else {
        reverseResult = 'Nothing found here';
      }
    } catch {
      reverseResult = 'Lookup failed';
    } finally {
      fetching = false;
    }
  }
</script>

<svelte:window on:keydown={onKeyDown} />

{#if $contextMenu}
  <!-- Transparent backdrop to capture outside clicks -->
  <div class="backdrop" on:click={close} on:contextmenu|preventDefault={close} role="presentation" />

  <div
    class="menu"
    style="left:{$contextMenu.x}px; top:{$contextMenu.y}px"
    role="menu"
  >
    <!-- Coordinate display -->
    <div class="coords">
      {$contextMenu.lngLat[1].toFixed(5)}, {$contextMenu.lngLat[0].toFixed(5)}
    </div>

    <div class="divider" />

    <!-- Copy coordinates -->
    <button class="menu-item" role="menuitem" on:click={copyCoords}>
      {#if copied}
        <svg viewBox="0 0 14 14" width="12" height="12" fill="none" stroke="#22c55e" stroke-width="2" stroke-linecap="round">
          <polyline points="2,7 5.5,11 12,3"/>
        </svg>
        <span>Copied!</span>
      {:else}
        <svg viewBox="0 0 14 14" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
          <rect x="5" y="1" width="8" height="10" rx="1"/>
          <path d="M9 1V0H1a1 1 0 00-1 1v10h2"/>
        </svg>
        <span>Copy coordinates</span>
      {/if}
    </button>

    <!-- What's here -->
    <button class="menu-item" role="menuitem" on:click={whatIsHere} disabled={fetching}>
      {#if fetching}
        <span class="spinner" aria-hidden="true" />
        <span>Looking up…</span>
      {:else}
        <svg viewBox="0 0 14 14" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
          <circle cx="7" cy="5.5" r="4"/>
          <line x1="7" y1="9.5" x2="7" y2="14"/>
        </svg>
        <span>What's here?</span>
      {/if}
    </button>

    {#if reverseResult}
      <div class="reverse-result">{reverseResult}</div>
    {/if}
  </div>
{/if}

<style>
  .backdrop {
    position: fixed;
    inset: 0;
    z-index: 98;
  }

  .menu {
    position: fixed;
    z-index: 99;
    background: rgba(255, 255, 255, 0.98);
    backdrop-filter: blur(8px);
    border-radius: 8px;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.18);
    padding: 6px;
    min-width: 180px;
    font-size: 13px;
    /* Clamp to viewport so it never goes off-screen */
    max-width: calc(100vw - 24px);
  }

  .coords {
    font-size: 11px;
    color: #6b7280;
    padding: 4px 8px 6px;
    font-variant-numeric: tabular-nums;
    letter-spacing: 0.02em;
  }

  .divider {
    height: 1px;
    background: #e5e7eb;
    margin: 2px 0;
  }

  .menu-item {
    display: flex;
    align-items: center;
    gap: 8px;
    width: 100%;
    padding: 7px 8px;
    border: none;
    border-radius: 5px;
    background: none;
    color: #374151;
    cursor: pointer;
    text-align: left;
    font-size: 13px;
    transition: background 0.12s;
  }
  .menu-item:hover:not(:disabled) { background: #f3f4f6; }
  .menu-item:disabled { opacity: 0.5; cursor: default; }

  .reverse-result {
    font-size: 11px;
    color: #374151;
    padding: 4px 8px 2px;
    line-height: 1.4;
    border-top: 1px solid #e5e7eb;
    margin-top: 2px;
  }

  .spinner {
    width: 12px;
    height: 12px;
    border: 2px solid #e5e7eb;
    border-top-color: #2563eb;
    border-radius: 50%;
    animation: spin 0.7s linear infinite;
    flex-shrink: 0;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  /* ── Dark mode (html.dark class) ───────────────────────────────────────── */
  :global(html.dark) .menu {
    background: rgba(17, 24, 39, 0.98);
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.5);
  }
  :global(html.dark) .coords { color: #6b7280; }
  :global(html.dark) .divider { background: #374151; }
  :global(html.dark) .menu-item { color: #e5e7eb; }
  :global(html.dark) .menu-item:hover:not(:disabled) { background: rgba(255,255,255,0.08); }
  :global(html.dark) .reverse-result { color: #d1d5db; border-color: #374151; }
</style>
