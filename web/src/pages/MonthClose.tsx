import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  api, devLabel, downloadExport, PERIOD_STATUS_LABEL,
  type ClosingSummary, type MonthPeriod,
} from '../api'
import { useAuth } from '../auth'

export default function MonthClose() {
  const nav = useNavigate()
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin_hr'
  const [periods, setPeriods] = useState<MonthPeriod[]>([])
  const [period, setPeriod] = useState('')
  const [sum, setSum] = useState<ClosingSummary | null>(null)
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)

  const loadPeriods = useCallback(async () => {
    const ps = await api.get<MonthPeriod[]>('/periods')
    setPeriods(ps)
    setPeriod((cur) => cur || (ps[0]?.period ?? ''))
  }, [])

  useEffect(() => { loadPeriods().catch((e) => setErr((e as Error).message)) }, [loadPeriods])

  const load = useCallback(async () => {
    if (!period) { setSum(null); return }
    setErr('')
    try {
      setSum(await api.get<ClosingSummary>(`/periods/${period}/closing-summary`))
    } catch (e) {
      setErr((e as Error).message)
    }
  }, [period])

  useEffect(() => { load() }, [load])

  // поллинг, пока активный прогон считается
  useEffect(() => {
    if (sum?.run && (sum.run.status === 'queued' || sum.run.status === 'running')) {
      const t = setInterval(load, 2000)
      return () => clearInterval(t)
    }
  }, [sum, load])

  const act = async (path: string, okMsg: string) => {
    setBusy(true); setErr(''); setMsg('')
    try {
      await api.post(`/periods/${period}/${path}`, {})
      setMsg(okMsg)
      await load()
      await loadPeriods()
    } catch (e) {
      setErr((e as Error).message)
    } finally {
      setBusy(false)
    }
  }
  const exportXlsx = () => sum?.run && downloadExport(sum.run.id).catch((e) => setErr((e as Error).message))
  const blockers = sum?.checklist.reduce((n, c) => n + (!c.ok && c.blocking ? c.count : 0), 0) ?? 0
  const warnings = sum?.checklist.reduce((n, c) => n + (!c.ok && !c.blocking ? c.count : 0), 0) ?? 0

  return (
    <div>
      <div className="pagehead">
        <h2>Закрытие месяца</h2>
        <div className="searchbar">
          <select value={period} onChange={(e) => setPeriod(e.target.value)}>
            {periods.map((p) => (
              <option key={p.period} value={p.period}>{p.period} · {PERIOD_STATUS_LABEL[p.status]}</option>
            ))}
          </select>
          {sum && (
            <span className={`badge st-${sum.status === 'closed' ? 'done' : 'queued'}`}>
              {PERIOD_STATUS_LABEL[sum.status]}
            </span>
          )}
        </div>
      </div>
      {err && <div className="error">{err}</div>}
      {msg && <div className="ok-box">{msg}</div>}
      {!periods.length && (
        <div className="muted">Нет периодов. Постройте прогон с указанием месяца на «Прогонах».</div>
      )}

      {sum && (
        <>
          <div className="metric-grid">
            <div className="metric-card">
              <div className="metric-label">Период</div>
              <div className="metric-value">{sum.period}</div>
              <div className="metric-note">{PERIOD_STATUS_LABEL[sum.status]}</div>
            </div>
            <div className="metric-card">
              <div className="metric-label">Активный прогон</div>
              <div className="metric-value">{sum.run ? `№${sum.run.id}` : 'нет'}</div>
              <div className="metric-note">{sum.run?.status ?? 'постройте табель'}</div>
            </div>
            <div className="metric-card">
              <div className="metric-label">Данные</div>
              <div className="metric-value">{sum.run?.n_employees ?? '—'}</div>
              <div className="metric-note">{sum.run?.n_day_records ?? '—'} дневных записей</div>
            </div>
            <div className="metric-card">
              <div className="metric-label">Готовность</div>
              <div className="metric-value">{sum.export_ready ? 'Готово' : blockers}</div>
              <div className="metric-note">{sum.export_ready ? 'можно закрывать' : `блокеров, предупреждений: ${warnings}`}</div>
            </div>
          </div>

          <div className="card panel">
            <div className="absrow">
              <span><b>Активный прогон:</b> {sum.run ? `№${sum.run.id} (${sum.run.status})` : 'нет'}</span>
              {sum.run && <span><b>Сотрудников:</b> {sum.run.n_employees ?? '—'}</span>}
              {sum.run && <span><b>Дней:</b> {sum.run.n_day_records ?? '—'}</span>}
              {sum.run?.is_final && <span className="badge st-done">★ финальный</span>}
            </div>
            <div className="absrow" style={{ marginTop: 8 }}>
              {sum.run?.status === 'done' && <button onClick={exportXlsx}>Скачать xlsx</button>}
              {sum.run && <button className="ghost" onClick={() => nav(`/runs/${sum.run?.id}`)}>Открыть прогон</button>}
              {isAdmin && sum.status !== 'closed' && (
                <button disabled={busy || !sum.export_ready} onClick={() => act('close', 'Месяц закрыт')}>
                  Закрыть месяц
                </button>
              )}
              {isAdmin && sum.status === 'closed' && (
                <button className="ghost" disabled={busy} onClick={() => act('reopen', 'Месяц переоткрыт')}>
                  Переоткрыть
                </button>
              )}
              {isAdmin && sum.status !== 'closed' && !sum.export_ready && (
                <span className="muted">Закрытие недоступно: остались блокеры ниже.</span>
              )}
            </div>
          </div>

          <h3 style={{ marginTop: 18 }}>Готовность к закрытию</h3>
          <div className="readiness-grid">
            {sum.checklist.map((c) => {
              return (
                <div key={c.key} className={`card readiness-card ${c.ok ? 'ok' : c.blocking ? 'blocking' : 'warn'}`}>
                  <div className="readiness-title">{c.ok ? '✓' : '✗'} {c.label}</div>
                  <div className="readiness-meta">
                    {c.ok ? 'готово' : `${c.count} · ${c.blocking ? 'блокер' : 'предупреждение'}`}
                  </div>
                  {!c.ok && c.link && (
                    <button className="link" onClick={() => nav(c.link ?? '')}>Перейти →</button>
                  )}
                </div>
              )
            })}
          </div>

          <h3 style={{ marginTop: 18 }}>Отклонения по типам</h3>
          {!Object.keys(sum.deviations.by_code).length ? (
            <div className="muted">Нет отклонений.</div>
          ) : (
            <ul>
              {Object.entries(sum.deviations.by_code).map(([code, n]) => (
                <li key={code}>{devLabel(code)}: {n}</li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  )
}
