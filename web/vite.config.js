import { readFileSync } from 'node:fs'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const OPENAPI = new URL('../docs/openapi.yaml', import.meta.url)

// Publica a documentação OpenAPI (docs/openapi.yaml) em /api-docs/openapi.yaml,
// lida pela página Swagger em public/api-docs/index.html.
function openApiSpec() {
  return {
    name: 'classly-openapi',
    configureServer(server) {
      server.middlewares.use('/api-docs/openapi.yaml', (req, res) => {
        res.setHeader('Content-Type', 'application/yaml')
        res.end(readFileSync(OPENAPI))
      })
    },
    generateBundle() {
      this.emitFile({ type: 'asset', fileName: 'api-docs/openapi.yaml', source: readFileSync(OPENAPI, 'utf8') })
    },
  }
}

// Em desenvolvimento, /api é encaminhado ao SAM local (make -C ../aws-sam dev),
// reproduzindo o comportamento do CloudFront na nuvem.
export default defineConfig({
  plugins: [react(), openApiSpec()],
  server: {
    proxy: {
      '^/api(/|$)': {
        target: 'http://127.0.0.1:3000',
        rewrite: (path) => path.replace(/^\/api(?=\/|$)/, ''),
      },
    },
  },
})
