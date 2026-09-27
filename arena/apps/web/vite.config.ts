import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [react()],
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
