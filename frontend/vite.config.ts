import { fileURLToPath, URL } from 'node:url'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

/**
 * Vite configuration.
 *
 * The dev server proxies `/api`, `/health` and `/openapi.json` to the FastAPI
 * backend. That keeps the browser on a single origin during development, so
 * CORS is not in the loop while you are debugging the app itself. In production
 * the app talks to `VITE_API_BASE_URL` directly and the backend's
 * `CORS_ORIGINS` must include the deployed origin.
 */
export default defineConfig(({ mode }) => {
  const backendTarget = process.env.VITE_DEV_PROXY_TARGET ?? 'http://127.0.0.1:8000'

  return {
    plugins: [react()],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
      },
    },
    server: {
      port: 5173,
      // Fail loudly rather than silently moving to 5174, which would fall
      // outside the backend's default CORS_ORIGINS.
      strictPort: true,
      proxy: {
        '/api': { target: backendTarget, changeOrigin: true },
        '/health': { target: backendTarget, changeOrigin: true },
        '/openapi.json': { target: backendTarget, changeOrigin: true },
      },
    },
    build: {
      outDir: 'dist',
      sourcemap: mode !== 'production',
      rollupOptions: {
        output: {
          // Leaflet and Recharts are large and change rarely; splitting them
          // out keeps the app chunk small across redeploys. Rollup 5 dropped
          // the object form of `manualChunks`, so this is the function form -
          // note that Recharts pulls in the d3-* packages, which belong in the
          // same chunk or they end up duplicated.
          manualChunks(id: string) {
            if (!id.includes('node_modules')) return undefined
            if (/node_modules[\\/](leaflet|leaflet-draw|@?react-leaflet)/.test(id)) {
              return 'leaflet'
            }
            if (/node_modules[\\/](recharts|d3-|internmap|victory-vendor)/.test(id)) {
              return 'charts'
            }
            return undefined
          },
        },
      },
    },
  }
})
