import adapter from '@sveltejs/adapter-auto';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/** @type {import('@sveltejs/kit').Config} */
const config = {
	preprocess: vitePreprocess(),
	kit: {
		adapter: adapter({
			// adapter-vercel doesn't support Node 24 yet. Pin to Node 20 LTS.
			// Ignored by adapter-node (local Docker), only used on Vercel.
			runtime: 'nodejs20.x',
		}),
	},
};

export default config;
