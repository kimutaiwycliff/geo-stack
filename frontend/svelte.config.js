import adapter from '@sveltejs/adapter-auto';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/** @type {import('@sveltejs/kit').Config} */
const config = {
	preprocess: vitePreprocess(),
	kit: {
		// adapter-auto selects the right adapter based on the deployment target:
		//   Vercel  → @sveltejs/adapter-vercel  (serverless functions)
		//   Docker  → @sveltejs/adapter-node    (fallback, used locally)
		// No config needed — Vercel injects VERCEL=1 at build time automatically.
		adapter: adapter(),
	},
};

export default config;
