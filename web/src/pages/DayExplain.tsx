import { useEffect, useState } from 'react'
import { api, devLabel, type DayExplain as DayExplainData } from '../api'

// Панель «Объяснение дня»: сырые события, выбор входа/выхода, обед, норма+пороги,
// пошаговая формула. Данные — read-only трассировка с бэка (движок не пересчитывается).
export default function DayExplain({ eid, date, runId }: { eid: number; date: string; runId?: number }) {
  const [data, setData] = useState<DayExplainData | null>(null)
  const [err, setErr] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let alive = true
    setLoading(true)
    setErr('')
    const q = runId ? `?run_id=${runId}` : ''
    api.get<DayExplainData>(`/employees/${eid}/days/${date}/explain${q}`)
      .then((d) => { if (alive) setData(d) })
      .catch((e) => { if (alive) setErr((e as Error).message) })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [eid, date, runId])

  if (loading) return <div className="muted" style={{ padding: 12 }}>Загрузка объяснения…</div>
  if (err) return <div className="error" style={{ margin: 12 }}>{err}</div>
  if (!data) return null

  const d = data.day
  const sch = data.schedule
  const fixedNote = d.start_fixed
    ? `фикс. время${d.original_start ? `, фактически было ${d.original_start}` : ''}`
    : null

  return (
    <div style={{ padding: '12px 14px', display: 'grid', gap: 14 }}>
      <section>
        <h4 style={{ margin: '0 0 6px' }}>Сырые события СКУД/ЛЭЗ</h4>
        {!data.raw_events.length ? (
          <div className="muted">Событий за этот день нет.</div>
        ) : (
          <table className="grid inner">
            <thead><tr><th>Время</th><th>Направление</th><th>Система</th><th>Источник</th></tr></thead>
            <tbody>
              {data.raw_events.map((ev, i) => (
                <tr key={i}>
                  <td>{ev.time}</td>
                  <td>{ev.kind}</td>
                  <td className={ev.source === 'LEZ' ? 'lez' : ''}>{ev.system ?? ev.source}</td>
                  <td>{ev.source}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
          События за календарный день; для ночных смен набор может отличаться от расчётного окна.
        </div>
      </section>

      <section>
        <h4 style={{ margin: '0 0 6px' }}>Выбор входа/выхода</h4>
        <div className="absrow">
          <span><b>Вход:</b>{' '}
            <span className={d.start_fixed ? 'fix' : d.entry_source === 'LEZ' ? 'lez' : ''}>
              {d.entry ?? '—'}
            </span>
            {d.entry_source ? ` (${d.entry_source})` : ''}
            {fixedNote ? ` · ${fixedNote}` : ''}
          </span>
          <span><b>Выход:</b>{' '}
            <span className={d.exit_source === 'LEZ' ? 'lez' : ''}>{d.exit ?? '—'}</span>
            {d.exit_source ? ` (${d.exit_source})` : ''}
          </span>
        </div>
        <div className="muted" style={{ fontSize: 12 }}>
          внутр.: {d.int_entry ?? '—'}…{d.int_exit ?? '—'} · ЛЭЗ: {d.lez_entry ?? '—'}…{d.lez_exit ?? '—'}
        </div>
      </section>

      <section>
        <h4 style={{ margin: '0 0 6px' }}>Обед и график</h4>
        <div className="absrow">
          <span><b>Вычет обеда:</b> {(d.lunch_deducted ?? 0).toFixed(2)} ч</span>
          {sch?.lunch_start && sch?.lunch_end && (
            <span><b>Окно обеда:</b> {sch.lunch_start}–{sch.lunch_end}</span>
          )}
          <span><b>График:</b> {sch?.code ?? 'не назначен'}
            {sch?.shift_start ? ` · смена с ${sch.shift_start}` : ''}
            {sch?.shift_len != null ? ` · ${sch.shift_len} ч` : ''}
          </span>
        </div>
      </section>

      <section>
        <h4 style={{ margin: '0 0 6px' }}>Норма дня и пороги</h4>
        <div className="absrow">
          <span><b>Норма дня:</b> {(d.day_norm ?? 0).toFixed(2)} ч</span>
        </div>
        <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
          Пороги ({data.thresholds_source === 'run_snapshot' ? 'снимок прогона' : 'текущие'}):{' '}
          {Object.entries(data.thresholds).map(([k, v]) => `${k}=${v}`).join(' · ')}
        </div>
      </section>

      <section>
        <h4 style={{ margin: '0 0 6px' }}>Формула</h4>
        <table className="grid inner">
          <tbody>
            {data.formula.map((s) => (
              <tr key={s.key}>
                <td>{s.label}</td>
                <td style={{ textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>
                  {s.value > 0 && s.key !== 'raw_hours' && s.key !== 'worked' ? '+' : ''}
                  {s.value} {s.unit}
                </td>
                <td className="muted">{s.detail ?? ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {d.deviations.length > 0 && (
          <div className="bad" style={{ marginTop: 6 }}>
            Отклонения: {d.deviations.map(devLabel).join('; ')}
          </div>
        )}
      </section>
    </div>
  )
}
