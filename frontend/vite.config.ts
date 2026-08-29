import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Keep browser API calls same-origin so development works through WSL,
    // containers, and LAN addresses—not only localhost.
    proxy: {
      '/api': {
        target: `http://127.0.0.1:${process.env.VITE_BACKEND_PORT ?? '8000'}`,
        changeOrigin: true,
      },
    },
  },
})
