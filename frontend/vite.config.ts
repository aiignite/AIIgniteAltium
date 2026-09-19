import path from 'path';
import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

// 与 AIDriveEDA 相同的子路径模式：门户经 /altium/ 反代本服务
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const base = env.VITE_BASE_PATH || '/';
  const apiPrefix = base === '/' ? '/api' : `${base.replace(/\/$/, '')}/api`;

  return {
    base,
    server: {
      port: 3340,
      host: '0.0.0.0',
      proxy: {
        [apiPrefix]: {
          target: 'http://localhost:3345',
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
