import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, type CalendarEntry, type CalendarNorm, type HolidayKind } from '../api'

const MONTH_NAMES = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
  'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь']
const WD = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
const pad = (n: number) => String(n).padStart(2, '0')
const dstr = (y: number, m: number, d: number) => `${y}-${pad(m)}-${pad(d)}`
const dow = (y: number, m: number, d: number) => new Date(Date.UTC(y, m - 1, d)).getUTCDay() // 0=Вс
const daysIn = (y: number, m: number) => new Date(Date.UTC(y, m, 0)).getUTCDate()

type Status = 'work' | 'weekend' | 'holiday' | 'dayoff' | 'override'

export default function Calendar() {
  const [year, setYear] = useState(2026)
  const [entries, setEntries] = useState<Record<string, HolidayKind>>({})
  const [norms, setNorms] = useState<CalendarNorm[]>([])
  const [err, setErr] = useState('')

  const today = useMemo(() => new Date(), [])
  const isToday = (y: number, m: number, d: number) =>
    y === today.getFullYear() && m === today.getMonth() + 1 && d === today.getDate()

  const load = useCallback(async (y: number) => {
    setErr('')
    try {
      const [rows, ns] = await Promise.all([
        api.get<CalendarEntry[]>(`/calendar?year=${y}`),
        api.get<CalendarNorm[]>(`/calendar/norms?year=${y}`),
      ])
      const m: Record<string, HolidayKind> = {}
      for (const r of rows) m[r.cal_date] = r.kind
      setEntries(m)
      setNorms(ns)
    } catch (e) {
      setErr((e as Error).message)
    }
  }, [])
  useEffect(() => {
    load(year)
  }, [year, load])

  const status = useCallback((y: number, m: number, d: number): Status => {
    const e = entries[dstr(y, m, d)]
    if (e === 'holiday') return 'holiday'
    if (e === 'dayoff') return 'dayoff'
    if (e === 'workday_override') return 'override'
    const w = dow(y, m, d)
    return w === 0 || w === 6 ? 'weekend' : 'work'
  }, [entries])

  // сокращённый (предпраздничный) день: рабочий, а следующий — праздник
  const isShort = useCallback((y: number, m: number, d: number): boolean => {
    const st = status(y, m, d)
    if (st !== 'work' && st !== 'override') return false
    const nxt = new Date(Date.UTC(y, m - 1, d + 1))
    const nds = dstr(nxt.getUTCFullYear(), nxt.getUTCMonth() + 1, nxt.getUTCDate())
    return entries[nds] === 'holiday'
  }, [entries, status])

  const normByMonth = useMemo(() => {
    const map: Record<number, CalendarNorm> = {}
    for (const n of norms) map[Number(n.month.split('-')[1])] = n
    return map
  }, [norms])

  const counts = useMemo(() => {
    let hol = 0, off = 0, ov = 0
    for (const k of Object.values(entries)) {
      if (k === 'holiday') hol++
      else if (k === 'dayoff') off++
      else if (k === 'workday_override') ov++
    }
    return { hol, off, ov }
  }, [entries])

  return (
    <div>
      <div className="pagehead">
        <h2>Производственный календарь</h2>
        <div className="searchbar">
          <button className="ghost" onClick={() => setYear(year - 1)}>‹</button>
          <input value={year} onChange={(e) => setYear(Number(e.target.value) || year)} style={{ width: 70, textAlign: 'center' }} />
          <button className="ghost" onClick={() => setYear(year + 1)}>›</button>
        </div>
      </div>
      {err && <div className="error">{err}</div>}

      <div className="callegend">
        <span><i className="cd holiday" /> праздник ({counts.hol})</span>
        <span><i className="cd dayoff" /> перенесённый выходной ({counts.off})</span>
        <span><i className="cd override" /> рабочий день / перенос ({counts.ov})</span>
        <span><i className="cd short" /> сокращённый день (−1 ч)</span>
        <span><i className="cd weekend" /> выходной (сб/вс)</span>
      </div>

      <div className="calyear">
        {MONTH_NAMES.map((name, mi) => {
          const m = mi + 1
          const first = (dow(year, m, 1) + 6) % 7 // Пн=0
          const total = daysIn(year, m)
          const cells: (number | null)[] = [...Array(first).fill(null),
            ...Array.from({ length: total }, (_, i) => i + 1)]
          const nm = normByMonth[m]
          return (
            <div className="calmonth" key={m}>
              <h4>{name}{nm ? <span className="mhours"> · {nm.norm_5x2} ч</span> : ''}</h4>
              <div className="calgrid">
                {WD.map((w) => <div key={w} className="calhd">{w}</div>)}
                {cells.map((d, i) => d === null
                  ? <div key={i} />
                  : <div key={i}
                         className={`calday ${status(year, m, d)}${isShort(year, m, d) ? ' short' : ''}${isToday(year, m, d) ? ' today' : ''}`}
                         title={dstr(year, m, d) + (isShort(year, m, d) ? ' — сокращённый (7 ч)' : '') + (isToday(year, m, d) ? ' — сегодня' : '')}>{d}</div>)}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
