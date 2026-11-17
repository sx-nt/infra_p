export function Message({ kind = 'error', children }) {
  if (!children) return null
  return <div className={`message ${kind}`} role={kind === 'error' ? 'alert' : 'status'}>{children}</div>
}

export function Loading() {
  return <p className="muted">Carregando…</p>
}

export function Empty({ children }) {
  return <p className="empty">{children}</p>
}

export function Field({ label, children }) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
    </label>
  )
}

export function ErrorList({ errors }) {
  if (!errors?.length) return null
  return (
    <ul className="error-list">
      {errors.map((error, index) => (
        <li key={index}>
          {error.allocation !== undefined && <strong>Linha {error.allocation + 1}: </strong>}
          {error.reason}
        </li>
      ))}
    </ul>
  )
}
