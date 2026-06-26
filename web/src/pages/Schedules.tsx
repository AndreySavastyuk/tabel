import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, type Schedule, type ScheduleNorm } from '../api'
import { useAuth } from '../auth'

const MONTHS = ['01', '02', '03', '04', '05', '06', '07', '08', '09', '10', '11', '12']
const MONTH_RU = ['Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн', 'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек']

interface Form {
  id: number | null
  code: string
  shift_start: string
  shift_len: string
  lunch_start: string
  lunch_end: string
}
const EMPTY: Form = { id: null, code: '', shift_start: '08:00', shift_len: '8', lunch_start: '12:00', lunch_end: '12:30' }

export default function Schedules() {
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin_hr'
  const canNorms = isAdmin || user?.role === 'accountant'

  const [rows, setRows] = useState<Schedule[]>([])
  const [form, setForm] = useState<Form>(EMPTY)
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')

  // нормы выбранного графика
  const [selId, setSelId] = useState<number | null>(null)
  const [year, setYear] = useState('2026')
  const [norms, setNorms] = useState<Record<string, string>>({})

  const load = async () => {
    try {
      setRows(await api.get<Schedule[]>('/schedules'))
    } catch (e) {
      setErr((e as Error).message)
    }
  }
  useEffect(() => {
    load()
  }, [])

  const loadNorms = useCallback(async (id: number) => {
    const ns = await api.get<ScheduleNorm[]>(`/schedules/${id}/norms`)
    const m: Record<string, string> = {}
    for (const n of ns) m[n.month] = String(n.norm_hours)
    setNorms(m)
  }, [])

  const edit = (s: Schedule) => {
    setForm({ id: s.id, code: s.code, shift_start: s.shift_start ?? '', shift_len: s.shift_len != null ? String(s.shift_len) : '',
      lunch_start: s.lunch_start ?? '', lunch_end: s.lunch_end ?? '' })
    setSelId(s.id)
    loadNorms(s.id)
  }

  const save = async () => {
    setErr('')
    setMsg('')
    const body = {
      code: form.code,
      shift_start: form.shift_start || null,
      shift_len: form.shift_len ? Number(form.shift_len) : null,
      lunch_start: form.lunch_start || null,
      lunch_end: form.lunch_end || null,
    }
    try {
      const saved = form.id
        ? await api.patch<Schedule>(`/schedules/${form.id}`, body)
        : await api.post<Schedule>('/schedules', body)
      setMsg('График сохранён')
      await load()
      edit(saved)
    } catch (e) {
      setErr((e as Error).message)
    }
  }

  const saveNorms = async () => {
    if (!selId) return
    setErr('')
    setMsg('')
    try {
      for (const mm of MONTHS) {
        const v = norms[`${year}-${mm}`]
        if (v && !Number.isNaN(Number(v))) {
          await api.put(`/schedules/${selId}/norms`, { month: `${year}-${mm}`, norm_hours: Number(v) })
        }
      }
      setMsg('Нормы сохранены')
      await loadNorms(selId)
    } catch (e) {
      setErr((e as Error).message)
    }
  }

  const selCode = useMemo(() => rows.find((r) => r.id === selId)?.code, [rows, selId])

  return (
    <div>
      <div className="pagehead"><h2>Графики и нормы</h2></div>
      {err && <div className="error">{err}</div>}
      {msg && <div className="ok-box">{msg}</div>}

      <table className="grid" style={{ marginBottom: 18 }}>
        <thead><tr><th>Код</th><th>Начало</th><th>Длит., ч</th><th>Обед</th>{isAdmin && <th></th>}</tr></thead>
        <tbody>
          {rows.map((s) => (
            <tr key={s.id} className={selId === s.id ? 'selrow' : ''}>
              <td>{s.code}</td>
              <td>{s.shift_start || '—'}</td>
              <td>{s.shift_len ?? '—'}</td>
              <td>{s.lunch_start && s.lunch_end ? `${s.lunch_start}–${s.lunch_end}` : '—'}</td>
              {isAdmin && <td><button className="link" onClick={() => edit(s)}>Изменить / нормы</button></td>}
            </tr>
          ))}
          {!rows.length && <tr><td colSpan={5} className="muted">Графиков нет.</td></tr>}
        </tbody>
      </table>

      {isAdmin && (
        <div className="card panel">
          <h3>{form.id ? `График «${form.code}»` : 'Новый график'}
            {form.id != null && <button className="link" style={{ marginLeft: 10 }}
              onClick={() => { setForm(EMPTY); setSelId(null); setNorms({}) }}>+ создать новый</button>}</h3>
          <div className="absrow">
            <label>Код<input value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} placeholder="Смена12" /></label>
            <label>Начало смены<input value={form.shift_start} onChange={(e) => setForm({ ...form, shift_start: e.target.value })} placeholder="08:00" style={{ width: 90 }} /></label>
            <label>Длит. смены, ч<input value={form.shift_len} onChange={(e) => setForm({ ...form, shift_len: e.target.value })} style={{ width: 80 }} /></label>
            <label>Обед с<input value={form.lunch_start} onChange={(e) => setForm({ ...form, lunch_start: e.target.value })} placeholder="12:00" style={{ width: 90 }} /></label>
            <label>Обед по<input value={form.lunch_end} onChange={(e) => setForm({ ...form, lunch_end: e.target.value })} placeholder="12:30" style={{ width: 90 }} /></label>
          </div>
          <button onClick={save} disabled={!form.code}>Сохранить график</button>
        </div>
      )}

      {canNorms && selId && (
        <div className="card panel">
          <h3>Нормы графика «{selCode}»</h3>
          <div className="searchbar" style={{ marginBottom: 10 }}>
            <label className="chk">Год <input value={year} onChange={(e) => setYear(e.target.value)} style={{ width: 70 }} /></label>
            <span className="muted">Норма часов за месяц (из производственного календаря)</span>
          </div>
          <div className="normsgrid">
            {MONTHS.map((mm, i) => (
              <label key={mm} className="normcell">
                <span>{MONTH_RU[i]}</span>
                <input value={norms[`${year}-${mm}`] ?? ''} placeholder="—"
                  onChange={(e) => setNorms({ ...norms, [`${year}-${mm}`]: e.target.value })} />
              </label>
            ))}
          </div>
          <button onClick={saveNorms} style={{ marginTop: 10 }}>Сохранить нормы за {year}</button>
        </div>
      )}
    </div>
  )
}
