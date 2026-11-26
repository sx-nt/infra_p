// Ambiente mínimo de navegador para testar auth.js e api.js no Node.
import { beforeEach, vi } from 'vitest'

class MemoryStorage {
  constructor() { this.items = new Map() }
  getItem(key) { return this.items.has(key) ? this.items.get(key) : null }
  setItem(key, value) { this.items.set(key, String(value)) }
  removeItem(key) { this.items.delete(key) }
}

beforeEach(() => {
  vi.restoreAllMocks()
  vi.stubGlobal('localStorage', new MemoryStorage())
  vi.stubGlobal('sessionStorage', new MemoryStorage())
  vi.stubGlobal('window', {
    location: { search: '', pathname: '/', hash: '', assign: vi.fn(), reload: vi.fn() },
    history: { replaceState: vi.fn() },
  })
})
