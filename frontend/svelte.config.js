import adapterNode from '@sveltejs/adapter-node';
import adapterVercel from '@sveltejs/adapter-vercel';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

// Vercel sets VERCEL=1 automatically at build time.
// Locally and in Docker it is unset, so adapter-node is used.
const isVercel = !!process.env.VERCEL;

/** @type {import('@sveltejs/kit').Config} */
const config = {
	preprocess: vitePreprocess(),
	kit: {
		adapter: isVercel
			? adapterVercel({ runtime: 'nodejs20.x' })
			: adapterNode({ out: 'build', precompress: true }),
	},
};

export default config;
