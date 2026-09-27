import { defineConfig } from 'tsup';

// Workspace packages ship TypeScript sources, so they are bundled in; npm deps stay external.
export default defineConfig({
  entry: ['src/main.ts'],
  format: ['esm'],
  platform: 'node',
  target: 'node22',
  outDir: 'dist',
  clean: true,
  sourcemap: true,
  noExternal: [/^@arena\//],
});
