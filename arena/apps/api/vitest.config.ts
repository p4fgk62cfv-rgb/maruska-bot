import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    // The suites share one test database (and the owner's welcome-gift setting in it): run files one by one.
    fileParallelism: false,
  },
});
