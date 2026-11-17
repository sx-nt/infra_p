import { useState } from 'react'
import { api } from '../api.js'
import { Empty, Field, Loading, Message } from '../components.jsx'
import { useResources } from '../hooks.js'

// Cadastro genérico de professores, disciplinas e turmas.
// fields: [{ name, label, type: 'text' | 'email' | 'number' | 'select', options?, render? }]
export default function Crud({ title, description, path, idKey, fields, extraPaths = [], buildOptions }) {
  const { data, error, reload } = useResources([path, ...extraPaths])
  const empty = Object.fromEntries(fields.map((f) => [f.name, '']))
  const [form, setForm] = useState(empty)
  const [editing, setEditing] = useState(null)
  const [message, setMessage] = useState({})
  const [busy, setBusy] = useState(false)

  if (!data) return error ? <Message>{error}</Message> : <Loading />
  const [items, ...extras] = data
  const options = buildOptions ? buildOptions(extras) : {}

  const payload = () =>
    Object.fromEntries(
      fields.map((f) => [f.name, f.type === 'number' ? Number(form[f.name]) : form[f.name].trim()]),
    )

  const submit = async (event) => {
    event.preventDefault()
    setBusy(true)
    try {
      if (editing) {
        await api(`${path}/${encodeURIComponent(editing)}`, { method: 'PUT', body: payload() })
        setMessage({ ok: 'Alterações salvas.' })
      } else {
        await api(path, { method: 'POST', body: payload() })
        setMessage({ ok: 'Cadastro realizado.' })
      }
      setForm(empty)
      setEditing(null)
      await reload()
    } catch (err) {
      setMessage({ error: err.message })
    } finally {
      setBusy(false)
    }
  }

  const edit = (item) => {
    setEditing(item[idKey])
    setForm(Object.fromEntries(fields.map((f) => [f.name, String(item[f.name] ?? '')])))
    setMessage({})
  }

  const remove = async (item) => {
    if (!window.confirm(`Excluir ${item[fields[0].name]}?`)) return
    try {
      await api(`${path}/${encodeURIComponent(item[idKey])}`, { method: 'DELETE' })
      setMessage({ ok: 'Registro excluído.' })
      await reload()
    } catch (err) {
      setMessage({ error: err.message })
    }
  }

  const display = (field, item) => {
    if (field.type === 'select') {
      const option = (options[field.name] || []).find(([value]) => value === item[field.name])
      return option ? option[1] : item[field.name]
    }
    return item[field.name]
  }

  return (
    <section>
      <header className="section-header">
        <h2>{title}</h2>
        {description && <p className="muted">{description}</p>}
      </header>

      <form className="card form-grid" onSubmit={submit}>
        <h3>{editing ? 'Editar' : 'Novo cadastro'}</h3>
        {fields.map((field) => (
          <Field key={field.name} label={field.label}>
            {field.type === 'select' ? (
              <select
                required
                value={form[field.name]}
                onChange={(e) => setForm({ ...form, [field.name]: e.target.value })}
              >
                <option value="">Selecione…</option>
                {(options[field.name] || []).map(([value, label]) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
            ) : (
              <input
                required
                type={field.type || 'text'}
                min={field.type === 'number' ? 1 : undefined}
                step={field.type === 'number' ? 1 : undefined}
                placeholder={field.placeholder}
                value={form[field.name]}
                onChange={(e) => setForm({ ...form, [field.name]: e.target.value })}
              />
            )}
          </Field>
        ))}
        <div className="actions">
          <button type="submit" className="primary" disabled={busy}>
            {editing ? 'Salvar alterações' : 'Cadastrar'}
          </button>
          {editing && (
            <button type="button" onClick={() => { setEditing(null); setForm(empty) }}>
              Cancelar
            </button>
          )}
        </div>
        <Message kind="success">{message.ok}</Message>
        <Message>{message.error}</Message>
      </form>

      {items.length === 0 ? (
        <Empty>Nenhum registro cadastrado.</Empty>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                {fields.map((f) => <th key={f.name}>{f.label}</th>)}
                <th aria-label="Ações" />
              </tr>
            </thead>
            <tbody>
              {[...items]
                .sort((a, b) => String(a[fields[0].name]).localeCompare(String(b[fields[0].name]), 'pt-BR'))
                .map((item) => (
                  <tr key={item[idKey]}>
                    {fields.map((f) => <td key={f.name} data-label={f.label}>{display(f, item)}</td>)}
                    <td className="row-actions">
                      <button type="button" onClick={() => edit(item)}>Editar</button>
                      <button type="button" className="danger" onClick={() => remove(item)}>Excluir</button>
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
