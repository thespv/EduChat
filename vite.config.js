import { defineConfig, loadEnv } from 'vite';
import { resolve } from 'path';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  let apiUrl = env.VITE_API_URL || '';
  if (!apiUrl || apiUrl === 'http://localhost:8000') {
    apiUrl = '';
  }
  
  return {
    root: '.',
    publicDir: 'public',
    build: {
      outDir: 'dist',
      emptyOutDir: true,
      rollupOptions: {
        input: {
          main: resolve(__dirname, 'index.html'),
          chat: resolve(__dirname, 'chat.html')
        }
      }
    },
    server: {
      port: 5173,
      open: true
    },
    define: {
      'import.meta.env.VITE_API_URL': JSON.stringify(apiUrl)
    }
  };
});