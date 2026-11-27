import { useState } from 'react'
import { api } from '../api.js'
import { Empty, ErrorList, Field, Loading, Message } from '../components.jsx'
import { useResources } from '../hooks.js'
import { DAYS, STATUS_NAME, byId, formatDate, hours } from '../labels.js'

const newAllocation = () => ({ classId: '', teacherId: '', day: 'MON', start: '08:00', end: '10:00' })

// Grade semanal: uma coluna por dia com as aulas em ordem de horário.
function WeekGrid({ schedule, lookups, highlightTeacherId, onlyMine }) {
  const { teachers, subjects, classes } = lookups
  const allocations = schedule.allocations.filter((a) => !onlyMine || a.teacherId === highlightTeacherId)
  const days = DAYS.filter(([day]) => !['SAT', 'SUN'].includes(day) || allocations.some((a) => a.day === day))
  if (allocations.length === 0) return <Empty>Nenhuma aula para exibir.</Empty>
  return (
    <div className="week">
      {days.map(([day, label]) => {
        const entries = allocations.filter((a) => a.day === day).sort((a, b) => a.start.localeCompare(b.start))
        return (
          <div className="week-day" key={day}>
            <h4>{label}</h4>
            {entries.length === 0 && <p className="muted small">—</p>}
            {entries.map((a) => (
              <div className={`slot ${a.teacherId === highlightTeacherId ? 'mine' : ''}`} key={a.allocationId}>
                <span className="slot-time">{a.start}–{a.end}</span>
                <strong>{subjects[a.subjectId]?.name || a.subjectId}</strong>
                <span>Turma {classes[a.classId]?.code || a.classId}</span>
                <span className="muted">{teachers[a.teacherId]?.name || a.teacherId}</span>
              </div>
            ))}
          </div>
        )
      })}
    </div>
  )
}

