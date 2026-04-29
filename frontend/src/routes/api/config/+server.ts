/**
 * GET /api/config — serve runtime config to the browser.
 *
 * SvelteKit's $env/static/public variables are baked in at build time.
 * This endpoint lets the browser fetch the CURRENT values at runtime,
 * which is critical in Docker environments where the same image
 * runs in local, cloud, and production with different API URLs.
 *
 * The browser stores this in window.__GEO_CONFIG__ (set in +page.svelte).
 */

import { env } from '$env/dynamic/public';
import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';

export const GET: RequestHandler = () => {
  return json({
    apiUrl: env.PUBLIC_API_URL ?? 'http://localhost:8000',
    martinUrl: env.PUBLIC_MARTIN_URL ?? 'http://localhost:3000',
    titilerUrl: env.PUBLIC_TITILER_URL ?? 'http://localhost:8080',
  });
};
