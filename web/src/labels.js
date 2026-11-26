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

// Duração em horas entre dois horários HH:MM (zero se o fim não for posterior).
export function hours(start, end) {
  const [sh, sm] = start.split(':').map(Number)
  const [eh, em] = end.split(':').map(Number)
  return Math.max(0, (eh * 60 + em - sh * 60 - sm) / 60)
}
