import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// In development, API calls go to the FastAPI server on :8000.
// In production, FastAPI serves the built files itself (frontend/dist).
export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': 'http://127.0.0.1:8000' } },
})
