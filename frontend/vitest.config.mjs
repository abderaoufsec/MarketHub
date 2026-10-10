import path from 'path'
import { defineConfig, transformWithEsbuild } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [
    // Next.js compiles JSX in `.js` files; Vite does not by default. This
    // plugin gives src/**/*.js the same treatment so unit tests can import
    // components and contexts without renaming every source file.
    {
      name: 'treat-src-js-as-jsx',
      async transform(code, id) {
        if (!id.match(/src[\\/].*\.js$/)) return null
        return transformWithEsbuild(code, id, {
          loader: 'jsx',
          jsx: 'automatic',
        })
      },
    },
    react(),
  ],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.js'],
    include: ['src/**/*.test.{js,jsx}'],
    exclude: ['node_modules', '.next', 'e2e'],
    // env.js validates NEXT_PUBLIC_API_URL at import time (Phase 2); give the
    // unit tests a deterministic value instead of relying on .env.local.
    env: {
      NEXT_PUBLIC_API_URL: 'http://api.test/api',
    },
    coverage: {
      provider: 'v8',
      reporter: ['text', 'lcov'],
      include: ['src/lib/**', 'src/context/**', 'src/components/**'],
      exclude: ['**/*.test.*', 'src/test/**'],
    },
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
})
