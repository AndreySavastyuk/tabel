import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, type OvertimeReport } from '../api'

export default function Overtime() {
  const nav = useNavigate()
  const [data, setData] = useState<OvertimeReport | null>(null)
  const [year, setYear] = useState<number | null>(null)
  const [trackedOnly, setTrackedOnly] = useState(true)
  const [err, setErr] = useState('')

  const load = useCallback(async (y?: number) => {
    setErr('')
    try {
      const d = await api.get<OvertimeReport>(`/overtime${y ? `?year=${y}` : ''}`)
      setData(d)
      setYear(d.year)
    } catch (e) {
      setErr((e as Error).message)
    }
  }, [])
  useEffect(() => { load() }, [load])

  const rows = (data?.rows ?? []).filter((r) => !trackedOnly || r.overtime_tracked)
  const totals = rows.reduce(
    (a, r) => ({ q1: a.q1 + r.q1, q2: a.q2 + r.q2, q3: a.q3 + r.q3, q4: a.q4 + r.q4, total: a.total + r.total }),
    { q1: 0, q2: 0, q3: 0, q4: 0, total: 0 })

  return (
    <div>
      <div className="pagehead">
        <h2>Переработки <span className="muted">({rows.length})</span></h2>
        <div className="searchbar">
          <label>Год{' '}
            <select value={year ?? ''} onChange={(e) => load(Number(e.target.value))}>
              {(data?.years ?? []).map((y) => <option key={y} value={y}>{y}</option>)}
            </select>
          </label>
          <label className="chk">
            <input type="checkbox" checked={trackedOnly} onChange={(e) => setTrackedOnly(e.target.checked)} /> только с учётом переработок
          </label>
        </div>
      </div>
      {err && <div className="error">{err}</div>}
      <div className="metric-grid">
        <div className="metric-card">
          <div className="metric-label">Сотрудников в отчёте</div>
          <div className="metric-value">{rows.length}</div>
          <div className="metric-note">{trackedOnly ? 'только с учётом переработок' : 'все сотрудники'}</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">Итого за год</div>
          <div className="metric-value">{totals.total.toFixed(2)} ч</div>
          <div className="metric-note">по выбранному году</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">Самый загруженный квартал</div>
          <div className="metric-value">
            {[
              ['Q1', totals.q1], ['Q2', totals.q2], ['Q3', totals.q3], ['Q4', totals.q4],
            ].sort((a, b) => Number(b[1]) - Number(a[1]))[0][0]}
          </div>
          <div className="metric-note">по сумме часов</div>
        </div>
      </div>
      <p className="muted" style={{ maxWidth: 900 }}>
        Переработка за квартал — сумма часов сверх длительности смены по дням квартала (актуальный прогон).
        Отметьте «учёт переработок» в карточке сотрудника, чтобы он попал в этот раздел.
      </p>
      <table className="grid">
        <thead>
          <tr><th>ФИО</th><th>Отдел</th><th>Учёт</th><th>Q1</th><th>Q2</th><th>Q3</th><th>Q4</th><th>Итого, ч</th></tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.employee_id}>
              <td><button className="link" onClick={() => nav(`/employees/${r.employee_id}`)}>{r.employee_name}</button></td>
              <td>{r.dept_name || '—'}</td>
              <td>{r.overtime_tracked ? 'да' : <span className="muted">—</span>}</td>
              <td>{r.q1 ? r.q1.toFixed(2) : '—'}</td>
              <td>{r.q2 ? r.q2.toFixed(2) : '—'}</td>
              <td>{r.q3 ? r.q3.toFixed(2) : '—'}</td>
              <td>{r.q4 ? r.q4.toFixed(2) : '—'}</td>
              <td><b>{r.total.toFixed(2)}</b></td>
            </tr>
          ))}
          {!rows.length && <tr><td colSpan={8} className="muted">Нет переработок за выбранный год.</td></tr>}
          {rows.length > 0 && (
            <tr className="totalrow">
              <td colSpan={3} style={{ textAlign: 'right' }}>Итого:</td>
              <td>{totals.q1.toFixed(2)}</td><td>{totals.q2.toFixed(2)}</td>
              <td>{totals.q3.toFixed(2)}</td><td>{totals.q4.toFixed(2)}</td>
              <td>{totals.total.toFixed(2)}</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}
