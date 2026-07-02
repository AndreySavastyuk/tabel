import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import {
  api, devCode, devLabel, type DayRecord, type Department, type Employee, type MonthSummary, type Schedule,
} from '../api'

const MONTH_RU = ['', 'январь', 'февраль', 'март', 'апрель', 'май', 'июнь',
  'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь']
const fmtMonth = (m: string) => {
  const [y, mm] = m.split('-')
  return `${MONTH_RU[Number(mm)]} ${y}`
}
const h = (n: number) => n.toFixed(2)

// «Выход с территории» приходит из движка строкой; вытащим её человекочитаемо.
const awayText = (r: DayRecord) =>
  r.deviations.filter((d) => devCode(d) === 'REENTRY_GAP').map((d) => d.replace('Выход с территории ', '')).join('; ')

export default function EmployeeReport() {
  const { id } = useParams()
  const eid = Number(id)
  const nav = useNavigate()
  const [sp] = useSearchParams()
  const month = sp.get('month') || ''

  const [emp, setEmp] = useState<Employee | null>(null)
  const [deptName, setDeptName] = useState('—')
  const [sched, setSched] = useState<Schedule | null>(null)
  const [sum, setSum] = useState<MonthSummary | null>(null)
  const [days, setDays] = useState<DayRecord[]>([])
  const [err, setErr] = useState('')

  useEffect(() => {
    ;(async () => {
      try {
        const [e, scheds, depts, months, ds] = await Promise.all([
          api.get<Employee>(`/employees/${eid}`),
          api.get<Schedule[]>('/schedules'),
          api.get<Department[]>('/departments'),
          api.get<MonthSummary[]>(`/employees/${eid}/months`),
          api.get<DayRecord[]>(`/employees/${eid}/days?month=${month}`),
        ])
        setEmp(e)
        setDeptName(depts.find((d) => d.id === e.department_id)?.name ?? '—')
        setSched(scheds.find((s) => s.id === e.schedule_id) ?? null)
        setSum(months.find((m) => m.month === month) ?? null)
        setDays([...ds].sort((a, b) => a.work_date.split('.').reverse().join('').localeCompare(b.work_date.split('.').reverse().join(''))))
      } catch (e) {
        setErr((e as Error).message)
      }
    })()
  }, [eid, month])

  // Норма с учётом уважительных отсутствий: дневная норма ≈ длительность смены,
  // каждый день отпуска/больничного/командировки/отгула уменьшает норму к отработке.
  const calc = useMemo(() => {
    if (!sum) return null
    const daily = sched?.shift_len ? Number(sched.shift_len) : 0
    const absDays = sum.absence_days || 0
    const credit = +(absDays * daily).toFixed(2)
    const normToWork = Math.max(0, +((sum.norm_hours ?? 0) - credit).toFixed(2))
    const balance = +(sum.worked_total - normToWork).toFixed(2)
    const percent = normToWork > 0 ? +(sum.worked_total / normToWork * 100).toFixed(1) : null
    return { daily, absDays, credit, normToWork, balance, percent }
  }, [sum, sched])

  // Разбор отсутствий по типам + проблемные дни.
  const groups = useMemo(() => {
    const absByType = new Map<string, number>()
    const missing: DayRecord[] = []
    const away: DayRecord[] = []
    const late: DayRecord[] = []
    const overtime: DayRecord[] = []
    for (const r of days) {
      if (r.absence) absByType.set(r.absence, (absByType.get(r.absence) ?? 0) + 1)
      if (!r.absence && !r.is_weekend && (!r.entry || !r.exit)) missing.push(r)
      if (awayText(r)) away.push(r)
      if (r.lateness_min > 0) late.push(r)
      if (r.overtime_h > 0) overtime.push(r)
    }
    return { absByType: [...absByType.entries()], missing, away, late, overtime }
  }, [days])

  if (err) return <div className="error">{err}</div>
  if (!emp || !month) return <div className="muted">Загрузка…</div>

  return (
    <div className="report">
      <div className="no-print report-actions">
        <button className="ghost" onClick={() => nav(`/employees/${eid}`)}>← К карточке</button>
        <button onClick={() => window.print()}>Печать / Сохранить PDF</button>
      </div>

      <div className="report-head">
        <h1>Отчёт по сотруднику за месяц</h1>
        <div className="report-sub">Табель СКУД · {fmtMonth(month)}</div>
      </div>

      <table className="kv">
        <tbody>
          <tr><td>ФИО</td><td><b>{emp.full_name}</b></td><td>Отдел</td><td>{deptName}</td></tr>
          <tr><td>График</td><td>{sched?.code ?? 'не задан'}{sched?.shift_len ? ` (смена ${h(Number(sched.shift_len))} ч)` : ''}</td>
            <td>Кабинет</td><td>{emp.cabinet || '—'}</td></tr>
        </tbody>
      </table>

      {!sum ? <div className="muted">Нет данных по этому месяцу.</div> : (
        <>
          <h3>Итоги месяца</h3>
          <table className="grid summary">
            <tbody>
              <tr><td>Рабочих дней отработано</td><td className="num">{sum.work_days}</td>
                  <td>Опозданий</td><td className="num">{sum.late_days} ({sum.late_minutes} мин)</td></tr>
              <tr><td>Норма месяца, ч</td><td className="num">{sum.norm_hours != null ? h(sum.norm_hours) : '—'}</td>
                  <td>Переработка, ч</td><td className="num">{h(sum.overtime_total)}</td></tr>
              <tr><td>Уваж. отсутствия, дн.</td><td className="num">{calc?.absDays ?? 0}</td>
                  <td>Зачёт отсутствий, ч</td><td className="num">{calc ? h(calc.credit) : '—'}</td></tr>
              <tr className="totalrow"><td>Норма к отработке, ч <span className="muted">(с учётом отсутствий)</span></td>
                  <td className="num">{calc ? h(calc.normToWork) : '—'}</td>
                  <td>Отработано, ч</td><td className="num"><b>{h(sum.worked_total)}</b></td></tr>
              <tr><td>Баланс к норме, ч</td>
                  <td className={`num ${calc && calc.balance < 0 ? 'neg' : 'pos'}`}>{calc ? (calc.balance > 0 ? '+' : '') + h(calc.balance) : '—'}</td>
                  <td>% выполнения</td><td className="num">{calc?.percent != null ? `${calc.percent}%` : '—'}</td></tr>
            </tbody>
          </table>

          {groups.absByType.length > 0 && (
            <p><b>Отсутствия:</b> {groups.absByType.map(([t, n]) => `${t} — ${n} дн.`).join(', ')}</p>
          )}

          <Section title="Дни без отметки (нет входа/выхода)" rows={groups.missing}
                   cell={(r) => `${!r.entry ? 'нет входа' : ''}${!r.entry && !r.exit ? ', ' : ''}${!r.exit ? 'нет выхода' : ''}`} />
          <Section title="Выход за территорию сверх нормы (> порога)" rows={groups.away} cell={awayText} />
          <Section title="Опоздания" rows={groups.late} cell={(r) => `${r.lateness_min} мин`} />
          <Section title="Переработки" rows={groups.overtime} cell={(r) => `${h(r.overtime_h)} ч`} />

          <h3>По дням</h3>
          <table className="grid">
            <thead>
              <tr><th>Дата</th><th>Вход</th><th>Выход</th><th>Обед</th><th>Часы</th>
                  <th>Опозд.</th><th>Перераб.</th><th>Отсутствие</th><th>Отклонения</th></tr>
            </thead>
            <tbody>
              {days.map((r, i) => {
                const both = r.entry && r.exit
                const hrs = r.effective_hours ?? r.worked_hours
                return (
                  <tr key={i} className={r.is_weekend ? 'we' : ''}>
                    <td>{r.work_date}</td>
                    <td className={!r.entry ? 'miss' : ''}>{r.entry ?? '—'}</td>
                    <td className={!r.exit ? 'miss' : ''}>{r.exit ?? '—'}</td>
                    <td>{r.lunch_deducted ? h(r.lunch_deducted) : ''}</td>
                    <td className={!both && !r.absence ? 'miss' : ''}>{both ? h(hrs) : '—'}</td>
                    <td>{r.lateness_min || ''}</td>
                    <td>{r.overtime_h || ''}</td>
                    <td>{r.absence || ''}</td>
                    <td className={r.deviations.length ? 'bad' : ''}>{r.deviations.map(devLabel).join('; ')}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </>
      )}
      <div className="report-foot muted">Сформировано в системе «Табель СКУД».</div>
    </div>
  )
}

function Section({ title, rows, cell }: { title: string; rows: DayRecord[]; cell: (r: DayRecord) => string }) {
  return (
    <div className="report-section">
      <h4>{title} <span className="muted">({rows.length})</span></h4>
      {rows.length === 0 ? <div className="muted">—</div> : (
        <ul className="daylist">
          {rows.map((r, i) => <li key={i}><b>{r.work_date}</b> — {cell(r)}</li>)}
        </ul>
      )}
    </div>
  )
}
