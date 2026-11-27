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
  IN_REVIEW: 'Em validação',
  APPROVED: 'Aprovada',
  PUBLISHED: 'Publicada',
  ARCHIVED: 'Arquivada',
}

export const AUDIT_ACTION_NAME = {
  LOGIN: 'Login',
  USER_CREATED: 'Primeiro acesso',
  ROLE_ASSIGNED: 'Perfil atribuído automaticamente',
  ROLE_CHANGED: 'Perfil alterado',
  CREATE: 'Cadastro',
  UPDATE: 'Alteração',
  DELETE: 'Exclusão',
  CALENDAR_SYNC: 'Importação do Google Calendar',
  SCHEDULE_IN_REVIEW: 'Grade enviada para validação',
  SCHEDULE_APPROVED: 'Grade aprovada',
  SCHEDULE_DRAFT: 'Grade devolvida para rascunho',
  SCHEDULE_PUBLISHED: 'Grade publicada',
  SCHEDULE_ARCHIVED: 'Grade arquivada',
  NOTIFICATION_SENT: 'E-mails de publicação enviados',
  NOTIFICATION_RESENT: 'E-mails reenviados',
}

export const ENTITY_NAME = {
  teachers: 'Professor',
  subjects: 'Disciplina',
  classes: 'Turma',
  qualifications: 'Habilitação',
  availability: 'Disponibilidade',
  schedule: 'Grade',
  user: 'Usuário',
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
