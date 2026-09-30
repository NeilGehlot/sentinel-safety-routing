import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'node:path'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': path.resolve(__dirname, './src') } },
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
      '/v1': 'http://127.0.0.1:8741',
      '/journeys': 'http://localhost:8000',
      '/signals': 'http://localhost:8000',
      '/emergencies': 'http://localhost:8000',
      '/internal': 'http://localhost:8000',
      '/settings': 'http://localhost:8000',
    },
  },
})
