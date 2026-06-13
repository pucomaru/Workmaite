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
    // dev 프록시는 프로덕션 Ingress(k8s/ingress.yaml)와 일치시킬 것:
    //   /api/v1 → SpringBoot(8080), 그 외 /api/* (ai·agent·neo4j·chats·stt·upload·usage) → FastAPI(8000)
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
