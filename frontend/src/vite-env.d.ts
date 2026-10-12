/// <reference types="vite/client" />

/**
 * Typed `import.meta.env` for the variables CropSense reads.
 *
 * Everything here ships to the browser in the built bundle, so nothing secret
 * belongs in these variables. See `frontend/.env.example`.
 */
interface ImportMetaEnv {
  /** Backend origin. Empty in dev, where Vite proxies `/api` and `/health`. */
  readonly VITE_API_BASE_URL?: string
  readonly VITE_DEFAULT_MAP_CENTER_LAT?: string
  readonly VITE_DEFAULT_MAP_CENTER_LNG?: string
  readonly VITE_DEFAULT_MAP_ZOOM?: string
  readonly VITE_REQUEST_TIMEOUT_MS?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
