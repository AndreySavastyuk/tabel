import { useState, type FormEvent } from 'react'
import { useAuth } from '../auth'

// Дев-удобства (предзаполнение и подсказка логинов) — только в dev-сборке.
// В проде (vite build) import.meta.env.PROD === true → пустые поля, без подсказки.
const DEV = !import.meta.env.PROD

export default function Login() {
  const { login } = useAuth()
  const [username, setUsername] = useState(DEV ? 'admin' : '')
  const [password, setPassword] = useState(DEV ? 'admin' : '')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setErr('')
    setBusy(true)
    try {
      await login(username, password)
    } catch (e) {
      setErr((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="center">
      <form className="card login" onSubmit={submit}>
        <h1>Табель СКУД</h1>
        <label>
          Логин
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoFocus />
        </label>
        <label>
          Пароль
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
        </label>
        {err && <div className="error">{err}</div>}
        <button disabled={busy}>{busy ? 'Вход…' : 'Войти'}</button>
        {DEV && <div className="hint muted">Дев-логины: admin/admin · buh/buh · ruk/ruk</div>}
      </form>
    </div>
  )
}
