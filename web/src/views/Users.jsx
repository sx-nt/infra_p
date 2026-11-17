import { useState } from 'react'
import { api } from '../api.js'
import { Loading, Message } from '../components.jsx'
import { useResources } from '../hooks.js'
import { ROLE_NAME, byId, formatDate } from '../labels.js'

export default function Users({ user }) {
  const { data, error, reload } = useResources(['/users', '/teachers'])
  const [message, setMessage] = useState({})

  if (!data) return error ? <Message>{error}</Message> : <Loading />
  const [users, teachers] = data
  const teacherById = byId(teachers, 'teacherId')

  const changeRole = async (target, role) => {
    try {
      await api(`/users/${encodeURIComponent(target.userId)}/role`, { method: 'PUT', body: { role } })
      setMessage({ ok: `Perfil de ${target.email} atualizado.` })
      await reload()
    } catch (err) {
      setMessage({ error: err.message })
    }
  }

  return (
    <section>
      <header className="section-header">
        <h2>Usuários</h2>
        <p className="muted">
          Contas criadas no login. Quem se cadastra com o e-mail de um professor já cadastrado recebe o perfil de
          professor automaticamente; os demais aguardam liberação.
        </p>
      </header>
      <Message kind="success">{message.ok}</Message>
      <Message>{message.error}</Message>
      <div className="table-wrap">
        <table>
          <thead>
            <tr><th>Nome</th><th>E-mail</th><th>Professor vinculado</th><th>Criado em</th><th>Perfil</th></tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.userId}>
                <td data-label="Nome">{u.name}</td>
                <td data-label="E-mail">{u.email}</td>
                <td data-label="Professor">{teacherById[u.teacherId]?.name || '—'}</td>
                <td data-label="Criado em">{formatDate(u.createdAt)}</td>
                <td data-label="Perfil">
                  <select
                    value={u.role}
                    disabled={u.userId === user.userId}
                    onChange={(e) => changeRole(u, e.target.value)}
                  >
                    {Object.entries(ROLE_NAME).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                  </select>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
