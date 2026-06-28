import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, previewAssign, type AssignApplyResult, type AssignItem, type AssignPreviewRow, type Department } from '../api'
import { useAuth } from '../auth'

export default function Assign() {
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin_hr'
  const [rows, setRows] = useState<AssignPreviewRow[]>([])
  // row -> выбранный employee_id (для matched проставляется автоматически)
  const [sel, setSel] = useState<Record<number, number>>({})
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [result, setResult] = useState<AssignApplyResult | null>(null)
  const [deptName, setDeptName] = useState<Record<number, string>>({})
  useEffect(() => {
    if (!isAdmin) return
    api.get<Department[]>('/departments')
      .then((d) => setDeptName(Object.fromEntries(d.map((x) => [x.id, x.name]))))
      .catch(() => { /* контекст отдела не критичен */ })
  }, [isAdmin])

  if (!isAdmin) {
    return (
      <div>
        <div className="pagehead"><h2>Назначение из файла</h2></div>
        <div className="muted">Доступно только роли «Кадры/Админ».</div>
      </div>
    )
  }

  const onFile = async (file: File | undefined) => {
    if (!file) return
    setErr(''); setResult(null)
    setBusy(true)
    try {
      const preview = await previewAssign(file)
      setRows(preview)
      const init: Record<number, number> = {}
      for (const r of preview) if (r.status === 'matched' && r.match) init[r.row] = r.match.employee_id
      setSel(init)
    } catch (e) {
      setErr((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const setRowEmp = (row: number, empId: number | null) =>
    setSel((s) => {
      const n = { ...s }
      if (empId) n[row] = empId
      else delete n[row]
      return n
    })

  const apply = async () => {
    const items: AssignItem[] = rows
      .filter((r) => sel[r.row])
      .map((r) => ({
        employee_id: sel[r.row],
        department_name: r.department_name,
        schedule_code: r.schedule_code,
        cabinet: r.cabinet,
      }))
    if (!items.length) return
    setErr(''); setBusy(true)
    try {
      setResult(await api.post<AssignApplyResult>('/assign/apply', { items }))
      setRows([]); setSel({})
    } catch (e) {
      setErr((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const counts = {
    matched: rows.filter((r) => r.status === 'matched').length,
    ambiguous: rows.filter((r) => r.status === 'ambiguous').length,
    not_found: rows.filter((r) => r.status === 'not_found').length,
  }
  const toApply = Object.keys(sel).length

  return (
    <div>
      <div className="pagehead"><h2>Назначение из файла</h2></div>
      <p className="muted">
        Загрузите лист «ФИО → Отдел / График / Кабинет». ФИО сопоставляются с
        сотрудниками нечётко; проверьте сопоставление, разрешите неоднозначные
        строки и примените. Несуществующие отделы/графики создадутся по имени.
      </p>
      {err && <div className="error">{err}</div>}

      <div className="card panel absrow" style={{ alignItems: 'center' }}>
        <label className="grow"><strong>Файл назначений (.xlsx)</strong></label>
        <input type="file" accept=".xlsx" disabled={busy}
               onChange={(e) => { onFile(e.target.files?.[0]); e.target.value = '' }} />
        {busy && <span className="muted">Обработка…</span>}
      </div>

      {result && (
        <div className="ok-box">
          Обновлено сотрудников: {result.updated}.
          {result.departments_created.length > 0 && <> Созданы отделы: {result.departments_created.join(', ')}.</>}
          {result.schedules_created.length > 0 && <> Созданы графики: {result.schedules_created.join(', ')}.</>}
          {' '}<Link to="/runs">Пересобрать табель →</Link>
        </div>
      )}

      {rows.length > 0 && (
        <>
          <div className="muted" style={{ margin: '8px 0' }}>
            Сопоставлено: {counts.matched} · неоднозначно: {counts.ambiguous} · не найдено: {counts.not_found}
          </div>
          <div className="card panel">
            <table className="grid">
              <thead>
                <tr><th>ФИО из файла</th><th>Отдел</th><th>График</th><th>Кабинет</th><th>Сотрудник</th></tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.row}>
                    <td>{r.raw_name}</td>
                    <td>{r.department_name || '—'}</td>
                    <td>{r.schedule_code || '—'}</td>
                    <td>{r.cabinet || '—'}</td>
                    <td>
                      {r.status === 'matched' && r.match && (
                        <label className="chk">
                          <input type="checkbox" checked={!!sel[r.row]}
                                 onChange={(e) => setRowEmp(r.row, e.target.checked ? r.match!.employee_id : null)} />
                          {r.match.full_name} <span className="muted">({Math.round(r.match.score * 100)}%)</span>
                          <span className="muted"> · тек. отдел: {r.match.department_id ? deptName[r.match.department_id] ?? '—' : 'нет'}</span>
                        </label>
                      )}
                      {r.status === 'ambiguous' && (
                        <select value={sel[r.row] ?? ''}
                                onChange={(e) => setRowEmp(r.row, e.target.value ? Number(e.target.value) : null)}>
                          <option value="">— выберите —</option>
                          {r.candidates.map((c) => (
                            <option key={c.employee_id} value={c.employee_id}>
                              {c.full_name} ({Math.round(c.score * 100)}%){c.department_id && deptName[c.department_id] ? ` — ${deptName[c.department_id]}` : ''}
                            </option>
                          ))}
                        </select>
                      )}
                      {r.status === 'not_found' && <span className="muted">не найден</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div style={{ marginTop: 12 }}>
            <button disabled={busy || toApply === 0} onClick={apply}>
              Применить ({toApply})
            </button>
          </div>
        </>
      )}
    </div>
  )
}
