import { useEffect, useState } from 'react'
import { api, type Department } from '../api'

export default function Departments() {
  const [rows, setRows] = useState<Department[]>([])
  const [err, setErr] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    ;(async () => {
      try {
        setRows(await api.get<Department[]>('/departments'))
      } catch (e) {
        setErr((e as Error).message)
      } finally {
        setLoading(false)
      }
    })()
  }, [])

  return (
    <div>
      <div className="pagehead">
        <h2>
          Отделы <span className="muted">({rows.length})</span>
        </h2>
      </div>
      {err && <div className="error">{err}</div>}
      {loading ? (
        <div className="muted">Загрузка…</div>
      ) : (
        <table className="grid">
          <thead>
            <tr>
              <th style={{ width: 60 }}>ID</th>
              <th>Название</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((d) => (
              <tr key={d.id}>
                <td>{d.id}</td>
                <td>{d.name}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
