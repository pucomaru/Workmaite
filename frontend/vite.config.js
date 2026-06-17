import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  build: {
    // 무거운 단일 라이브러리(PIXI·TipTap)를 페이지 청크에서 분리해 별도 vendor 청크로 묶는다.
    // 총 바이트는 동일하지만 페이지 코드 변경 시 재다운로드를 막아 캐시 적중률을 크게 높인다.
    chunkSizeWarningLimit: 700,
    rollupOptions: {
      output: {
        // rolldown 기반 Vite는 manualChunks를 함수 형태로만 받는다.
        manualChunks(id) {
          if (!id.includes('node_modules')) return
          if (id.includes('pixi.js')) return 'pixi'
          if (id.includes('@tiptap') || id.includes('prosemirror')) return 'tiptap'
        },
      },
    },
  },
  // 컴포넌트 마운트 테스트(@vue/test-utils)를 위해 jsdom 환경 사용.
  // 순수 모듈 테스트도 jsdom에서 그대로 통과한다.
  test: {
    environment: 'jsdom',
  },
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
      // FastAPI WebSocket 엔드포인트(/ws/sessions/{id}/transcribe, /ws/meetings/{id}/agenda).
      '/ws': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        ws: true,
      },
    },
  },
})
