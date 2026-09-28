import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import { existsSync, readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

function iphoneCertificateProfile(): Plugin {
  return {
    name: 'intrac-iphone-certificate-profile',
    configureServer(server) {
      server.middlewares.use((request, response, next) => {
        if (request.url?.split('?')[0] !== '/intrac-local-ca.mobileconfig') return next()
        const path = fileURLToPath(new URL('./public/intrac-local-ca.mobileconfig', import.meta.url))
        if (!existsSync(path)) { response.statusCode = 404; response.end('Run npm run setup:https first.'); return }
        const profile = readFileSync(path)
        response.setHeader('Content-Type', 'application/x-apple-aspen-config')
        response.setHeader('Content-Disposition', 'inline; filename="intrac-local-ca.mobileconfig"')
        response.setHeader('Cache-Control', 'no-store')
        response.setHeader('Content-Length', profile.length)
        response.end(request.method === 'HEAD' ? undefined : profile)
      })
    },
  }
}

export default defineConfig(({ mode }) => {
  const localHttps = mode === 'local-https'
  const certificates = fileURLToPath(new URL('../.local/https/', import.meta.url))
  return {
    plugins: [react(), iphoneCertificateProfile()],
    cacheDir: localHttps ? 'node_modules/.vite-https' : 'node_modules/.vite',
    server: {
      port: localHttps ? 5174 : 5173,
      strictPort: true,
      https: localHttps ? {
        key: readFileSync(`${certificates}server-key.pem`),
        cert: readFileSync(`${certificates}server.pem`),
      } : undefined,
      proxy: { '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: false,
        configure(proxy) {
          // Preserve the browser's scheme for the API's same-origin check.
          proxy.on('proxyReq', request => request.setHeader('X-Forwarded-Proto', localHttps ? 'https' : 'http'))
        },
      } },
    },
    preview: {
      proxy: { '/api': { target: 'http://127.0.0.1:8000', changeOrigin: false, headers: { 'X-Forwarded-Proto': 'http' } } },
    },
  }
})
