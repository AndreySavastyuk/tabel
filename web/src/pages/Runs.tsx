import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, downloadExport, uploadFile, type Run, type UploadSource } from '../api'
import { useAuth } from '../auth'

const SOURCES: { key: UploadSource; label: string; accept: string }[] = [
  { key: 'stork', label: 'StorK (CSV)', accept: '.csv' },
  { key: 'sigur', label: 'SIGUR (XLSX)', accept: '.xlsx' },
  { key: 'lez', label: 'ЛЭЗ lez (XLSX)', accept: '.xlsx' },
]

const STATUS_LABEL: Record<Run['status'], string> = {
  queued: 'в очереди', running: 'идёт расчёт…', done: 'готов', failed: 'ошибка',
}

export default function Runs() {
  const nav = useNavigate()
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin_hr'
  const [runs, setRuns] = useState<Run[]>([])
  const [uploaded, setUploaded] = useState<Record<string, { id: number; filename: string }>>({})
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [periodMode, setPeriodMode] = useState<'month' | 'range'>('month')
  const [month, setMonth] = useState('')
  const [fromDate, setFromDate] = useState('')
  const [toDate, setToDate] = useState('')

  const siblingOf = (r: Run) =>
    runs.find((o) => o.id !== r.id && o.status === 'done' && !!r.period_label && o.period_label === r.period_label)

  const loadRuns = async () => {
    try {
      setRuns(await api.get<Run[]>('/runs'))
    } catch (e) {
      setErr((e as Error).message)
    }
  }
  useEffect(() => {
    loadRuns()
  }, [])
  useEffect(() => {
    if (!runs.some((r) => r.status === 'queued' || r.status === 'running')) return
    const t = setInterval(loadRuns, 2000)
    return () => clearInterval(t)
  }, [runs])

  const onFile = async (src: UploadSource, f?: File) => {
    if (!f) return
    setErr('')
    try {
      const u = await uploadFile(src, f)
      setUploaded((p) => ({ ...p, [src]: { id: u.id, filename: u.filename } }))
    } catch (e) {
      setErr((e as Error).message)
    }
  }

  const build = async () => {
    const ids = Object.values(uploaded).map((u) => u.id)
    if (!ids.length) {
      setErr('Загрузите хотя бы один файл')
      return
    }
    const body: { upload_ids: number[]; period?: string; period_from?: string; period_to?: string } = { upload_ids: ids }
    if (periodMode === 'month') {
      if (!month) { setErr('Выберите месяц прогона'); return }
      body.period = month
    } else {
      if (!fromDate || !toDate) { setErr('Укажите даты диапазона'); return }
      body.period_from = fromDate
      body.period_to = toDate
    }
    setBusy(true)
    setErr('')
    try {
      const r = await api.post<Run>('/runs', body)
      setUploaded({})
      await loadRuns()
      nav(`/runs/${r.id}`)
    } catch (e) {
      setErr((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <div className="pagehead">
        <h2>Прогоны табеля</h2>
      </div>
      {err && <div className="error">{err}</div>}

      {isAdmin && (
        <div className="card panel">
          <h3>Новый прогон</h3>
          <p className="muted">Загрузите выгрузки СКУД и постройте табель.</p>
          <div className="uploads">
            {SOURCES.map((s) => (
              <label key={s.key} className="uploadbox">
                <span>{s.label}</span>
                <input type="file" accept={s.accept}
                       onChange={(e) => onFile(s.key, e.target.files?.[0])} />
                {uploaded[s.key] && <em className="ok">✓ {uploaded[s.key].filename}</em>}
              </label>
            ))}
          </div>
          <div className="absrow" style={{ marginTop: 8, marginBottom: 8 }}>
            <label className="chk">
              <input type="radio" name="pmode" checked={periodMode === 'month'}
                     onChange={() => setPeriodMode('month')} /> Месяц
            </label>
            {periodMode === 'month' && (
              <input type="month" value={month} onChange={(e) => setMonth(e.target.value)} />
            )}
            <label className="chk">
              <input type="radio" name="pmode" checked={periodMode === 'range'}
                     onChange={() => setPeriodMode('range')} /> Диапазон
            </label>
            {periodMode === 'range' && (
              <>
                <input type="date" value={fromDate} onChange={(e) => setFromDate(e.target.value)} />
                <span className="muted">—</span>
                <input type="date" value={toDate} onChange={(e) => setToDate(e.target.value)} />
              </>
            )}
          </div>
          <button disabled={busy || !Object.keys(uploaded).length} onClick={build}>
            {busy ? 'Запуск…' : 'Построить табель'}
          </button>
        </div>
      )}

      <table className="grid">
        <thead>
          <tr>
            <th style={{ width: 50 }}>№</th>
            <th>Статус</th>
            <th>Период</th>
            <th>Создан</th>
            <th>Дней</th>
            <th>Сотрудников</th>
            <th>Действия</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((r) => (
            <tr key={r.id}>
              <td>{r.id}</td>
              <td>
                <span className={`badge st-${r.status}`}>{STATUS_LABEL[r.status]}</span>
                {r.status === 'failed' && r.error_text && (
                  <div className="muted" style={{ fontSize: 12 }}>{r.error_text}</div>
                )}
              </td>
              <td>
                {r.period_label ?? (r.period_from && r.period_to ? `${r.period_from}–${r.period_to}` : '—')}
                {r.is_final && <span className="badge st-done" style={{ marginLeft: 6 }}>★ финальный</span>}
              </td>
              <td>{r.created_at?.replace('T', ' ').slice(0, 16)}</td>
              <td>{r.n_day_records ?? '—'}</td>
              <td>{r.n_employees ?? '—'}</td>
              <td className="actions">
                <button className="link" onClick={() => nav(`/runs/${r.id}`)}>Открыть</button>
                {r.status === 'done' && (
                  <button className="link" onClick={() => downloadExport(r.id).catch((e) => setErr((e as Error).message))}>Скачать xlsx</button>
                )}
                {(() => {
                  const sib = siblingOf(r)
                  return r.status === 'done' && sib && (
                    <button className="link" onClick={() => nav(`/runs/${r.id}/diff/${sib.id}`)}>Сравнить</button>
                  )
                })()}
              </td>
            </tr>
          ))}
          {!runs.length && (
            <tr><td colSpan={7} className="muted">Прогонов пока нет.</td></tr>
          )}
        </tbody>
      </table>
    </div>
  )
}
