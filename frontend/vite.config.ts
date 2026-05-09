import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  optimizeDeps: {
    // Transformers.js uses WASM + dynamic imports that break Vite's pre-bundler
    exclude: ['@huggingface/transformers'],
  },
})
