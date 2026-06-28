import { useCallback, useEffect, useState } from 'react'
import { api, type Department, type UnresolvedAlias } from '../api'
import { useAuth } from '../auth'

export default function Aliases() {
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin_hr'
  const [rows, setRows] = useState<UnresolvedAlias[]>([])
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')
  const [deptName, setDeptName] = useState<Record<number, string>>({})

  const load = useCallback(async () => {
    setLoading(true)
    setErr('')
    try {
      const [al, deps] = await Promise.all([
        api.get<UnresolvedAlias[]>('/aliases/unresolved'),
        api.get<Department[]>('/departments'),
      ])
      setRows(al)
      setDeptName(Object.fromEntries(deps.map((d) => [d.id, d.name])))
    } catch (e) {
      setErr((e as Error).message)
    } finally {
      setLoading(false)
    }
  }, [])
  useEffect(() => {
    if (isAdmin) load()
    else setLoading(false)
  }, [isAdmin, load])

  const confirmNew = async (id: number) => {
    setErr(''); setMsg('')
    try {
      await api.post(`/aliases/${id}/confirm`, {})
      setMsg('Отмечен как отдельный сотрудник.')
      await load()
    } catch (e) { setErr((e as Error).message) }
  }
  const merge = async (id: number, targetId: number, name: string) => {
    setErr(''); setMsg('')
    try {
      const r = await api.post<{ moved: Record<string, number> }>(`/aliases/${id}/merge`, { target_employee_id: targetId })
      const m = r.moved
      setMsg(`Объединено с «${name}». Перенесено: дни ${m.day_records}, своды ${m.periods}, события ${m.events}, отсутствия ${m.absences}.`)
      await load()
    } catch (e) { setErr((e as Error).message) }
  }

  if (!isAdmin) {
    return (
      <div>
        <div className="pagehead"><h2>Разбор ФИО</h2></div>
        <div className="muted">Доступно только роли «Кадры/Админ».</div>
      </div>
    )
  }

  return (
    <div>
      <div className="pagehead">
        <h2>Разбор ФИО <span className="muted">({rows.length})</span></h2>
      </div>
      <p className="muted">
        Имена из выгрузок СКУД, не совпавшие с карточками сотрудников. Объедините
        с существующим сотрудником (если это опечатка/вариант ФИО) или подтвердите
        как нового. Кандидаты подобраны по похожести ФИО.
      </p>
      {err && <div className="error">{err}</div>}
      {msg && <div className="ok-box">{msg}</div>}

      {loading ? <div className="muted">Загрузка…</div> :
        rows.length === 0 ? <div className="ok-box">Очередь пуста — все ФИО распознаны.</div> : (
          <div className="card panel">
            <table className="grid">
              <thead>
                <tr><th>ФИО из выгрузки</th><th>Источник</th><th>Кандидаты</th><th>Действия</th></tr>
              </thead>
              <tbody>
                {rows.map((a) => (
                  <tr key={a.id}>
                    <td><strong>{a.raw_name}</strong></td>
                    <td>{a.source ? <span className="badge">{a.source}</span> : '—'}</td>
                    <td>
                      {a.candidates.length === 0 ? <span className="muted">нет похожих</span> : (
                        <div className="absrow" style={{ flexWrap: 'wrap', gap: 6 }}>
                          {a.candidates.map((c) => (
                            <button key={c.employee_id} className="link"
                                    title={`похожесть ${Math.round(c.score * 100)}%${c.canonical ? ', из справочника' : ''}`}
                                    onClick={() => merge(a.id, c.employee_id, c.full_name)}>
                              Объединить → {c.full_name}{c.department_id && deptName[c.department_id] ? ` · ${deptName[c.department_id]}` : ''} ({Math.round(c.score * 100)}%{c.canonical ? ', ✓' : ''})
                            </button>
                          ))}
                        </div>
                      )}
                    </td>
                    <td className="actions">
                      <button className="link" onClick={() => confirmNew(a.id)}>Подтвердить как нового</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
    </div>
  )
}
