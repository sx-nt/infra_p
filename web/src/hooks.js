import { useCallback, useEffect, useState } from 'react'
import { api } from './api.js'

// Carrega uma ou mais rotas da API e expõe recarga, carregamento e erro.
export function useResources(paths) {
  const key = paths.join('|')
  const [data, setData] = useState(null)
  const [error, setError] = useState('')

  const reload = useCallback(async () => {
    try {
      const results = await Promise.all((key ? key.split('|') : []).map((path) => api(path)))
      setData(results)
      setError('')
    } catch (err) {
      setError(err.message)
    }
  }, [key])

  useEffect(() => {
    reload()
  }, [reload])

  return { data, error, reload }
}
