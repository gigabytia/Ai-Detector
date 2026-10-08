/// <reference types="vitest/config" />
import { fileURLToPath, URL } from 'node:url'

import tailwindcss from '@tailwindcss/vite'
import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

const apiTarget = process.env.VITE_API_PROXY_TARGET ?? 'http://127.0.0.1:8000'
const workerTarget = process.env.VITE_WORKER_PROXY_TARGET ?? 'http://127.0.0.1:8001'

export default defineConfig({
  plugins: [vue(), tailwindcss()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    // Same-origin paths as in the docker nginx config (docs/data-flow.md §5).
    proxy: {
      '/api': apiTarget,
      '/health': apiTarget,
      '/live': { target: workerTarget, ws: true, rewrite: (path) => path.replace(/^\/live/, '') },
    },
  },
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.ts'],
  },
})
