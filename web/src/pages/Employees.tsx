import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, type Department, type Employee, type Schedule } from '../api'
import { useAuth } from '../auth'

export default function Employees() {
  const { user } = useAuth()
  const nav = useNavigate()
  const isAdmin = user?.role === 'admin_hr'

  const [rows, setRows] = useState<Employee[]>([])
  const [depts, setDepts] = useState<Department[]>([])
  const [scheds, setScheds] = useState<Schedule[]>([])
  const [q, setQ] = useState('')
  const [deptFilter, setDeptFilter] = useState('')
  const [noSchedule, setNoSchedule] = useState(false)
  const [noDept, setNoDept] = useState(false)
  const [sel, setSel] = useState<Set<number>>(new Set())
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')
  const [loading, setLoading] = useState(true)

  // панель присвоения
  const [aDept, setADept] = useState(false)
  const [deptVal, setDeptVal] = useState('')
  const [aCab, setACab] = useState(false)
  const [cabVal, setCabVal] = useState('')
  const [aSched, setASched] = useState(false)
  const [schedVal, setSchedVal] = useState('')

  const deptName = useMemo(() => Object.fromEntries(depts.map((d) => [d.id, d.name])), [depts])
  const schedCode = useMemo(() => Object.fromEntries(scheds.map((s) => [s.id, s.code])), [scheds])
  const stats = useMemo(() => ({
    active: rows.filter((e) => e.is_active).length,
    noDept: rows.filter((e) => !e.department_id).length,
    noSchedule: rows.filter((e) => !e.schedule_id).length,
    lez: rows.filter((e) => e.lez_controlled).length,
  }), [rows])

  const load = async () => {
    setLoading(true)
    setErr('')
    try {
      const params = new URLSearchParams({ limit: '5000' })
      if (q) params.set('q', q)
      if (deptFilter) params.set('department_id', deptFilter)
      if (noSchedule) params.set('no_schedule', 'true')
      if (noDept) params.set('no_department', 'true')
      const [emps, ds, ss] = await Promise.all([
        api.get<Employee[]>(`/employees?${params}`),
        api.get<Department[]>('/departments'),
        api.get<Schedule[]>('/schedules'),
      ])
      setRows(emps)
      setDepts(ds)
      setScheds(ss)
      setSel(new Set())
    } catch (e) {
      setErr((e as Error).message)
    } finally {
      setLoading(false)
    }
  }
  // Загрузка один раз при монтировании; дальше вручную («Показать»/«Применить»).
  // Через ref на актуальный load — чтобы эффект не зависел от load и не
  // перезапрашивал список при наборе текста в поиске.
  const loadRef = useRef(load)
  loadRef.current = load
  useEffect(() => {
    loadRef.current()
  }, [])

  const search = (e: FormEvent) => {
    e.preventDefault()
    load()
  }
  const toggle = (id: number) =>
    setSel((s) => {
      const n = new Set(s)
      if (n.has(id)) n.delete(id)
      else n.add(id)
      return n
    })
  const allChecked = rows.length > 0 && rows.every((r) => sel.has(r.id))
  const toggleAll = () => setSel(allChecked ? new Set() : new Set(rows.map((r) => r.id)))

  const apply = async () => {
    if (!sel.size) return
    const payload: Record<string, unknown> = { ids: [...sel] }
    if (aDept) payload.department_id = deptVal ? Number(deptVal) : null
    if (aCab) payload.cabinet = cabVal || null
    if (aSched) payload.schedule_id = schedVal ? Number(schedVal) : null
    if (Object.keys(payload).length === 1) {
      setErr('Отметьте хотя бы одно поле для присвоения')
      return
    }
    setErr('')
    setMsg('')
    try {
      const r = await api.patch<{ updated: number }>('/employees/bulk', payload)
      setMsg(`Обновлено сотрудников: ${r.updated}`)
      await load()
    } catch (e) {
      setErr((e as Error).message)
    }
  }

  return (
    <div>
      <div className="pagehead">
        <h2>Сотрудники <span className="muted">({rows.length})</span></h2>
        <form onSubmit={search} className="searchbar">
          <input placeholder="Поиск по ФИО" value={q} onChange={(e) => setQ(e.target.value)} />
          <select value={deptFilter} onChange={(e) => setDeptFilter(e.target.value)}>
            <option value="">Все отделы</option>
            {depts.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select>
          <label className="chk"><input type="checkbox" checked={noSchedule}
            onChange={(e) => setNoSchedule(e.target.checked)} /> без графика</label>
          <label className="chk"><input type="checkbox" checked={noDept}
            onChange={(e) => setNoDept(e.target.checked)} /> без отдела</label>
          <button>Показать</button>
        </form>
      </div>
      {err && <div className="error">{err}</div>}
      {msg && <div className="ok-box">{msg}</div>}

      <div className="metric-grid">
        <div className="metric-card">
          <div className="metric-label">Активные сотрудники</div>
          <div className="metric-value">{stats.active}</div>
          <div className="metric-note">в текущем списке</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">Без отдела</div>
          <div className="metric-value">{stats.noDept}</div>
          <div className="metric-note">нужно назначить подразделение</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">Без графика</div>
          <div className="metric-value">{stats.noSchedule}</div>
          <div className="metric-note">не попадут в норму корректно</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">Контроль ЛЭЗ</div>
          <div className="metric-value">{stats.lez}</div>
          <div className="metric-note">сверка проходной</div>
        </div>
      </div>

      {noDept && isAdmin && (
        <div className="muted" style={{ marginBottom: 8 }}>
          Очередь «без отдела». Назначьте отдел: отметьте строки и панель выше, либо{' '}
          <Link to="/assign">массово из файла</Link>.
        </div>
      )}

      {isAdmin && sel.size > 0 && (
        <div className="card panel assignbar">
          <strong>Выбрано: {sel.size}</strong>
          <label className="chk"><input type="checkbox" checked={aDept} onChange={(e) => setADept(e.target.checked)} /> Отдел</label>
          <select disabled={!aDept} value={deptVal} onChange={(e) => setDeptVal(e.target.value)}>
            <option value="">(очистить)</option>
            {depts.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select>
          <label className="chk"><input type="checkbox" checked={aCab} onChange={(e) => setACab(e.target.checked)} /> Кабинет</label>
          <input disabled={!aCab} value={cabVal} onChange={(e) => setCabVal(e.target.value)} placeholder="(пусто = очистить)" style={{ width: 130 }} />
          <label className="chk"><input type="checkbox" checked={aSched} onChange={(e) => setASched(e.target.checked)} /> График</label>
          <select disabled={!aSched} value={schedVal} onChange={(e) => setSchedVal(e.target.value)}>
            <option value="">(очистить)</option>
            {scheds.map((s) => <option key={s.id} value={s.id}>{s.code}</option>)}
          </select>
          <button onClick={apply}>Применить</button>
        </div>
      )}

      {loading ? <div className="muted">Загрузка…</div> : (
        <table className="grid">
          <thead>
            <tr>
              {isAdmin && <th style={{ width: 30 }}><input type="checkbox" checked={allChecked} onChange={toggleAll} /></th>}
              <th>ФИО</th><th>Отдел</th><th>Кабинет</th><th>График</th><th>Контроль ЛЭЗ</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((e) => (
              <tr key={e.id} className={sel.has(e.id) ? 'selrow' : ''}>
                {isAdmin && <td><input type="checkbox" checked={sel.has(e.id)} onChange={() => toggle(e.id)} /></td>}
                <td><button className="link" onClick={() => nav(`/employees/${e.id}`)}>{e.full_name}</button></td>
                <td>{e.department_id ? deptName[e.department_id] ?? '—' : '—'}</td>
                <td>{e.cabinet || '—'}</td>
                <td className={!e.schedule_id ? 'muted' : ''}>{e.schedule_id ? schedCode[e.schedule_id] ?? '—' : 'нет'}</td>
                <td>{e.lez_controlled ? 'да' : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
