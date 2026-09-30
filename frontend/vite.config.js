import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
      '/journeys': 'http://localhost:8000',
      '/signals': 'http://localhost:8000',
      '/emergencies': 'http://localhost:8000',
      '/internal': 'http://localhost:8000',
      '/settings': 'http://localhost:8000',
    },
  },
})
