import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [sveltekit()],
	server: {
		host: '0.0.0.0',
		port: 5173,
		// Proxy API calls in dev so the browser doesn't need to know the API URL
		// Proxy /api to FastAPI. Inside Docker, use the service name; outside use localhost.
		proxy: {
			'/api': {
				target: process.env.VITE_API_PROXY_TARGET || process.env.PUBLIC_API_URL || 'http://localhost:8000',
				rewrite: (path) => path.replace(/^\/api/, ''),
				changeOrigin: true,
			},
		},
	},
	optimizeDeps: {
		// pmtiles uses browser APIs — pre-bundle to avoid reload issues in dev
		include: ['maplibre-gl', 'pmtiles'],
	},
});
