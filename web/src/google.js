// Autorização de leitura do Google Calendar com o Google Identity Services.
// O token obtido é enviado uma vez ao backend, que consulta a agenda.

const SCRIPT_URL = 'https://accounts.google.com/gsi/client'
const SCOPE = 'https://www.googleapis.com/auth/calendar.readonly'

let loading = null

function loadScript() {
  if (window.google?.accounts?.oauth2) return Promise.resolve()
  loading ||= new Promise((resolve, reject) => {
    const script = document.createElement('script')
    script.src = SCRIPT_URL
    script.async = true
    script.onload = resolve
    script.onerror = () => {
      loading = null
      reject(new Error('Não foi possível carregar o login do Google.'))
    }
    document.head.appendChild(script)
  })
  return loading
}

export async function requestCalendarToken(clientId) {
  await loadScript()
  return new Promise((resolve, reject) => {
    const client = window.google.accounts.oauth2.initTokenClient({
      client_id: clientId,
      scope: SCOPE,
      callback: (response) =>
        response.error
          ? reject(new Error('A leitura da agenda não foi autorizada.'))
          : resolve(response.access_token),
      error_callback: () => reject(new Error('A autorização do Google foi cancelada.')),
    })
    client.requestAccessToken()
  })
}
