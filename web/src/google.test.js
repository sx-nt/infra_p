import { describe, expect, it, vi } from 'vitest'
import { requestCalendarToken } from './google.js'

function stubGoogle(response) {
  const initTokenClient = vi.fn((options) => ({
    requestAccessToken: () => options.callback(response),
  }))
  window.google = { accounts: { oauth2: { initTokenClient } } }
  return initTokenClient
}

describe('requestCalendarToken', () => {
  it('pede só leitura da agenda e devolve o token', async () => {
    const init = stubGoogle({ access_token: 'ya29.token' })
    await expect(requestCalendarToken('client.apps.googleusercontent.com')).resolves.toBe('ya29.token')
    expect(init.mock.calls[0][0]).toMatchObject({
      client_id: 'client.apps.googleusercontent.com',
      scope: 'https://www.googleapis.com/auth/calendar.readonly',
    })
  })

  it('explica quando o usuário não autoriza', async () => {
    stubGoogle({ error: 'access_denied' })
    await expect(requestCalendarToken('c')).rejects.toThrow('não foi autorizada')
  })
})
