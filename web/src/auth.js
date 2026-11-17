// Login pelo Amazon Cognito (managed login) com authorization code + PKCE.
// A configuração vem de /config.json, gerado pelo Pulumi a cada implantação.

const TOKENS_KEY = 'classly.tokens'
const PKCE_KEY = 'classly.pkce'

let config = null

export async function loadConfig() {
  const response = await fetch('/config.json', { cache: 'no-store' })
  if (!response.ok) throw new Error('Não foi possível carregar a configuração da aplicação.')
  config = await response.json()
  return config
}

export function getConfig() {
  return config
}

function base64Url(bytes) {
  return btoa(String.fromCharCode(...new Uint8Array(bytes)))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '')
}

function readTokens() {
  try {
    return JSON.parse(localStorage.getItem(TOKENS_KEY))
  } catch {
    return null
  }
}

function storeTokens(data, previousRefreshToken) {
  const tokens = {
    idToken: data.id_token,
    refreshToken: data.refresh_token || previousRefreshToken,
    expiresAt: Date.now() + data.expires_in * 1000,
  }
  localStorage.setItem(TOKENS_KEY, JSON.stringify(tokens))
  return tokens
}

async function requestToken(params) {
  const response = await fetch(`${config.auth.domain}/oauth2/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ client_id: config.auth.clientId, ...params }),
  })
  if (!response.ok) throw new Error('O provedor de autenticação recusou a sessão.')
  return response.json()
}

export async function login(identityProvider) {
  const verifier = base64Url(crypto.getRandomValues(new Uint8Array(32)))
  const state = base64Url(crypto.getRandomValues(new Uint8Array(16)))
  sessionStorage.setItem(PKCE_KEY, JSON.stringify({ verifier, state }))
  const challenge = base64Url(
    await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier)),
  )
  const params = new URLSearchParams({
    response_type: 'code',
    client_id: config.auth.clientId,
    redirect_uri: config.auth.redirectUri,
    scope: 'openid email profile',
    state,
    code_challenge: challenge,
    code_challenge_method: 'S256',
    lang: 'pt-BR',
  })
  if (identityProvider) params.set('identity_provider', identityProvider)
  window.location.assign(`${config.auth.domain}/oauth2/authorize?${params}`)
}

// Conclui o login quando o Cognito redireciona de volta com ?code=...
export async function handleRedirect() {
  const params = new URLSearchParams(window.location.search)
  const code = params.get('code')
  const error = params.get('error_description') || params.get('error')
  if (!code && !error) return
  window.history.replaceState(null, '', window.location.pathname + window.location.hash)
  if (error) throw new Error(`Falha no login: ${error}`)

  const pkce = JSON.parse(sessionStorage.getItem(PKCE_KEY) || 'null')
  sessionStorage.removeItem(PKCE_KEY)
  if (!pkce || pkce.state !== params.get('state')) {
    throw new Error('Sessão de login inválida. Tente entrar novamente.')
  }
  storeTokens(
    await requestToken({
      grant_type: 'authorization_code',
      code,
      redirect_uri: config.auth.redirectUri,
      code_verifier: pkce.verifier,
    }),
  )
}

export async function getIdToken() {
  if (!config?.auth) return null
  const tokens = readTokens()
  if (!tokens) return null
  if (tokens.expiresAt - 60_000 > Date.now()) return tokens.idToken
  if (!tokens.refreshToken) return null
  try {
    const data = await requestToken({ grant_type: 'refresh_token', refresh_token: tokens.refreshToken })
    return storeTokens(data, tokens.refreshToken).idToken
  } catch {
    localStorage.removeItem(TOKENS_KEY)
    return null
  }
}

export function logout() {
  localStorage.removeItem(TOKENS_KEY)
  if (!config?.auth) return window.location.reload()
  const params = new URLSearchParams({
    client_id: config.auth.clientId,
    logout_uri: config.auth.logoutUri,
  })
  window.location.assign(`${config.auth.domain}/logout?${params}`)
}
