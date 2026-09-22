import path from 'path';
import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const base = env.VITE_BASE_PATH || '/';
  const apiPrefix = base === '/' ? '/api' : `${base.replace(/\/$/, '')}/api`;

  return {
    base,
    server: {
      port: 3290,
      host: '0.0.0.0',
      proxy: {
        [apiPrefix]: {
          target: 'http://127.0.0.1:3295',
          changeOrigin: true,
          timeout: 600_000,
          rewrite: (p) =>
            base === '/' ? p : p.replace(new RegExp(`^${base.replace(/\/$/, '')}`), ''),
        },
      },
    },
    plugins: [react()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, 'src'),
      },
    },
  };
});
