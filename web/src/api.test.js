import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, api } from './api.js'
import { loadConfig } from './auth.js'

function response(status, body) {
  return { ok: status < 400, status, json: async () => body, text: async () => (body === undefined ? '' : JSON.stringify(body)) }
}

describe('api (desenvolvimento local, sem Cognito)', () => {
  beforeEach(async () => {
    vi.stubGlobal('fetch', vi.fn(async () => response(200, { apiBase: '/api', auth: null })))
    await loadConfig()
  })

  it('envia JSON para a rota com o prefixo /api', async () => {
    fetch.mockResolvedValueOnce(response(201, { teacherId: 't1' }))
    expect(await api('/teachers', { method: 'POST', body: { name: 'Ana' } })).toEqual({ teacherId: 't1' })
    const [url, request] = fetch.mock.calls[1]
    expect(url).toBe('/api/teachers')
    expect(request.headers).toEqual({ 'Content-Type': 'application/json' })
    expect(request.body).toBe('{"name":"Ana"}')
  })

  it('aceita respostas sem corpo (204)', async () => {
    fetch.mockResolvedValueOnce(response(204))
    expect(await api('/teachers/t1', { method: 'DELETE' })).toBeNull()
  })

  it('transforma erros da API em ApiError com a mensagem e os conflitos', async () => {
    fetch.mockResolvedValueOnce(response(422, { message: 'A grade contém conflitos.', errors: [{ reason: 'x' }] }))
    const error = await api('/schedules', { method: 'POST', body: {} }).catch((e) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect(error.status).toBe(422)
    expect(error.message).toBe('A grade contém conflitos.')
    expect(error.errors).toEqual([{ reason: 'x' }])
  })
})

describe('api (nuvem, com Cognito)', () => {
  beforeEach(async () => {
    vi.stubGlobal('fetch', vi.fn(async () => response(200, { apiBase: '/api', auth: { domain: 'https://x', clientId: 'c' } })))
    await loadConfig()
  })

  it('envia o ID token no cabeçalho Authorization', async () => {
    localStorage.setItem('classly.tokens', JSON.stringify({ idToken: 'id-1', expiresAt: Date.now() + 3600_000 }))
    fetch.mockResolvedValueOnce(response(200, []))
    await api('/teachers')
    expect(fetch.mock.calls[1][1].headers.Authorization).toBe('Bearer id-1')
  })

  it('explica a sessão expirada quando o API Gateway responde 401', async () => {
    fetch.mockResolvedValueOnce({ ok: false, status: 401, text: async () => '{"message":"Unauthorized"}' })
    await expect(api('/teachers')).rejects.toThrow('Sua sessão expirou. Entre novamente.')
  })
})
