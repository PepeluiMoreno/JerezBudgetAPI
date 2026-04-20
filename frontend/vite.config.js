import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    host: '0.0.0.0',
    port: 8080,
    allowedHosts: true,
    proxy: {
      // En dev: apunta a localhost (la API está expuesta en :8015)
      // En producción (Docker): nginx hace el proxy a api:8015
      '/graphql': process.env.VITE_API_PROXY || 'http://localhost:8015',
      '/health':  process.env.VITE_API_PROXY || 'http://localhost:8015',
      '/api':     process.env.VITE_API_PROXY || 'http://localhost:8015',
    }
  }
})
