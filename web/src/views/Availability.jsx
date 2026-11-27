import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { Empty, Field, Loading, Message } from '../components.jsx'
import { useResources } from '../hooks.js'
import { DAYS } from '../labels.js'

const newRow = () => ({ day: 'MON', start: '08:00', end: '10:00', type: 'BLOCKED' })

export default function Availability({ user }) {
  const isCoordinator = user.role === 'COORDINATOR'
  const { data: teacherData, error: teacherError } = useResources(isCoordinator ? ['/teachers'] : [])
  const [teacherId, setTeacherId] = useState(isCoordinator ? '' : user.teacherId)
  const [rows, setRows] = useState(null)
  const [message, setMessage] = useState({})

  useEffect(() => {
    if (!teacherId) return
    setRows(null)
    api(`/teachers/${teacherId}/availability`)
      .then((items) =>
        setRows(
          items
            .map(({ day, start, end, type, origin }) => ({ day, start, end, type, origin }))
            .sort((a, b) => DAYS.findIndex(([d]) => d === a.day) - DAYS.findIndex(([d]) => d === b.day) || a.start.localeCompare(b.start)),
        ),
      )
      .catch((err) => setMessage({ error: err.message }))
  }, [teacherId])

  if (!isCoordinator && !user.teacherId) {
    return <Message>Seu usuário não está vinculado a um professor cadastrado.</Message>
  }

  const update = (index, field, value) => setRows(rows.map((row, i) => (i === index ? { ...row, [field]: value } : row)))

  const save = async (event) => {
    event.preventDefault()
    try {
      await api(`/teachers/${teacherId}/availability`, { method: 'PUT', body: { availability: rows } })
      setMessage({ ok: 'Disponibilidade salva.' })
    } catch (err) {
      setMessage({ error: err.message })
    }
  }

  return (
    <section>
      <header className="section-header">
        <h2>{isCoordinator ? 'Disponibilidade dos professores' : 'Minha disponibilidade'}</h2>
        <p className="muted">
          Horários bloqueados impedem a alocação de aulas. Horários disponíveis são informativos.
        </p>
      </header>

      {isCoordinator && (
        <div className="card">
          {teacherError && <Message>{teacherError}</Message>}
          <Field label="Professor">
            <select value={teacherId} onChange={(e) => { setTeacherId(e.target.value); setMessage({}) }}>
              <option value="">Selecione…</option>
              {(teacherData?.[0] || []).map((t) => <option key={t.teacherId} value={t.teacherId}>{t.name}</option>)}
            </select>
          </Field>
        </div>
      )}

      {teacherId && !rows && !message.error && <Loading />}
      {teacherId && rows && (
        <form className="card" onSubmit={save}>
          {rows.length === 0 && <Empty>Nenhuma restrição informada.</Empty>}
          {rows.map((row, index) => (
            <div className="row-editor" key={index}>
              <Field label="Dia">
                <select value={row.day} onChange={(e) => update(index, 'day', e.target.value)}>
                  {DAYS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                </select>
              </Field>
              <Field label="Início">
                <input type="time" required value={row.start} onChange={(e) => update(index, 'start', e.target.value)} />
              </Field>
              <Field label="Fim">
                <input type="time" required value={row.end} onChange={(e) => update(index, 'end', e.target.value)} />
              </Field>
              <Field label="Tipo">
                <select value={row.type} onChange={(e) => update(index, 'type', e.target.value)}>
                  <option value="BLOCKED">Bloqueado</option>
                  <option value="AVAILABLE">Disponível</option>
                </select>
              </Field>
              <button type="button" className="danger" onClick={() => setRows(rows.filter((_, i) => i !== index))}>
                Remover
              </button>
            </div>
          ))}
          <div className="actions">
            <button type="button" onClick={() => setRows([...rows, newRow()])}>Adicionar horário</button>
            <button type="submit" className="primary">Salvar</button>
          </div>
          <Message kind="success">{message.ok}</Message>
          <Message>{message.error}</Message>
        </form>
      )}
    </section>
  )
}
