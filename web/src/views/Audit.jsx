import { useState } from 'react'
import { Empty, Loading, Message } from '../components.jsx'
import { useResources } from '../hooks.js'
import { AUDIT_ACTION_NAME, ENTITY_NAME, formatDate } from '../labels.js'

function summary(item) {
  const d = item.details || {}
  if (item.action === 'ROLE_CHANGED') return `${d.email}: ${d.from} → ${d.to}`
  if (item.action === 'ROLE_ASSIGNED') return `${d.from} → ${d.to}`
  if (item.action === 'CALENDAR_SYNC') return `${d.imported} compromisso(s) importado(s)`
  if (item.action.startsWith('NOTIFICATION')) {
    return d.skipped ? d.skipped : `${d.sent} enviado(s), ${d.failed?.length || 0} falha(s)`
  }
  if (item.entity === 'schedule' && d.term) return `${d.term} · versão ${d.version}${d.reason ? ` — “${d.reason}”` : ''}`
  if (item.action === 'UPDATE' && d.after) return d.after.name || d.after.code || ''
  return d.name || d.code || d.email || ''
}

export default function Audit() {
  const { data, error, reload } = useResources(['/audit?limit=500'])
  const [entity, setEntity] = useState('')

  if (!data) return error ? <Message>{error}</Message> : <Loading />
  const items = data[0].filter((item) => !entity || item.entity === entity)

  return (
    <section>
      <header className="section-header">
        <h2>Auditoria</h2>
        <button type="button" onClick={reload}>Atualizar</button>
        <p className="muted">
          Operações críticas registradas: logins, cadastros, alterações, exclusões, mudanças de perfil e o ciclo de
          vida das grades. Tentativas de acesso sem autenticação válida ficam no log de acesso da API.
        </p>
      </header>
      <div className="card">
        <label className="field">
          <span>Filtrar por</span>
          <select value={entity} onChange={(e) => setEntity(e.target.value)}>
            <option value="">Todas as operações</option>
            {Object.entries(ENTITY_NAME).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
      </div>
      {items.length === 0 ? (
        <Empty>Nenhuma operação registrada.</Empty>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>Quando</th><th>Quem</th><th>Operação</th><th>Item</th><th>Detalhe</th></tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.auditId}>
                  <td data-label="Quando">{formatDate(item.at)}</td>
                  <td data-label="Quem">{item.email}</td>
                  <td data-label="Operação">{AUDIT_ACTION_NAME[item.action] || item.action}</td>
                  <td data-label="Item">{ENTITY_NAME[item.entity] || item.entity}</td>
                  <td data-label="Detalhe">{summary(item)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
