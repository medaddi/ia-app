import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import { defineConfig, loadEnv } from 'vite';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, __dirname, '');
  return {
    base: '/',
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, 'src'),
      },
    },
    build: {
      rollupOptions: {
        output: {
          // Libraries in their own long-cached files: an app update only re-downloads the app's code
          manualChunks: {
            react: ['react', 'react-dom'],
            motion: ['motion/react'],
            charts: ['lightweight-charts'],
          },
        },
      },
    },
    server: {
      // In development the Python API runs on :8000 (backend/); /api is proxied so no CORS setup is needed
      proxy: {
        '/api': { target: env.API_PROXY || 'http://localhost:8000', changeOrigin: true },
      },
    },
  };
});
