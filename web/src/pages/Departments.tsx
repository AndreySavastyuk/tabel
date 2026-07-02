import { Fragment, useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, type Department, type Employee, type Schedule } from '../api'
import { useAuth } from '../auth'

type Group = { id: number | null; name: string; emps: Employee[] }
const keyOf = (id: number | null) => (id == null ? 'none' : String(id))

export default function Departments() {
  const { user } = useAuth()
  const nav = useNavigate()

  const [depts, setDepts] = useState<Department[]>([])
  const [emps, setEmps] = useState<Employee[]>([])
  const [scheds, setScheds] = useState<Schedule[]>([])
  const [err, setErr] = useState('')
  const [loading, setLoading] = useState(true)

  // фильтры / быстрый поиск
  const [deptQuery, setDeptQuery] = useState('')
  const [empQuery, setEmpQuery] = useState('')
  const [activeOnly, setActiveOnly] = useState(false)
  const [nonEmptyOnly, setNonEmptyOnly] = useState(false)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  // Руководитель отдела видит только свой отдел (бэкенд так же скоупит /employees).
  const scopeDept = user?.role === 'dept_head' ? user.department_id ?? -1 : null

  const load = useCallback(async () => {
    try {
      const [ds, es, ss] = await Promise.all([
        api.get<Department[]>('/departments'),
        api.get<Employee[]>('/employees?limit=5000'),
        api.get<Schedule[]>('/schedules'),
      ])
      setDepts(ds)
      setEmps(es)
      setScheds(ss)
    } catch (e) {
      setErr((e as Error).message)
    } finally {
      setLoading(false)
    }
  }, [])
  useEffect(() => { load() }, [load])

  // Редактирование (только Кадры/Админ): переименование в раскрытой карточке
  // отдела + добавление нового отдела. Список остаётся свёрнутым по умолчанию.
  const isAdmin = user?.role === 'admin_hr'
  const [newDept, setNewDept] = useState('')
  const [renameId, setRenameId] = useState<number | null>(null)
  const [renameVal, setRenameVal] = useState('')
  const [busy, setBusy] = useState(false)

  const addDept = async () => {
    if (!newDept.trim()) return
    setBusy(true); setErr('')
    try { await api.post('/departments', { name: newDept.trim() }); setNewDept(''); await load() }
    catch (e) { setErr((e as Error).message) } finally { setBusy(false) }
  }
  const saveRename = async (d: Department) => {
    setBusy(true); setErr('')
    try {
      await api.patch(`/departments/${d.id}`, { name: renameVal.trim(), parent_id: d.parent_id ?? null })
      setRenameId(null); await load()
    } catch (e) { setErr((e as Error).message) } finally { setBusy(false) }
  }

  const schedCode = useMemo(
    () => Object.fromEntries(scheds.map((s) => [s.id, s.code])),
    [scheds],
  )

  // сотрудники, сгруппированные по отделу (null = без отдела)
  const byDept = useMemo(() => {
    const m = new Map<number | null, Employee[]>()
    for (const e of emps) {
      const k = e.department_id ?? null
      const arr = m.get(k)
      if (arr) arr.push(e)
      else m.set(k, [e])
    }
    return m
  }, [emps])

  // отделы (+ «без отдела») с полными списками сотрудников
  const groups: Group[] = useMemo(() => {
    const gs: Group[] = depts
      .filter((d) => scopeDept == null || d.id === scopeDept)
      .map((d) => ({ id: d.id, name: d.name, emps: byDept.get(d.id) ?? [] }))
    if (scopeDept == null) {
      const orphans = byDept.get(null) ?? []
      if (orphans.length) gs.push({ id: null, name: 'Без отдела', emps: orphans })
    }
    return gs
  }, [depts, byDept, scopeDept])

  const deptTerm = deptQuery.trim().toLowerCase()
  const empTerm = empQuery.trim().toLowerCase()
  const searchMode = empTerm.length > 0

  // видимые группы + отфильтрованные для показа сотрудники
  const view = useMemo(() => {
    const keep = (e: Employee) =>
      (!activeOnly || e.is_active) &&
      (!empTerm || e.full_name.toLowerCase().includes(empTerm))
    return groups
      .map((g) => ({ g, list: g.emps.filter(keep) }))
      .filter(({ g, list }) => {
        if (deptTerm && !g.name.toLowerCase().includes(deptTerm)) return false
        if (searchMode) return list.length > 0 // в режиме поиска — только отделы с совпадениями
        if (nonEmptyOnly && g.emps.length === 0) return false
        return true
      })
  }, [groups, deptTerm, empTerm, activeOnly, nonEmptyOnly, searchMode])

  const totalShownEmp = useMemo(() => view.reduce((s, { g }) => s + g.emps.length, 0), [view])
  const totalMatched = useMemo(() => view.reduce((s, { list }) => s + list.length, 0), [view])

  const toggle = (id: number | null) =>
    setExpanded((s) => {
      const n = new Set(s)
      const k = keyOf(id)
      if (n.has(k)) n.delete(k)
      else n.add(k)
      return n
    })
  const isOpen = (id: number | null) => searchMode || expanded.has(keyOf(id))

  return (
    <div>
      <div className="pagehead">
        <h2>
          Отделы <span className="muted">({view.length})</span>
        </h2>
        <div className="searchbar">
          <input
            placeholder="Поиск по отделу"
            value={deptQuery}
            onChange={(e) => setDeptQuery(e.target.value)}
          />
          <input
            placeholder="Поиск по сотруднику"
            value={empQuery}
            onChange={(e) => setEmpQuery(e.target.value)}
          />
          <label className="chk">
            <input
              type="checkbox"
              checked={activeOnly}
              onChange={(e) => setActiveOnly(e.target.checked)}
            />{' '}
            только активные
          </label>
          <label className="chk">
            <input
              type="checkbox"
              checked={nonEmptyOnly}
              onChange={(e) => setNonEmptyOnly(e.target.checked)}
            />{' '}
            непустые
          </label>
        </div>
      </div>

      {err && <div className="error">{err}</div>}

      {loading ? (
        <div className="muted">Загрузка…</div>
      ) : (
        <>
          {isAdmin && (
            <div className="searchbar" style={{ marginBottom: 10 }}>
              <input placeholder="Новый отдел" value={newDept}
                     onChange={(e) => setNewDept(e.target.value)} />
              <button disabled={busy || !newDept.trim()} onClick={addDept}>Добавить отдел</button>
            </div>
          )}
          <div className="muted" style={{ marginBottom: 8 }}>
            {searchMode
              ? `Найдено сотрудников: ${totalMatched} в ${view.length} отд.`
              : `Сотрудников в показанных отделах: ${totalShownEmp}`}
          </div>
          <table className="grid">
            <thead>
              <tr>
                <th style={{ width: 34 }}></th>
                <th>Отдел</th>
                <th style={{ width: 120 }}>Сотрудников</th>
                <th style={{ width: 100 }}>Активных</th>
              </tr>
            </thead>
            <tbody>
              {view.map(({ g, list }) => {
                const open = isOpen(g.id)
                const hasEmps = g.emps.length > 0
                const active = g.emps.filter((e) => e.is_active).length
                return (
                  <Fragment key={keyOf(g.id)}>
                    <tr className={open ? 'selrow' : ''}>
                      <td>
                        <button
                          className="link"
                          style={{ padding: '2px 9px' }}
                          disabled={!hasEmps}
                          onClick={() => toggle(g.id)}
                          aria-label={open ? 'Свернуть' : 'Раскрыть'}
                        >
                          {open ? '▾' : '▸'}
                        </button>
                      </td>
                      <td>
                        {hasEmps ? (
                          <button className="link" onClick={() => toggle(g.id)}>
                            {g.name}
                          </button>
                        ) : (
                          <span className="muted">{g.name}</span>
                        )}
                      </td>
                      <td>{g.emps.length}</td>
                      <td className="muted">{active}</td>
                    </tr>
                    {open && (
                      <tr>
                        <td></td>
                        <td colSpan={3} style={{ padding: 0 }}>
                          {isAdmin && g.id != null && (
                            <div className="searchbar" style={{ padding: '8px 12px' }}>
                              {renameId === g.id ? (
                                <>
                                  <input value={renameVal} onChange={(e) => setRenameVal(e.target.value)} />
                                  <button disabled={busy || !renameVal.trim()}
                                          onClick={() => saveRename(depts.find((x) => x.id === g.id)!)}>Сохранить</button>
                                  <button className="ghost" onClick={() => setRenameId(null)}>Отмена</button>
                                </>
                              ) : (
                                <button className="ghost"
                                        onClick={() => { setRenameId(g.id); setRenameVal(g.name) }}>Переименовать отдел</button>
                              )}
                            </div>
                          )}
                          {list.length === 0 ? (
                            <div className="muted" style={{ padding: '8px 12px' }}>
                              Нет сотрудников по текущему фильтру
                            </div>
                          ) : (
                            <table className="grid inner">
                              <thead>
                                <tr>
                                  <th>ФИО</th>
                                  <th style={{ width: 120 }}>Кабинет</th>
                                  <th style={{ width: 150 }}>График</th>
                                  <th style={{ width: 120 }}>Статус</th>
                                </tr>
                              </thead>
                              <tbody>
                                {list.map((e) => (
                                  <tr key={e.id}>
                                    <td>
                                      <button className="link" onClick={() => nav(`/employees/${e.id}`)}>
                                        {e.full_name}
                                      </button>
                                    </td>
                                    <td>{e.cabinet || '—'}</td>
                                    <td className={!e.schedule_id ? 'muted' : ''}>
                                      {e.schedule_id ? schedCode[e.schedule_id] ?? '—' : 'нет'}
                                    </td>
                                    <td className={e.is_active ? '' : 'muted'}>
                                      {e.is_active ? 'активен' : 'неактивен'}
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          )}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                )
              })}
              {view.length === 0 && (
                <tr>
                  <td colSpan={4} className="muted" style={{ padding: 12 }}>
                    Ничего не найдено
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </>
      )}
    </div>
  )
}
