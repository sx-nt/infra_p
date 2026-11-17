import { getConfig, getIdToken } from './auth.js'

export class ApiError extends Error {
  constructor(status, message, errors) {
    super(message)
    this.status = status
    this.errors = errors || []
  }
}

export async function api(path, { method = 'GET', body } = {}) {
  const headers = {}
  const token = await getIdToken()
  if (token) headers.Authorization = `Bearer ${token}`
  if (body !== undefined) headers['Content-Type'] = 'application/json'

  const response = await fetch(`${getConfig().apiBase}${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const text = await response.text()
  let data = null
  try {
    data = text ? JSON.parse(text) : null
  } catch {
    data = null
  }
  if (!response.ok) {
    const fallback = response.status === 401 ? 'Sua sessão expirou. Entre novamente.' : `Erro ${response.status}`
    throw new ApiError(response.status, data?.message || fallback, data?.errors)
  }
  return data
}
