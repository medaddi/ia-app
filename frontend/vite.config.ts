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
        // 127.0.0.1, not "localhost": on Windows localhost tries IPv6 (::1) first and adds 0.2 s to every API request
        '/api': { target: env.API_PROXY || 'http://127.0.0.1:8000', changeOrigin: true },
      },
    },
  };
});
