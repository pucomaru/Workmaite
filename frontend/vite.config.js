import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
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
