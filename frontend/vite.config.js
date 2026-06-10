import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    proxy: {
      '/api/v1': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        ws: true,
      },
      '/wlk': {
        target: 'https://workmaite.project.skala-ai.com',
        changeOrigin: true,
        ws: true,
      },
      // LiveKit 신호 서버 프록시 (CORS 우회)
      '/livekit-signal': {
        target: 'http://localhost:7880',
        changeOrigin: true,
        rewrite: path => path.replace(/^\/livekit-signal/, ''),
        ws: true,
      },
    },
  },
})
