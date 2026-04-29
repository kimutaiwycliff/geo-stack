import adapter from '@sveltejs/adapter-node';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/** @type {import('@sveltejs/kit').Config} */
const config = {
	preprocess: vitePreprocess(),
	kit: {
		adapter: adapter({
			// Node adapter: SvelteKit runs as a Node.js server behind Caddy in production.
			// Output goes to build/ — that's what the frontend Docker image runs.
			out: 'build',
			precompress: true,
		}),
	},
};

export default config;
