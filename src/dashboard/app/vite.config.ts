export default defineConfig({
  build: { outDir: '../src/dashboard', emptyOutDir: true },
  server: { port: 5173, proxy: { '/scenario': 'http://localhost:8000', '/recent': 'http://localhost:8000', '/metrics': 'http://localhost:8000' } }
});
