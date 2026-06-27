import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'
import {
  ABSENCE_STATUS_LABEL, ABSENCE_TYPES, api, type Absence, type AbsenceType, type Employee,
} from '../api'
import { useAuth } from '../auth'

export default function Absences() {
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin_hr'
  const isDeptHead = user?.role === 'dept_head'
  const canCreate = isAdmin || isDeptHead

  const [rows, setRows] = useState<Absence[]>([])
  const [emps, setEmps] = useState<Employee[]>([])
  const [err, setErr] = useState('')

  // форма
  const [empName, setEmpName] = useState('')
  const [type, setType] = useState<AbsenceType>(isDeptHead ? 'отгул' : 'отпуск')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    try {
      setRows(await api.get<Absence[]>('/absences'))
      if (canCreate) setEmps(await api.get<Employee[]>('/employees?limit=5000'))
    } catch (e) {
      setErr((e as Error).message)
    }
  }, [canCreate])
  useEffect(() => {
    load()
  }, [load])

  const empByName = useMemo(() => {
    const m = new Map<string, number>()
    for (const e of emps) m.set(e.full_name, e.id)
    return m
  }, [emps])

  const add = async (e: FormEvent) => {
    e.preventDefault()
    setErr('')
    const eid = empByName.get(empName.trim())
    if (!eid) {
      setErr('Выберите сотрудника из списка')
      return
    }
    if (!from || !to) {
      setErr('Укажите даты «с» и «по»')
      return
    }
    setBusy(true)
    try {
      await api.post('/absences', { employee_id: eid, type, date_from: from, date_to: to, note: note || null })
      setEmpName(''); setFrom(''); setTo(''); setNote('')
      await load()
    } catch (e) {
      setErr((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const act = async (fn: () => Promise<unknown>) => {
    setErr('')
    try {
      await fn()
      await load()
    } catch (e) {
      setErr((e as Error).message)
    }
  }

  const pending = rows.filter((r) => r.status === 'submitted')
  const types: AbsenceType[] = isDeptHead ? ['отгул'] : ABSENCE_TYPES

  return (
    <div>
      <div className="pagehead"><h2>Отсутствия</h2></div>
      {err && <div className="error">{err}</div>}

      {canCreate && (
        <form className="card panel absform" onSubmit={add}>
          <h3>Добавить отсутствие</h3>
          <div className="absrow">
            <label>Сотрудник
              <input list="emps" value={empName} onChange={(e) => setEmpName(e.target.value)}
                     placeholder="Начните вводить ФИО" />
              <datalist id="emps">
                {emps.map((e) => <option key={e.id} value={e.full_name} />)}
              </datalist>
            </label>
            <label>Тип
              <select value={type} onChange={(e) => setType(e.target.value as AbsenceType)}>
                {types.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </label>
            <label>С<input type="date" value={from} onChange={(e) => setFrom(e.target.value)} /></label>
            <label>По<input type="date" value={to} onChange={(e) => setTo(e.target.value)} /></label>
            <label className="grow">Примечание
              <input value={note} onChange={(e) => setNote(e.target.value)} /></label>
          </div>
          <button disabled={busy}>{busy ? 'Сохранение…' : 'Добавить'}</button>
          {isDeptHead && <span className="muted" style={{ marginLeft: 12 }}>
            Руководитель оформляет отгул — он попадёт на подтверждение.</span>}
        </form>
      )}

      {pending.length > 0 && (
        <div className="card panel">
          <h3>На подтверждении ({pending.length})</h3>
          <table className="grid">
            <thead><tr><th>ФИО</th><th>Тип</th><th>С</th><th>По</th><th>Действия</th></tr></thead>
            <tbody>
              {pending.map((a) => (
                <tr key={a.id}>
                  <td>{a.employee_name}</td>
                  <td>{a.type}</td>
                  <td>{a.date_from}</td>
                  <td>{a.date_to}</td>
                  <td className="actions">
                    {isAdmin ? (
                      <>
                        <button className="link" onClick={() => act(() => api.post(`/absences/${a.id}/approve`, {}))}>Подтвердить</button>
                        <button className="link" onClick={() => act(() => api.post(`/absences/${a.id}/reject`, {}))}>Отклонить</button>
                      </>
                    ) : <span className="muted">ожидает Кадры</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h3>Все отсутствия <span className="muted">({rows.length})</span></h3>
      <table className="grid">
        <thead><tr><th>ФИО</th><th>Тип</th><th>С</th><th>По</th><th>Статус</th><th>Примечание</th>{isAdmin && <th></th>}</tr></thead>
        <tbody>
          {rows.map((a) => (
            <tr key={a.id}>
              <td>{a.employee_name}</td>
              <td>{a.type}</td>
              <td>{a.date_from}</td>
              <td>{a.date_to}</td>
              <td><span className={`badge st-${a.status === 'approved' ? 'done' : a.status === 'rejected' ? 'failed' : 'running'}`}>
                {ABSENCE_STATUS_LABEL[a.status]}</span></td>
              <td>{a.note || ''}</td>
              {isAdmin && <td><button className="link" onClick={() => act(() => api.del(`/absences/${a.id}`))}>Удалить</button></td>}
            </tr>
          ))}
          {!rows.length && <tr><td colSpan={isAdmin ? 7 : 6} className="muted">Отсутствий нет.</td></tr>}
        </tbody>
      </table>
    </div>
  )
}
