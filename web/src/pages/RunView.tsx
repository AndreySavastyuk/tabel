import { Fragment, useCallback, useEffect, useMemo, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { api, devLabel, downloadExport, type DayRecord, type Period, type Run } from '../api'
import { useAuth } from '../auth'

type Tab = 'depts' | 'dev' | 'acc' | 'norms' | 'late'
const dkey = (d: string) => {
  const [a, b, c] = d.split('.')
  return `${c}${b}${a}`
}
const fmtPct = (p: number) => `${Math.round(p)}%`

export default function RunView() {
  const { id } = useParams()
  const runId = Number(id)
  const nav = useNavigate()
  const [run, setRun] = useState<Run | null>(null)
  const [recs, setRecs] = useState<DayRecord[]>([])
  const [periods, setPeriods] = useState<Period[] | null>(null)
  const [tab, setTab] = useState<Tab>('depts')
  const [err, setErr] = useState('')
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin_hr'
  const [busy, setBusy] = useState(false)

  const setFinal = async (makeFinal: boolean) => {
    setBusy(true)
    setErr('')
    try {
      setRun(await api.post<Run>(`/runs/${runId}/${makeFinal ? 'finalize' : 'unfinalize'}`, {}))
    } catch (e) {
      setErr((e as Error).message)
    } finally {
      setBusy(false)
    }
  }
  const exportXlsx = () => downloadExport(runId).catch((e) => setErr((e as Error).message))

  const loadRun = useCallback(async () => {
    try {
      setRun(await api.get<Run>(`/runs/${runId}`))
    } catch (e) {
      setErr((e as Error).message)
    }
  }, [runId])

  useEffect(() => {
    loadRun()
  }, [loadRun])

  // поллинг, пока прогон не готов
  useEffect(() => {
    if (run && (run.status === 'queued' || run.status === 'running')) {
      const t = setInterval(loadRun, 2000)
      return () => clearInterval(t)
    }
  }, [run, loadRun])

  // данные результата
  useEffect(() => {
    if (run?.status !== 'done') return
    ;(async () => {
      try {
        setRecs(await api.get<DayRecord[]>(`/runs/${runId}/day-records?limit=20000`))
      } catch (e) {
        setErr((e as Error).message)
      }
      try {
        setPeriods(await api.get<Period[]>(`/runs/${runId}/periods`))
      } catch {
        setPeriods(null) // нет прав (руководитель) — своды скрыты
      }
    })()
  }, [run?.status, runId])

  const deptGroups = useMemo(() => {
    const g = new Map<string, DayRecord[]>()
    for (const r of recs) {
      const dept = r.dept_name || 'Без отдела'
      const key = r.cabinet ? `${dept} — ${r.cabinet}` : `Отдел ${dept}`
      ;(g.get(key) ?? g.set(key, []).get(key)!).push(r)
    }
    return [...g.entries()].sort((a, b) => a[0].localeCompare(b[0], 'ru'))
  }, [recs])

  const deviations = useMemo(
    () => recs.filter((r) => r.deviations.length)
      .sort((a, b) => (a.employee_name ?? '').localeCompare(b.employee_name ?? '', 'ru') || dkey(a.work_date).localeCompare(dkey(b.work_date))),
    [recs],
  )

  if (!run) return <div className="muted">Загрузка…</div>

  const tabs: { k: Tab; label: string; show: boolean }[] = [
    { k: 'depts', label: 'По отделам', show: true },
    { k: 'dev', label: `Отклонения (${deviations.length})`, show: true },
    { k: 'acc', label: 'Бухгалтерия', show: !!periods },
    { k: 'norms', label: 'Нормы', show: !!periods },
    { k: 'late', label: 'Опоздания и переработки', show: !!periods },
  ]

  return (
    <div>
      <div className="pagehead">
        <h2>
          Прогон №{run.id}
          {run.period_label && <span className="muted"> · {run.period_label}</span>}
          <span className="muted"> · {run.status === 'done' ? 'готов' : run.status}</span>
          {run.is_final && <span className="badge st-done" style={{ marginLeft: 8 }}>★ финальный</span>}
        </h2>
        <div className="searchbar">
          <button className="ghost" onClick={() => nav('/runs')}>← К прогонам</button>
          {run.status === 'done' && <button onClick={exportXlsx}>Скачать xlsx</button>}
          {isAdmin && run.status === 'done' && (
            run.is_final
              ? <button className="ghost" disabled={busy} onClick={() => setFinal(false)}>Снять финальность</button>
              : <button disabled={busy} onClick={() => setFinal(true)}>Утвердить (финальный)</button>
          )}
        </div>
      </div>
      {err && <div className="error">{err}</div>}

      {run.status !== 'done' ? (
        <div className="card">
          {run.status === 'failed'
            ? <div className="error">Ошибка: {run.error_text}</div>
            : <div className="muted">Идёт расчёт… (обновляется автоматически)</div>}
        </div>
      ) : (
        <>
          <div className="tabs">
            {tabs.filter((t) => t.show).map((t) => (
              <button key={t.k} className={tab === t.k ? 'tab active' : 'tab'} onClick={() => setTab(t.k)}>
                {t.label}
              </button>
            ))}
          </div>

          {tab === 'depts' && deptGroups.map(([title, rows]) => <DeptTable key={title} title={title} rows={rows} />)}
          {tab === 'dev' && <Deviations rows={deviations} />}
          {tab === 'acc' && periods && <Accounting rows={periods} />}
          {tab === 'norms' && periods && <Norms rows={periods} />}
          {tab === 'late' && periods && <Lateness rows={periods} />}
        </>
      )}
    </div>
  )
}

function DeptTable({ title, rows }: { title: string; rows: DayRecord[] }) {
  const byEmp = useMemo(() => {
    const m = new Map<string, DayRecord[]>()
    for (const r of rows) {
      const n = r.employee_name ?? '?'
      ;(m.get(n) ?? m.set(n, []).get(n)!).push(r)
    }
    return [...m.entries()].sort((a, b) => a[0].localeCompare(b[0], 'ru'))
  }, [rows])

  return (
    <div className="deptblock">
      <h3>{title}</h3>
      <table className="grid">
        <thead>
          <tr><th>ФИО</th><th>Дата</th><th>Вход</th><th>Выход</th><th>Обед</th><th>Часы</th></tr>
        </thead>
        <tbody>
          {byEmp.map(([name, drs]) => {
            const sorted = [...drs].sort((a, b) => dkey(a.work_date).localeCompare(dkey(b.work_date)))
            let total = 0
            return (
              <Fragment key={name}>
                {sorted.map((r, i) => {
                  const hasBoth = r.entry && r.exit
                  const eff = r.effective_hours ?? r.worked_hours   // за вычетом отлучек
                  if (hasBoth) total += eff
                  return (
                    <tr key={name + i}>
                      <td>{name}</td>
                      <td className={r.is_weekend ? 'we' : ''}>{r.work_date}</td>
                      <td className={!r.entry ? 'miss' : r.start_fixed ? 'fix' : r.entry_source === 'LEZ' ? 'lez' : ''}>{r.entry ?? '—'}</td>
                      <td className={!r.exit ? 'miss' : r.exit_source === 'LEZ' ? 'lez' : ''}>{r.exit ?? '—'}</td>
                      <td>{r.lunch_deducted ? r.lunch_deducted.toFixed(2) : '0'}</td>
                      <td className={!hasBoth ? 'miss' : ''}>
                        {hasBoth ? eff.toFixed(2) : '—'}
                        {r.deduct_minutes ? <span className="muted" title={`вычтено ${r.deduct_minutes} мин вне территории`}> −{(r.deduct_minutes / 60).toFixed(1)}ч</span> : null}
                      </td>
                    </tr>
                  )
                })}
                <tr className="totalrow">
                  <td colSpan={5} style={{ textAlign: 'right' }}>Итого:</td>
                  <td>{total.toFixed(2)}</td>
                </tr>
              </Fragment>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function Deviations({ rows }: { rows: DayRecord[] }) {
  if (!rows.length) return <div className="ok-box">Отклонений не найдено</div>
  return (
    <table className="grid">
      <thead>
        <tr><th>ФИО</th><th>Дата</th><th>Внутр. вход</th><th>Внутр. выход</th><th>ЛЭЗ вход</th><th>ЛЭЗ выход</th><th>Часы</th><th>Отклонения</th></tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i}>
            <td>{r.employee_name}</td>
            <td className={r.is_weekend ? 'we' : ''}>{r.work_date}</td>
            <td>{r.int_entry ?? '-'}</td>
            <td>{r.int_exit ?? '-'}</td>
            <td>{r.lez_entry ?? '-'}</td>
            <td>{r.lez_exit ?? '-'}</td>
            <td>{r.entry && r.exit ? (r.effective_hours ?? r.worked_hours).toFixed(2) : '-'}</td>
            <td className="bad">{r.deviations.map(devLabel).join('; ')}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function Accounting({ rows }: { rows: Period[] }) {
  const sorted = [...rows].sort((a, b) =>
    (a.period_norm > 0 ? 0 : 1) - (b.period_norm > 0 ? 0 : 1) ||
    (a.period_norm > 0 ? a.percent - b.percent : 0) ||
    (a.employee_name ?? '').localeCompare(b.employee_name ?? '', 'ru'))
  return (
    <table className="grid">
      <thead>
        <tr><th>ФИО</th><th>Отдел</th><th>Отработано, ч</th><th>Зачёт отсут., ч</th><th>Норма, ч</th><th>% отработано</th><th>Группа</th></tr>
      </thead>
      <tbody>
        {sorted.map((p) => {
          const low = p.period_norm > 0 && p.percent < 50
          return (
            <tr key={p.employee_id} className={low ? 'lowrow' : ''}>
              <td>{p.employee_name}</td>
              <td>{p.dept_name || 'Без отдела'}</td>
              <td>{p.worked_total.toFixed(2)}{p.deducted_hours ? <span className="muted" title="вычтено времени вне территории"> (−{p.deducted_hours.toFixed(1)}ч)</span> : null}</td>
              <td>{(p.credited_total - p.worked_total).toFixed(2)}</td>
              <td>{p.period_norm > 0 ? p.period_norm.toFixed(0) : '—'}</td>
              <td>{p.period_norm > 0 ? fmtPct(p.percent) : <span className="warn-txt">нет нормы</span>}</td>
              <td>{p.bucket}</td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

function Norms({ rows }: { rows: Period[] }) {
  const sorted = [...rows].sort((a, b) =>
    (a.dept_name ?? '').localeCompare(b.dept_name ?? '', 'ru') ||
    (a.employee_name ?? '').localeCompare(b.employee_name ?? '', 'ru'))
  return (
    <table className="grid">
      <thead>
        <tr><th>ФИО</th><th>Отдел</th><th>График</th><th>Отработано, ч</th><th>Зачтено, ч</th><th>Норма, ч</th><th>+/- к норме</th></tr>
      </thead>
      <tbody>
        {sorted.map((p) => (
          <tr key={p.employee_id}>
            <td>{p.employee_name}</td>
            <td>{p.dept_name || 'Без отдела'}</td>
            <td>{p.schedule_code || '—'}</td>
            <td>{p.worked_total.toFixed(2)}{p.deducted_hours ? <span className="muted" title="вычтено времени вне территории"> (−{p.deducted_hours.toFixed(1)}ч)</span> : null}</td>
            <td>{p.credited_total.toFixed(2)}</td>
            <td>{p.period_norm > 0 ? p.period_norm.toFixed(0) : '—'}</td>
            <td>{p.period_norm > 0 ? (p.credited_total - p.period_norm).toFixed(2) : '—'}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function Lateness({ rows }: { rows: Period[] }) {
  const items = rows.filter((p) => p.late_count > 0 || p.overtime_total > 0)
    .sort((a, b) => b.late_count - a.late_count || b.overtime_total - a.overtime_total)
  if (!items.length) return <div className="ok-box">Опозданий и переработок не найдено (графики не заданы?)</div>
  return (
    <table className="grid">
      <thead>
        <tr><th>ФИО</th><th>Отдел</th><th>Опозданий, дней</th><th>Σ опозданий, мин</th><th>Переработка, ч</th></tr>
      </thead>
      <tbody>
        {items.map((p) => (
          <tr key={p.employee_id}>
            <td>{p.employee_name}</td>
            <td>{p.dept_name || 'Без отдела'}</td>
            <td className={p.late_count ? 'warn-cell' : ''}>{p.late_count}</td>
            <td>{p.late_minutes}</td>
            <td className={p.overtime_total ? 'warn-cell' : ''}>{p.overtime_total.toFixed(2)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
