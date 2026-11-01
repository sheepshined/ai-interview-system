import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

const backendTarget = process.env.VITE_BACKEND_TARGET || 'http://127.0.0.1:8000'
const websocketTarget = backendTarget.replace(/^http/, 'ws')

// 新前端 (墨卷档案) dev server: 3001, 与旧前端 3000 并存
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 3001,
    proxy: {
      '/api': { target: backendTarget, changeOrigin: true },
      '/ws': { target: websocketTarget, ws: true },
      '/kb_files': { target: backendTarget, changeOrigin: true },
    },
  },
})