// Monta uma grade nova ou ajusta um rascunho existente (schedule).
function ScheduleEditor({ lookups, qualifications, schedule, onSaved, onCancel }) {
  const { classes, subjects, teachers } = lookups
  const editing = Boolean(schedule)
  const [term, setTerm] = useState(schedule?.term || '')
  const [rows, setRows] = useState(
    schedule
      ? schedule.allocations.map(({ classId, teacherId, day, start, end }) => ({ classId, teacherId, day, start, end }))
      : [newAllocation()],
  )
  const [result, setResult] = useState(null)
  const [unresolved, setUnresolved] = useState([])
  const [message, setMessage] = useState({})
  const [busy, setBusy] = useState(false)

  const terms = [...new Set(Object.values(classes).map((c) => c.term))].sort()
  const termClasses = Object.values(classes).filter((c) => c.term === term).sort((a, b) => a.code.localeCompare(b.code))
  const qualified = (subjectId) =>
    qualifications.filter((q) => q.subjectId === subjectId && q.enabled).map((q) => teachers[q.teacherId]).filter(Boolean)

  const update = (index, field, value) => {
    setResult(null)
    setRows(rows.map((row, i) => (i === index ? { ...row, [field]: value, ...(field === 'classId' ? { teacherId: '' } : {}) } : row)))
  }

  const payload = () => ({
    term,
    allocations: rows.map((row) => ({ ...row, subjectId: classes[row.classId]?.subjectId || '' })),
  })

  // Carga horária alocada por turma, comparada com a exigida pela disciplina.
  const load = termClasses.map((c) => {
    const allocated = rows.filter((r) => r.classId === c.classId).reduce((sum, r) => sum + hours(r.start, r.end), 0)
    return { c, allocated, required: Number(subjects[c.subjectId]?.weeklyHours || 0) }
  })

  const run = async (task) => {
    setBusy(true)
    setMessage({})
    try {
      await task()
    } catch (err) {
      setMessage({ error: err.message })
      if (err.errors?.length) setResult({ valid: false, errors: err.errors })
    } finally {
      setBusy(false)
    }
  }

  const generate = () =>
    run(async () => {
      if (rows.some((r) => r.classId) && !window.confirm('Substituir as aulas atuais pela proposta gerada?')) return
      const proposal = await api('/schedules/generate', { method: 'POST', body: { term } })
      setRows(proposal.allocations.length ? proposal.allocations : [newAllocation()])
      setUnresolved(proposal.unresolved)
      setResult(proposal.errors.length ? { valid: false, errors: proposal.errors } : null)
      setMessage({
        ok: `Proposta gerada com ${proposal.allocations.length} aula(s). Revise, ajuste se precisar e salve o rascunho.`,
      })
    })

  const validate = () => run(async () => setResult(await api('/schedules/validate', { method: 'POST', body: payload() })))

  const save = () =>
    run(async () => {
      const saved = editing
        ? await api(`/schedules/${schedule.scheduleId}`, { method: 'PUT', body: { allocations: payload().allocations } })
        : await api('/schedules', { method: 'POST', body: payload() })
      onSaved(saved)
    })

  return (
    <div className="card">
      <h3>{editing ? `Ajustar rascunho ${schedule.term} · versão ${schedule.version}` : 'Nova grade'}</h3>
      {terms.length === 0 ? (
        <Message>Cadastre turmas com período letivo antes de montar uma grade.</Message>
      ) : (
        <>
          <div className="actions">
            <Field label="Período letivo">
              <select
                value={term}
                disabled={editing}
                onChange={(e) => { setTerm(e.target.value); setRows([newAllocation()]); setResult(null); setUnresolved([]) }}
              >
                <option value="">Selecione…</option>
                {terms.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </Field>
            {term && (
              <button type="button" className="align-end" disabled={busy} onClick={generate}>
                Gerar proposta automaticamente
              </button>
            )}
          </div>

          {term && (
            <>
              <div className="load">
                {load.map(({ c, allocated, required }) => (
                  <span key={c.classId} className={`badge ${allocated === required ? 'ok' : 'warn'}`}>
                    {c.code}: {allocated}h / {required}h
                  </span>
                ))}
              </div>

              {unresolved.length > 0 && (
                <Message>
                  Turmas que a geração não conseguiu alocar:
                  <ErrorList errors={unresolved.map((u) => ({ reason: `${classes[u.classId]?.code || u.classId}: ${u.reason}` }))} />
                </Message>
              )}

              {rows.map((row, index) => {
                const subjectId = classes[row.classId]?.subjectId
                return (
                  <div className="row-editor allocation" key={index}>
                    <span className="row-number">{index + 1}</span>
                    <Field label="Turma">
                      <select required value={row.classId} onChange={(e) => update(index, 'classId', e.target.value)}>
                        <option value="">Selecione…</option>
                        {termClasses.map((c) => (
                          <option key={c.classId} value={c.classId}>{c.code} — {subjects[c.subjectId]?.name}</option>
                        ))}
                      </select>
                    </Field>
                    <Field label="Professor habilitado">
                      <select required value={row.teacherId} disabled={!subjectId} onChange={(e) => update(index, 'teacherId', e.target.value)}>
                        <option value="">{subjectId && qualified(subjectId).length === 0 ? 'Nenhum habilitado' : 'Selecione…'}</option>
                        {subjectId && qualified(subjectId).map((t) => <option key={t.teacherId} value={t.teacherId}>{t.name}</option>)}
                      </select>
                    </Field>
                    <Field label="Dia">
                      <select value={row.day} onChange={(e) => update(index, 'day', e.target.value)}>
                        {DAYS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                      </select>
                    </Field>
                    <Field label="Início">
                      <input type="time" value={row.start} onChange={(e) => update(index, 'start', e.target.value)} />
                    </Field>
                    <Field label="Fim">
                      <input type="time" value={row.end} onChange={(e) => update(index, 'end', e.target.value)} />
                    </Field>
                    <button type="button" className="danger" disabled={rows.length === 1} onClick={() => { setRows(rows.filter((_, i) => i !== index)); setResult(null) }}>
                      Remover
                    </button>
                  </div>
                )
              })}

              {result?.valid && <Message kind="success">Nenhum conflito encontrado. A grade pode ser salva.</Message>}
              {result && !result.valid && (
                <Message>
                  A grade contém conflitos:
                  <ErrorList errors={result.errors} />
                </Message>
              )}
              <Message kind="success">{message.ok}</Message>
              <Message>{message.error}</Message>

              <div className="actions">
                <button type="button" onClick={() => { setRows([...rows, { ...newAllocation(), ...rows[rows.length - 1] }]); setResult(null) }}>
                  Adicionar aula
                </button>
                <button type="button" disabled={busy} onClick={validate}>Validar</button>
                <button type="button" className="primary" disabled={busy} onClick={save}>
                  {editing ? 'Salvar ajustes' : 'Salvar rascunho'}
                </button>
                <button type="button" onClick={onCancel}>Cancelar</button>
              </div>
            </>
          )}
        </>
      )}
    </div>
  )
}

function History({ schedule }) {
  if (!schedule.history?.length) return null
  return (
    <details className="history">
      <summary>Histórico</summary>
      <ol>
        {schedule.history.map((entry, index) => (
          <li key={index}>
            <strong>{STATUS_NAME[entry.status] || entry.status}</strong> · {formatDate(entry.at)} · {entry.by}
            {entry.reason && <> — “{entry.reason}”</>}
          </li>
        ))}
      </ol>
    </details>
  )
}

function NotificationStatus({ notification, teachers }) {
  if (!notification) return null
  if (notification.skipped) return <p className="muted small">E-mails não enviados: {notification.skipped}</p>
  return (
    <div className="small">
      <p className="muted">
        E-mails: {notification.sent} enviado(s)
        {notification.failed?.length ? `, ${notification.failed.length} com falha` : ''}
        {notification.lastAttemptAt ? ` · última tentativa em ${formatDate(notification.lastAttemptAt)}` : ''}
      </p>
      <ErrorList errors={(notification.failed || []).map((f) => ({ reason: `${teachers[f.teacherId]?.name || f.teacherId}: ${f.reason}` }))} />
    </div>
  )
}

export default function Schedules({ user }) {
  const isCoordinator = user.role === 'COORDINATOR'
  const { data, error, reload } = useResources(
    isCoordinator
      ? ['/schedules', '/teachers', '/subjects', '/classes', '/qualifications']
      : ['/schedules', '/teachers', '/subjects', '/classes'],
  )
  const [selected, setSelected] = useState(null)
  const [editor, setEditor] = useState(null) // null | 'new' | rascunho em edição
  const [onlyMine, setOnlyMine] = useState(!isCoordinator)
  const [message, setMessage] = useState({})

  if (!data) return error ? <Message>{error}</Message> : <Loading />
  const [schedules, teachers, subjects, classes, qualifications = []] = data
  const lookups = {
    teachers: byId(teachers, 'teacherId'),
    subjects: byId(subjects, 'subjectId'),
    classes: byId(classes, 'classId'),
  }
  const current = schedules.find((s) => s.scheduleId === selected) || schedules[0]

  const act = async (schedule, action, { confirm, body, success } = {}) => {
    if (confirm && !window.confirm(confirm)) return
    try {
      const updated = await api(`/schedules/${schedule.scheduleId}/${action}`, { method: 'POST', body })
      setSelected(updated.scheduleId)
      setMessage({ ok: typeof success === 'function' ? success(updated) : success })
      await reload()
    } catch (err) {
      setMessage({ error: err.message, errors: err.errors })
    }
  }

  const publishedMessage = (published) => {
    const n = published.notification || {}
    if (n.skipped) return `Grade publicada. E-mails não enviados: ${n.skipped}`
    return `Grade publicada. ${n.sent} professor(es) notificado(s)${n.failed?.length ? `; ${n.failed.length} falha(s) no envio` : ''}.`
  }

  const reject = (schedule) => {
    const reason = window.prompt('Motivo da devolução para rascunho:')
    if (reason?.trim()) act(schedule, 'reject', { body: { reason }, success: 'Grade devolvida para rascunho.' })
  }

  const remove = async (schedule) => {
    if (!window.confirm('Excluir este rascunho?')) return
    try {
      await api(`/schedules/${schedule.scheduleId}`, { method: 'DELETE' })
      setSelected(null)
      setMessage({ ok: 'Rascunho excluído.' })
      await reload()
    } catch (err) {
      setMessage({ error: err.message })
    }
  }

  const actions = (schedule) => {
    switch (schedule.status) {
      case 'DRAFT':
        return (
          <>
            <button type="button" className="primary" onClick={() => act(schedule, 'submit', { success: 'Grade enviada para validação.' })}>
              Enviar para validação
            </button>
            <button type="button" onClick={() => { setEditor(schedule); setMessage({}) }}>Ajustar</button>
            <button type="button" className="danger" onClick={() => remove(schedule)}>Excluir</button>
          </>
        )
      case 'IN_REVIEW':
        return (
          <>
            <button type="button" className="primary" onClick={() => act(schedule, 'approve', { success: 'Grade aprovada. Ela já pode ser publicada.' })}>
              Aprovar
            </button>
            <button type="button" onClick={() => reject(schedule)}>Devolver</button>
          </>
        )
      case 'APPROVED':
        return (
          <>
            <button
              type="button"
              className="primary"
              onClick={() => act(schedule, 'publish', {
                confirm: `Publicar a grade ${schedule.term} (versão ${schedule.version})? Os professores serão notificados por e-mail.`,
                success: publishedMessage,
              })}
            >
              Publicar
            </button>
            <button type="button" onClick={() => reject(schedule)}>Devolver</button>
          </>
        )
      case 'PUBLISHED':
        return schedule.notification?.failed?.length ? (
          <button type="button" onClick={() => act(schedule, 'notify', { success: (s) => `Reenvio concluído: ${s.notification.sent} e-mail(s) enviado(s) no total.` })}>
            Reenviar e-mails com falha
          </button>
        ) : null
      default:
        return null
    }
  }

  return (
    <section>
      <header className="section-header">
        <h2>{isCoordinator ? 'Grades de horários' : 'Grades publicadas'}</h2>
        {isCoordinator && !editor && (
          <button type="button" className="primary" onClick={() => { setEditor('new'); setMessage({}) }}>Nova grade</button>
        )}
        {isCoordinator && (
          <p className="muted">Ciclo: Rascunho → Em validação → Aprovada → Publicada. Toda etapa revalida os conflitos.</p>
        )}
      </header>

      <Message kind="success">{message.ok}</Message>
      <Message>{message.error}</Message>
      {message.errors?.length > 0 && <ErrorList errors={message.errors} />}

      {editor && (
        <ScheduleEditor
          key={editor === 'new' ? 'new' : editor.scheduleId}
          lookups={lookups}
          qualifications={qualifications}
          schedule={editor === 'new' ? null : editor}
          onCancel={() => setEditor(null)}
          onSaved={async (schedule) => {
            setEditor(null)
            setSelected(schedule.scheduleId)
            setMessage({ ok: 'Rascunho salvo. Envie para validação quando estiver pronto.' })
            await reload()
          }}
        />
      )}

      {schedules.length === 0 ? (
        <Empty>{isCoordinator ? 'Nenhuma grade criada ainda.' : 'Nenhuma grade publicada ainda.'}</Empty>
      ) : (
        <div className="schedule-layout">
          <ul className="schedule-list">
            {schedules.map((s) => (
              <li key={s.scheduleId}>
                <button
                  type="button"
                  className={s.scheduleId === current?.scheduleId ? 'active' : ''}
                  onClick={() => setSelected(s.scheduleId)}
                >
                  <strong>{s.term}</strong> · versão {s.version}
                  <span className={`badge status-${s.status}`}>{STATUS_NAME[s.status] || s.status}</span>
                  <span className="muted small">{formatDate(s.publishedAt || s.updatedAt || s.createdAt)}</span>
                </button>
              </li>
            ))}
          </ul>

          {current && (
            <div className="card schedule-detail">
              <div className="schedule-head">
                <div>
                  <h3>Grade {current.term} · versão {current.version}</h3>
                  <p className="muted small">
                    {STATUS_NAME[current.status]}
                    {current.publishedAt
                      ? ` em ${formatDate(current.publishedAt)} por ${current.publishedBy}`
                      : ` · criada em ${formatDate(current.createdAt)}${current.createdBy ? ` por ${current.createdBy}` : ''}`}
                  </p>
                </div>
                <div className="actions">
                  {user.teacherId && (
                    <label className="toggle">
                      <input type="checkbox" checked={onlyMine} onChange={(e) => setOnlyMine(e.target.checked)} />
                      Só meus horários
                    </label>
                  )}
                  {isCoordinator && actions(current)}
                </div>
              </div>
              {isCoordinator && current.status === 'PUBLISHED' && (
                <NotificationStatus notification={current.notification} teachers={lookups.teachers} />
              )}
              <WeekGrid schedule={current} lookups={lookups} highlightTeacherId={user.teacherId} onlyMine={onlyMine && !!user.teacherId} />
              {isCoordinator && <History schedule={current} />}
            </div>
          )}
        </div>
      )}
    </section>
  )
}
