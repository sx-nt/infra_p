import { describe, expect, it } from 'vitest'
import { byId, hours } from './labels.js'

describe('hours', () => {
  it('calcula a duração de uma aula', () => {
    expect(hours('08:00', '10:00')).toBe(2)
    expect(hours('07:30', '09:10')).toBeCloseTo(1.6667, 3)
  })

  it('nunca retorna duração negativa', () => {
    expect(hours('10:00', '08:00')).toBe(0)
  })
})

describe('byId', () => {
  it('indexa a lista pela chave informada', () => {
    const map = byId([{ teacherId: 'a', name: 'Ana' }, { teacherId: 'b', name: 'Bruno' }], 'teacherId')
    expect(map.b.name).toBe('Bruno')
  })
})
