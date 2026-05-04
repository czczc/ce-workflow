/// <reference types="vitest" />
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vuetify from 'vite-plugin-vuetify'

export default defineConfig({
  test: {
    environment: 'node',
  },
  plugins: [
    vue(),
    vuetify({ autoImport: true }),
  ],
  server: {
    proxy: {
      '/chat': {
        target: 'http://127.0.0.1:8000',
        bypass: (req) => req.headers.accept?.includes('text/html') ? '/index.html' : null,
      },
      '/documents': {
        target: 'http://127.0.0.1:8000',
        bypass: (req) => req.headers.accept?.includes('text/html') ? '/index.html' : null,
      },
      '/qc': 'http://127.0.0.1:8000',
      '/reports': {
        target: 'http://127.0.0.1:8000',
        bypass: (req) => req.headers.accept?.includes('text/html') ? '/index.html' : null,
      },
    },
  },
})
