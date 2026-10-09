import { defineConfig } from 'tsup';

// Workspace packages ship TypeScript sources, so they are bundled in; npm deps stay external.
export default defineConfig({
  // The bots think and train in worker threads: their entry files sit next to main.js.
  entry: { main: 'src/main.ts', 'think.worker': 'src/brain/think.worker.ts', 'train.worker': 'src/brain/train.worker.ts' },
  format: ['esm'],
  platform: 'node',
  target: 'node22',
  outDir: 'dist',
  clean: true,
  sourcemap: true,
  noExternal: [/^@arena\//],
});
