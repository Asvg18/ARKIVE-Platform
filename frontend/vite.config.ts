// vitest's defineConfig, not vite's — it is the one that knows about the
// `test` key. Importing vite's makes `tsc -b` reject this file.
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    // Bind-mounted source does not deliver inotify events through Docker
    // Desktop — on Windows especially — so the default watcher never
    // fires and hot reload silently does nothing while the server itself
    // looks perfectly healthy. Polling fixes it but costs CPU, so it is
    // opt-in: only the dev container sets VITE_USE_POLLING, and a native
    // `npm run dev` keeps the efficient native watcher.
    watch:
      process.env.VITE_USE_POLLING === 'true'
        ? { usePolling: true, interval: 300 }
        : undefined,
  },
  test: {
    // jsdom, not node: client.ts reaches for localStorage and
    // window.dispatchEvent, and decodeJwt uses atob. Testing those with
    // hand-rolled globals would be testing the stubs, not the code.
    environment: 'jsdom',
    include: ['src/**/*.test.ts', 'src/**/*.test.tsx'],
  },
})
