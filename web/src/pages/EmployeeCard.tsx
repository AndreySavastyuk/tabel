import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  api, devLabel, type DayRecord, type Department, type Employee, type MonthSummary, type Schedule,
} from '../api'
import { useAuth } from '../auth'
import DayExplain from './DayExplain'

const MONTH_RU = ['', 'январь', 'февраль', 'март', 'апрель', 'май', 'июнь',
  'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь']
const fmtMonth = (m: string) => {
  const [y, mm] = m.split('-')
  return `${MONTH_RU[Number(mm)]} ${y}`
}

export default function EmployeeCard() {
  const { id } = useParams()
  const eid = Number(id)
  const nav = useNavigate()
  const [emp, setEmp] = useState<Employee | null>(null)
  const [depts, setDepts] = useState<Department[]>([])
  const [scheds, setScheds] = useState<Schedule[]>([])
  const [months, setMonths] = useState<MonthSummary[]>([])
  const [openMonth, setOpenMonth] = useState<string | null>(null)
  const [days, setDays] = useState<DayRecord[]>([])
  const [err, setErr] = useState('')

  const { user } = useAuth()
  const isAdmin = user?.role === 'admin_hr'
  const [editing, setEditing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [fDept, setFDept] = useState('')
  const [fCab, setFCab] = useState('')
  const [fSched, setFSched] = useState('')

  const startEdit = () => {
    if (!emp) return
    setFDept(emp.department_id ? String(emp.department_id) : '')
    setFCab(emp.cabinet ?? '')
    setFSched(emp.schedule_id ? String(emp.schedule_id) : '')
    setEditing(true)
  }
  const save = async () => {
    setSaving(true)
    setErr('')
    try {
      const updated = await api.patch<Employee>(`/employees/${eid}`, {
        department_id: fDept ? Number(fDept) : null,
        cabinet: fCab.trim() || null,
        schedule_id: fSched ? Number(fSched) : null,
      })
      setEmp(updated)
      setEditing(false)
    } catch (e) {
      setErr((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  useEffect(() => {
    ;(async () => {
      try {
        const [e, d, s, m] = await Promise.all([
          api.get<Employee>(`/employees/${eid}`),
          api.get<Department[]>('/departments'),
          api.get<Schedule[]>('/schedules'),
          api.get<MonthSummary[]>(`/employees/${eid}/months`),
        ])
        setEmp(e); setDepts(d); setScheds(s); setMonths(m)
      } catch (e) {
        setErr((e as Error).message)
      }
    })()
  }, [eid])

  const openDays = useCallback(async (month: string) => {
    if (openMonth === month) {
      setOpenMonth(null)
      return
    }
    setOpenMonth(month)
    try {
      setDays(await api.get<DayRecord[]>(`/employees/${eid}/days?month=${month}`))
    } catch (e) {
      setErr((e as Error).message)
    }
  }, [eid, openMonth])

  const deptName = useMemo(() => depts.find((d) => d.id === emp?.department_id)?.name, [depts, emp])
  const schedCode = useMemo(() => scheds.find((s) => s.id === emp?.schedule_id)?.code, [scheds, emp])

  if (err) return <div className="error">{err}</div>
  if (!emp) return <div className="muted">Загрузка…</div>

  return (
    <div>
      <div className="pagehead">
        <h2>{emp.full_name}</h2>
        <button className="ghost" onClick={() => nav('/employees')}>← К сотрудникам</button>
      </div>
      <div className="card empmeta">
        {!editing ? (
          <>
            <span><b>Отдел:</b> {deptName || '—'}</span>
            <span><b>Кабинет:</b> {emp.cabinet || '—'}</span>
            <span><b>График:</b> {schedCode || 'не задан'}</span>
            {emp.fixed_time && <span><b>Фикс. время:</b> {emp.fixed_time}</span>}
            <span><b>Контроль ЛЭЗ:</b> {emp.lez_controlled ? 'да' : 'нет'}</span>
            {isAdmin && <button className="ghost" onClick={startEdit}>Изменить</button>}
          </>
        ) : (
          <>
            <label>Отдел{' '}
              <select value={fDept} onChange={(e) => setFDept(e.target.value)}>
                <option value="">— без отдела —</option>
                {depts.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
              </select>
            </label>
            <label>Кабинет{' '}
              <input value={fCab} onChange={(e) => setFCab(e.target.value)} style={{ width: 110 }} />
            </label>
            <label>График{' '}
              <select value={fSched} onChange={(e) => setFSched(e.target.value)}>
                <option value="">не задан</option>
                {scheds.map((s) => <option key={s.id} value={s.id}>{s.code}</option>)}
              </select>
            </label>
            <button disabled={saving} onClick={save}>{saving ? 'Сохранение…' : 'Сохранить'}</button>
            <button className="ghost" disabled={saving} onClick={() => setEditing(false)}>Отмена</button>
          </>
        )}
      </div>

      <h3 style={{ marginTop: 18 }}>По месяцам</h3>
      {!months.length ? <div className="muted">Нет данных по прогонам. Постройте табель на «Прогонах».</div> : (
        <table className="grid">
          <thead>
            <tr>
              <th>Месяц</th><th>Раб. дней</th><th>Отработано, ч</th><th>Норма, ч</th>
              <th>± к норме</th><th>Переработка, ч</th><th>Опозданий</th><th>Отсутствий</th><th></th>
            </tr>
          </thead>
          <tbody>
            {months.map((m) => {
              const open = openMonth === m.month
              return (
                <>
                  <tr key={m.month} className={open ? 'selrow' : ''} style={{ cursor: 'pointer' }} onClick={() => openDays(m.month)}>
                    <td><b>{fmtMonth(m.month)}</b></td>
                    <td>{m.work_days}</td>
                    <td>{m.worked_total.toFixed(2)}</td>
                    <td>{m.norm_hours != null ? m.norm_hours.toFixed(0) : '—'}</td>
                    <td className={m.balance == null ? '' : m.balance < 0 ? 'miss' : 'fix'}>
                      {m.balance != null ? (m.balance > 0 ? '+' : '') + m.balance.toFixed(2) : '—'}
                    </td>
                    <td className={m.overtime_total ? 'warn-cell' : ''}>{m.overtime_total.toFixed(2)}</td>
                    <td className={m.late_days ? 'warn-cell' : ''}>{m.late_days ? `${m.late_days} (${m.late_minutes} мин)` : '—'}</td>
                    <td>{m.absence_days || '—'}</td>
                    <td className="link">{open ? '▲ свернуть' : '▼ по дням'}</td>
                  </tr>
                  {open && (
                    <tr key={m.month + '_days'}>
                      <td colSpan={9} style={{ padding: 0 }}><DayTable rows={days} eid={eid} /></td>
                    </tr>
                  )}
                </>
              )
            })}
          </tbody>
        </table>
      )}
    </div>
  )
}

function DayTable({ rows, eid }: { rows: DayRecord[]; eid: number }) {
  const [openDate, setOpenDate] = useState<string | null>(null)
  if (!rows.length) return <div className="muted" style={{ padding: 10 }}>Нет дней.</div>
  return (
    <table className="grid inner">
      <thead>
        <tr>
          <th>Дата</th><th>Вход</th><th>Выход</th><th>Обед</th><th>Часы</th>
          <th>Опозд., мин</th><th>Переработка, ч</th><th>Отсутствие</th><th>Отклонения</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => {
          const hasBoth = r.entry && r.exit
          const open = openDate === r.work_date
          return (
            <>
              <tr key={i} className={open ? 'selrow' : ''}>
                <td className={r.is_weekend ? 'we' : ''}>
                  <button className="link" title="Объяснить расчёт"
                          onClick={() => setOpenDate(open ? null : r.work_date)}>
                    {r.work_date}
                  </button>
                </td>
                <td className={!r.entry ? 'miss' : r.start_fixed ? 'fix' : r.entry_source === 'LEZ' ? 'lez' : ''}>{r.entry ?? '—'}</td>
                <td className={!r.exit ? 'miss' : r.exit_source === 'LEZ' ? 'lez' : ''}>{r.exit ?? '—'}</td>
                <td>{r.lunch_deducted ? r.lunch_deducted.toFixed(2) : '0'}</td>
                <td className={!hasBoth && !r.absence ? 'miss' : ''}>{hasBoth ? r.worked_hours.toFixed(2) : '—'}</td>
                <td className={r.lateness_min ? 'warn-cell' : ''}>{r.lateness_min || ''}</td>
                <td className={r.overtime_h ? 'warn-cell' : ''}>{r.overtime_h || ''}</td>
                <td>{r.absence || ''}</td>
                <td className={r.deviations.length ? 'bad' : ''}>{r.deviations.map(devLabel).join('; ')}</td>
              </tr>
              {open && (
                <tr key={`${i}_explain`}>
                  <td colSpan={9} style={{ padding: 0 }}><DayExplain eid={eid} date={r.work_date} /></td>
                </tr>
              )}
            </>
          )
        })}
      </tbody>
    </table>
  )
}
