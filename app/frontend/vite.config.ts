import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig(({mode}) => {
  const target = loadEnv(mode, '.', 'VITE_').VITE_API_TARGET || 'http://127.0.0.1:8001';
  return { plugins: [vue()], server: { port: 6173, strictPort: true, proxy: { '/api': target, '/health': target, '/ws': { target: target.replace(/^http/, 'ws'), ws: true } } } };
})
