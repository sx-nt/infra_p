import { useEffect, useState } from 'react'
import { api } from './api.js'
import { getConfig, handleRedirect, getIdToken, loadConfig, login, logout } from './auth.js'
import { Loading, Message } from './components.jsx'
import { ROLE_NAME } from './labels.js'
import Audit from './views/Audit.jsx'
import Availability from './views/Availability.jsx'
import Crud from './views/Crud.jsx'
import Qualifications from './views/Qualifications.jsx'
import Schedules from './views/Schedules.jsx'
import Users from './views/Users.jsx'

const SECTIONS = {
  grades: { label: 'Grades', roles: ['COORDINATOR', 'TEACHER'], render: (user) => <Schedules user={user} /> },
  disponibilidade: {
    label: 'Disponibilidade',
    roles: ['COORDINATOR', 'TEACHER'],
    render: (user) => <Availability user={user} />,
  },
  professores: {
    label: 'Professores',
    roles: ['COORDINATOR'],
    render: () => (
      <Crud
        title="Professores"
        description="O e-mail vincula o professor à conta usada no login."
        path="/teachers"
        idKey="teacherId"
        fields={[
          { name: 'name', label: 'Nome' },
          { name: 'email', label: 'E-mail', type: 'email' },
        ]}
      />
    ),
  },
  disciplinas: {
    label: 'Disciplinas',
    roles: ['COORDINATOR'],
    render: () => (
      <Crud
        title="Disciplinas"
        path="/subjects"
        idKey="subjectId"
        fields={[
          { name: 'code', label: 'Código', placeholder: 'ISN75620501' },
          { name: 'name', label: 'Nome' },
          { name: 'weeklyHours', label: 'Carga semanal (h)', type: 'number' },
        ]}
      />
    ),
  },
  turmas: {
    label: 'Turmas',
    roles: ['COORDINATOR'],
    render: () => (
      <Crud
        title="Turmas"
        path="/classes"
        idKey="classId"
        extraPaths={['/subjects']}
        buildOptions={([subjects]) => ({
          subjectId: subjects.map((s) => [s.subjectId, `${s.code} — ${s.name}`]),
        })}
        fields={[
          { name: 'code', label: 'Código' },
          { name: 'term', label: 'Período letivo', placeholder: '2026.2' },
          { name: 'subjectId', label: 'Disciplina', type: 'select' },
        ]}
      />
    ),
  },
  habilitacoes: { label: 'Habilitações', roles: ['COORDINATOR'], render: () => <Qualifications /> },
  usuarios: { label: 'Usuários', roles: ['COORDINATOR'], render: (user) => <Users user={user} /> },
  auditoria: { label: 'Auditoria', roles: ['COORDINATOR'], render: () => <Audit /> },
}

function currentSection() {
  return window.location.hash.replace(/^#\/?/, '') || 'grades'
}

function Login({ error }) {
  const providers = getConfig().auth.identityProviders || []
  return (
    <main className="login">
      <div className="card login-card">
        <h1>Classly</h1>
        <p>Planejamento e publicação de grades de horários.</p>
        <Message>{error}</Message>
        <button type="button" className="primary wide" onClick={() => login()}>Entrar com e-mail</button>
        {providers.includes('Google') && (
          <button type="button" className="wide" onClick={() => login('Google')}>Entrar com Google</button>
        )}
        <p className="muted small">
          Ainda não tem conta? Use “Entrar com e-mail” e escolha “Criar conta”. Você receberá um código de
          verificação por e-mail.
        </p>
      </div>
    </main>
  )
}

export default function App() {
  const [state, setState] = useState({ status: 'loading' })
  const [section, setSection] = useState(currentSection)

  useEffect(() => {
    const onHash = () => setSection(currentSection())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  useEffect(() => {
    ;(async () => {
      try {
        const config = await loadConfig()
        await handleRedirect()
        if (config.auth && !(await getIdToken())) return setState({ status: 'anonymous' })
        setState({ status: 'ready', user: await api('/me') })
      } catch (err) {
        setState(err.status === 401 ? { status: 'anonymous', error: err.message } : { status: 'error', error: err.message })
      }
    })()
  }, [])

  if (state.status === 'loading') return <main className="center"><Loading /></main>
  if (state.status === 'anonymous') return <Login error={state.error} />
  if (state.status === 'error') {
    return (
      <main className="center">
        <Message>{state.error}</Message>
        <button type="button" onClick={() => window.location.reload()}>Tentar novamente</button>
      </main>
    )
  }

  const { user } = state
  const allowed = Object.entries(SECTIONS).filter(([, s]) => s.roles.includes(user.role))
  const active = allowed.find(([key]) => key === section) || allowed[0]

  return (
    <div className="app">
      <header className="topbar">
        <span className="brand">Classly</span>
        <nav aria-label="Seções">
          {allowed.map(([key, s]) => (
            <a key={key} href={`#/${key}`} className={active?.[0] === key ? 'active' : ''}>{s.label}</a>
          ))}
        </nav>
        <div className="user">
          <span>
            {user.name}
            <small>{ROLE_NAME[user.role]}</small>
          </span>
          {getConfig().auth && <button type="button" onClick={logout}>Sair</button>}
        </div>
      </header>
      <main className="content">
        {active ? (
          // A chave remonta a seção ao trocar de aba: cada cadastro tem seu próprio estado.
          <div key={active[0]}>{active[1].render(user)}</div>
        ) : (
          <div className="card">
            <h2>Acesso aguardando liberação</h2>
            <p>
              Sua conta ({user.email}) foi criada, mas ainda não está vinculada a um professor cadastrado. Peça à
              coordenação para cadastrar seu e-mail ou liberar seu acesso e entre novamente.
            </p>
          </div>
        )}
      </main>
    </div>
  )
}
