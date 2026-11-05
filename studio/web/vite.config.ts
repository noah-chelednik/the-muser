import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Dev server proxies the Python API (python -m studio.server, port 8765).
const isolation = { 'Cross-Origin-Opener-Policy': 'same-origin', 'Cross-Origin-Embedder-Policy': 'require-corp' }

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    headers: isolation,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8765', changeOrigin: true },
      '/files': { target: 'http://127.0.0.1:8765', changeOrigin: true },
    },
  },
  preview: { headers: isolation },
  build: { outDir: 'dist', chunkSizeWarningLimit: 900 },
})
