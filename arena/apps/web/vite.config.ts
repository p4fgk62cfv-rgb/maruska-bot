import react from '@vitejs/plugin-react';
import { readFileSync } from 'node:fs';
import { defineConfig } from 'vite';

const pkg = JSON.parse(readFileSync(new URL('./package.json', import.meta.url), 'utf8')) as { version: string };
const built = new Date().toISOString().slice(0, 10);

export default defineConfig({
  plugins: [react()],
  define: { __APP_VERSION__: JSON.stringify(`${pkg.version} (${built})`) },
  server: {
    host: true,
    port: 5173,
    proxy: {
      '/api': process.env.ARENA_API ?? 'http://localhost:8080',
      '/ws': { target: (process.env.ARENA_API ?? 'http://localhost:8080').replace('http', 'ws'), ws: true },
    },
  },
  build: {
    target: 'es2020',
    cssCodeSplit: true,
    rollupOptions: {
      output: {
        // React rarely changes: a separate chunk stays cached across app releases.
        manualChunks: (id) => (/node_modules\/(react|react-dom|scheduler)\//.test(id) ? 'react' : undefined),
      },
    },
  },
});
