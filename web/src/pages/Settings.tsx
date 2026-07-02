import { useCallback, useEffect, useState } from 'react'
import { api, type Cabinet, type Threshold } from '../api'
import { useAuth } from '../auth'

export default function Settings() {
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin_hr'

  const [cabs, setCabs] = useState<Cabinet[]>([])
  const [cabEdit, setCabEdit] = useState<Record<string, string>>({})
  const [thr, setThr] = useState<Threshold[]>([])
  const [thrEdit, setThrEdit] = useState<Record<string, string>>({})
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')

  const load = useCallback(async () => {
    setErr('')
    try {
      const [c, t] = await Promise.all([
        api.get<Cabinet[]>('/settings/cabinets'),
        api.get<Threshold[]>('/settings/thresholds'),
      ])
      setCabs(c); setThr(t)
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

      <div className="muted" style={{ marginBottom: 12 }}>
        Отделы и графики — на соседних вкладках раздела «Администрирование».
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
