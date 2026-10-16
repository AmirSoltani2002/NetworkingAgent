import { fileURLToPath, URL } from 'node:url';
import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

const proxy = { '/api/factory/ws': { target: `ws://127.0.0.1:${process.env.CORE_PORT ?? 8000}`, ws: true }, '/api': { target: `http://127.0.0.1:${process.env.CORE_PORT ?? 8000}` } };

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  server: { host: '127.0.0.1', port: 8080, strictPort: true, proxy },
  preview: { host: '127.0.0.1', port: 8080, strictPort: true, proxy },
});
