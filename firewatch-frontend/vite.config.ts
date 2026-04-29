import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    // '@/' maps to 'src/' -- allows imports like: import { Button } from '@/components/ui/button'
    // instead of: import { Button } from '../../components/ui/button'
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 3000,
    // Proxy: in development, requests to /api/... are forwarded to the FastAPI backend.
    // The browser sees localhost:3000 for everything, so there are no CORS issues
    // and cookies are set on the same origin.
    proxy: {
      '/api': {
        // In Docker, VITE_BACKEND_PROXY_TARGET is set to http://backend:8000 via
        // docker-compose.yml so the Vite server can reach the backend container.
        // Locally without Docker it falls back to the usual localhost address.
        target: process.env.VITE_BACKEND_PROXY_TARGET ?? 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
