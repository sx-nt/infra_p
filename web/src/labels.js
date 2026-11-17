export const DAYS = [
  ['MON', 'Segunda'],
  ['TUE', 'Terça'],
  ['WED', 'Quarta'],
  ['THU', 'Quinta'],
  ['FRI', 'Sexta'],
  ['SAT', 'Sábado'],
  ['SUN', 'Domingo'],
]
export const DAY_NAME = Object.fromEntries(DAYS)

export const ROLE_NAME = {
  COORDINATOR: 'Coordenação',
  TEACHER: 'Professor',
  PENDING: 'Aguardando liberação',
}

export const STATUS_NAME = {
  DRAFT: 'Rascunho',
  PUBLISHED: 'Publicada',
  ARCHIVED: 'Arquivada',
}

export function byId(items, key) {
  return Object.fromEntries(items.map((item) => [item[key], item]))
}

export function formatDate(value) {
  return value ? new Date(value).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' }) : '—'
}
