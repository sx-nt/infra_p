import { useState } from 'react'
import { api } from '../api.js'
import { Empty, Field, Loading, Message } from '../components.jsx'
import { useResources } from '../hooks.js'
import { byId } from '../labels.js'

export default function Qualifications() {
  const { data, error, reload } = useResources(['/qualifications', '/teachers', '/subjects'])
  const [form, setForm] = useState({ teacherId: '', subjectId: '' })
  const [message, setMessage] = useState({})

  if (!data) return error ? <Message>{error}</Message> : <Loading />
  const [qualifications, teachers, subjects] = data
  const teacherById = byId(teachers, 'teacherId')
  const subjectById = byId(subjects, 'subjectId')

  const save = async (teacherId, subjectId, enabled) => {
    try {
      await api(`/teachers/${teacherId}/subjects/${subjectId}`, { method: 'PUT', body: { enabled } })
      setMessage({ ok: 'Habilitação atualizada.' })
      await reload()
    } catch (err) {
      setMessage({ error: err.message })
    }
  }

  const remove = async (teacherId, subjectId) => {
    try {
      await api(`/teachers/${teacherId}/subjects/${subjectId}`, { method: 'DELETE' })
      setMessage({ ok: 'Habilitação removida.' })
      await reload()
    } catch (err) {
      setMessage({ error: err.message })
    }
  }

  const sorted = [...qualifications].sort((a, b) =>
    (teacherById[a.teacherId]?.name || '').localeCompare(teacherById[b.teacherId]?.name || '', 'pt-BR'),
  )

  return (
    <section>
      <header className="section-header">
        <h2>Habilitações</h2>
        <p className="muted">Disciplinas que cada professor pode lecionar (RN06).</p>
      </header>

      <form
        className="card form-grid"
        onSubmit={(e) => {
          e.preventDefault()
          save(form.teacherId, form.subjectId, true)
        }}
      >
        <h3>Habilitar professor</h3>
        <Field label="Professor">
          <select required value={form.teacherId} onChange={(e) => setForm({ ...form, teacherId: e.target.value })}>
            <option value="">Selecione…</option>
            {teachers.map((t) => <option key={t.teacherId} value={t.teacherId}>{t.name}</option>)}
          </select>
        </Field>
        <Field label="Disciplina">
          <select required value={form.subjectId} onChange={(e) => setForm({ ...form, subjectId: e.target.value })}>
            <option value="">Selecione…</option>
            {subjects.map((s) => <option key={s.subjectId} value={s.subjectId}>{s.code} — {s.name}</option>)}
          </select>
        </Field>
        <div className="actions">
          <button type="submit" className="primary">Habilitar</button>
        </div>
        <Message kind="success">{message.ok}</Message>
        <Message>{message.error}</Message>
      </form>

      {sorted.length === 0 ? (
        <Empty>Nenhuma habilitação cadastrada.</Empty>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>Professor</th><th>Disciplina</th><th>Situação</th><th aria-label="Ações" /></tr>
            </thead>
            <tbody>
              {sorted.map((q) => (
                <tr key={`${q.teacherId}-${q.subjectId}`}>
                  <td data-label="Professor">{teacherById[q.teacherId]?.name || q.teacherId}</td>
                  <td data-label="Disciplina">{subjectById[q.subjectId]?.name || q.subjectId}</td>
                  <td data-label="Situação">
                    <span className={`badge ${q.enabled ? 'ok' : 'off'}`}>{q.enabled ? 'Habilitado' : 'Suspenso'}</span>
                  </td>
                  <td className="row-actions">
                    <button type="button" onClick={() => save(q.teacherId, q.subjectId, !q.enabled)}>
                      {q.enabled ? 'Suspender' : 'Reativar'}
                    </button>
                    <button type="button" className="danger" onClick={() => remove(q.teacherId, q.subjectId)}>Remover</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
