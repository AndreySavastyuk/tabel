import { useCallback, useEffect, useState } from 'react'
import { api, type Cabinet, type Department, type Threshold } from '../api'
import { useAuth } from '../auth'

export default function Settings() {
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin_hr'

  const [depts, setDepts] = useState<Department[]>([])
  const [deptEdit, setDeptEdit] = useState<Record<number, string>>({})
  const [newDept, setNewDept] = useState('')
  const [cabs, setCabs] = useState<Cabinet[]>([])
  const [cabEdit, setCabEdit] = useState<Record<string, string>>({})
  const [thr, setThr] = useState<Threshold[]>([])
  const [thrEdit, setThrEdit] = useState<Record<string, string>>({})
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')

  const load = useCallback(async () => {
    setErr('')
    try {
      const [d, c, t] = await Promise.all([
        api.get<Department[]>('/departments'),
        api.get<Cabinet[]>('/settings/cabinets'),
        api.get<Threshold[]>('/settings/thresholds'),
      ])
      setDepts(d); setCabs(c); setThr(t)
      setDeptEdit(Object.fromEntries(d.map((x) => [x.id, x.name])))
      setCabEdit(Object.fromEntries(c.map((x) => [x.name, x.name])))
      setThrEdit(Object.fromEntries(t.map((x) => [x.key, String(x.value)])))
    } catch (e) {
      setErr((e as Error).message)
    }
  }, [])
  useEffect(() => {
    if (isAdmin) load()
  }, [isAdmin, load])

  const wrap = (fn: () => Promise<void>) => async () => {
    setErr(''); setMsg('')
    try { await fn() } catch (e) { setErr((e as Error).message) }
  }

  const saveDept = (d: Department) => wrap(async () => {
    await api.patch(`/departments/${d.id}`, { name: deptEdit[d.id].trim(), parent_id: d.parent_id ?? null })
    setMsg('Отдел переименован.'); await load()
  })
  const addDept = wrap(async () => {
    if (!newDept.trim()) return
    await api.post('/departments', { name: newDept.trim() })
    setMsg('Отдел добавлен.'); setNewDept(''); await load()
  })
  const renameCab = (oldName: string) => wrap(async () => {
    const r = await api.post<{ updated: number }>('/settings/cabinets/rename',
      { old_name: oldName, new_name: cabEdit[oldName] })
    setMsg(`Кабинет переименован у ${r.updated} сотр.`); await load()
  })
  const saveThr = wrap(async () => {
    const values: Record<string, number> = {}
    for (const t of thr) values[t.key] = Number(thrEdit[t.key])
    await api.put('/settings/thresholds', { values })
    setMsg('Пороги сохранены (применятся при следующем прогоне).'); await load()
  })

  if (!isAdmin) {
    return (
      <div>
        <div className="pagehead"><h2>Настройки</h2></div>
        <div className="muted">Доступно только роли «Кадры/Админ».</div>
      </div>
    )
  }

  return (
    <div>
      <div className="pagehead"><h2>Настройки</h2></div>
      {err && <div className="error">{err}</div>}
      {msg && <div className="ok-box">{msg}</div>}

      <div className="card panel">
        <h3>Отделы <span className="muted">({depts.length})</span></h3>
        <table className="grid">
          <tbody>
            {depts.map((d) => (
              <tr key={d.id}>
                <td style={{ width: '70%' }}>
                  <input value={deptEdit[d.id] ?? ''} style={{ width: '100%' }}
                         onChange={(e) => setDeptEdit((s) => ({ ...s, [d.id]: e.target.value }))} />
                </td>
                <td>
                  <button disabled={!deptEdit[d.id]?.trim() || deptEdit[d.id] === d.name}
                          onClick={saveDept(d)}>Сохранить</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="absrow" style={{ marginTop: 8 }}>
          <input placeholder="Новый отдел" value={newDept} onChange={(e) => setNewDept(e.target.value)} />
          <button disabled={!newDept.trim()} onClick={addDept}>Добавить отдел</button>
        </div>
      </div>

      <div className="card panel">
        <h3>Кабинеты <span className="muted">({cabs.length})</span></h3>
        {cabs.length === 0 ? <div className="muted">Кабинеты не заданы у сотрудников.</div> : (
          <table className="grid">
            <thead><tr><th>Название</th><th>Сотрудников</th><th></th></tr></thead>
            <tbody>
              {cabs.map((c) => (
                <tr key={c.name}>
                  <td style={{ width: '60%' }}>
                    <input value={cabEdit[c.name] ?? ''} style={{ width: '100%' }}
                           onChange={(e) => setCabEdit((s) => ({ ...s, [c.name]: e.target.value }))} />
                  </td>
                  <td>{c.count}</td>
                  <td>
                    <button disabled={cabEdit[c.name] === c.name} onClick={renameCab(c.name)}>Переименовать</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card panel">
        <h3>Пороги расчёта</h3>
        <p className="muted">Влияют на разбиение смен, опоздания, отклонения. Применяются при следующем прогоне.</p>
        <table className="grid">
          <thead><tr><th>Параметр</th><th>Значение</th><th>Ед.</th><th>По умолчанию</th></tr></thead>
          <tbody>
            {thr.map((t) => (
              <tr key={t.key}>
                <td>{t.label}</td>
                <td>
                  <input type="number" step="any" value={thrEdit[t.key] ?? ''} style={{ width: 90 }}
                         onChange={(e) => setThrEdit((s) => ({ ...s, [t.key]: e.target.value }))} />
                </td>
                <td className="muted">{t.unit}</td>
                <td className="muted">{t.default}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <button style={{ marginTop: 8 }} onClick={saveThr}>Сохранить пороги</button>
      </div>
    </div>
  )
}
