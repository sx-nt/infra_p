import { beforeEach, describe, expect, it, vi } from 'vitest'
import { getIdToken, handleRedirect, loadConfig, login, logout } from './auth.js'

const CONFIG = {
  apiBase: '/api',
  auth: {
    domain: 'https://classly.auth.sa-east-1.amazoncognito.com',
    clientId: 'client-123',
    redirectUri: 'https://classly.test/',
    logoutUri: 'https://classly.test',
    identityProviders: ['COGNITO'],
  },
}

function jsonResponse(body, ok = true) {
  return { ok, json: async () => body, text: async () => JSON.stringify(body) }
}

beforeEach(async () => {
  vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(CONFIG)))
  await loadConfig()
})

describe('login', () => {
  it('redireciona ao Cognito com PKCE S256 e guarda o verificador', async () => {
    await login()
    const url = new URL(window.location.assign.mock.calls[0][0])
    expect(url.origin + url.pathname).toBe(`${CONFIG.auth.domain}/oauth2/authorize`)
    expect(url.searchParams.get('client_id')).toBe('client-123')
    expect(url.searchParams.get('code_challenge_method')).toBe('S256')
    expect(url.searchParams.get('lang')).toBe('pt-BR')
    const pkce = JSON.parse(sessionStorage.getItem('classly.pkce'))
    expect(url.searchParams.get('state')).toBe(pkce.state)

    // O desafio enviado é o SHA-256 do verificador guardado.
    const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(pkce.verifier))
    const expected = btoa(String.fromCharCode(...new Uint8Array(digest)))
      .replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
    expect(url.searchParams.get('code_challenge')).toBe(expected)
  })

  it('pode ir direto para o Google', async () => {
    await login('Google')
    expect(window.location.assign.mock.calls[0][0]).toContain('identity_provider=Google')
  })
})

describe('handleRedirect', () => {
  it('não faz nada sem código na URL', async () => {
    await handleRedirect()
    expect(fetch).toHaveBeenCalledTimes(1)
  })

  it('recusa um state diferente do enviado', async () => {
    sessionStorage.setItem('classly.pkce', JSON.stringify({ verifier: 'v', state: 'certo' }))
    window.location.search = '?code=abc&state=forjado'
    await expect(handleRedirect()).rejects.toThrow('Sessão de login inválida')
  })

  it('troca o código por tokens e limpa a URL', async () => {
    sessionStorage.setItem('classly.pkce', JSON.stringify({ verifier: 'v', state: 's' }))
    window.location.search = '?code=abc&state=s'
    fetch.mockResolvedValueOnce(jsonResponse({ id_token: 'id-1', refresh_token: 'r-1', expires_in: 3600 }))

    await handleRedirect()

    const [url, request] = fetch.mock.calls[1]
    expect(url).toBe(`${CONFIG.auth.domain}/oauth2/token`)
    const form = new URLSearchParams(request.body)
    expect(form.get('grant_type')).toBe('authorization_code')
    expect(form.get('code_verifier')).toBe('v')
    expect(window.history.replaceState).toHaveBeenCalled()
    expect(await getIdToken()).toBe('id-1')
  })

  it('mostra o erro devolvido pelo Cognito', async () => {
    window.location.search = '?error=access_denied&error_description=Usuario+cancelou'
    await expect(handleRedirect()).rejects.toThrow('Usuario cancelou')
  })
})

describe('getIdToken', () => {
  it('renova o token expirado com o refresh token', async () => {
    localStorage.setItem('classly.tokens', JSON.stringify({ idToken: 'velho', refreshToken: 'r-1', expiresAt: Date.now() - 1 }))
    fetch.mockResolvedValueOnce(jsonResponse({ id_token: 'novo', expires_in: 3600 }))
    expect(await getIdToken()).toBe('novo')
    expect(JSON.parse(localStorage.getItem('classly.tokens')).refreshToken).toBe('r-1')
  })

  it('descarta a sessão quando a renovação falha', async () => {
    localStorage.setItem('classly.tokens', JSON.stringify({ idToken: 'velho', refreshToken: 'r-1', expiresAt: 0 }))
    fetch.mockResolvedValueOnce(jsonResponse({}, false))
    expect(await getIdToken()).toBeNull()
    expect(localStorage.getItem('classly.tokens')).toBeNull()
  })
})

it('logout limpa a sessão e sai pelo Cognito', () => {
  localStorage.setItem('classly.tokens', '{}')
  logout()
  expect(localStorage.getItem('classly.tokens')).toBeNull()
  expect(window.location.assign.mock.calls[0][0]).toBe(
    `${CONFIG.auth.domain}/logout?client_id=client-123&logout_uri=https%3A%2F%2Fclassly.test`,
  )
})
