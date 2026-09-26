import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// In dev (npm run dev), proxy /api to the backend running locally on :8000.
// In docker-compose, nginx (see nginx.conf) handles this proxy instead.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
