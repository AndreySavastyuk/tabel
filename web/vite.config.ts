import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dev-сервер на 5173 проксирует /api -> бэкенд FastAPI (8000), снимая /api.
// В проде фронт собирается в статику и раздаётся тем же сервером/прокси.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ''),
      },
    },
  },
})
