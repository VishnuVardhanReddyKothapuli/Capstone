import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The API is called with relative paths (/api/...) in both dev and production:
// in dev this proxy forwards them to uvicorn, in production FastAPI serves the
// built bundle itself. Either way the app only ever talks to its own origin.
const BACKEND = 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: BACKEND, changeOrigin: true },
      '/health': { target: BACKEND, changeOrigin: true },
      '/docs': { target: BACKEND, changeOrigin: true },
      '/openapi.json': { target: BACKEND, changeOrigin: true },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
  },
})
