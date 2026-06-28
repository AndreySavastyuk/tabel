import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  api, DEV_LABELS, DEV_STATUS_LABEL, DEV_STATUS_ORDER,
  type DeviationItem, type DeviationStatus, type UserBrief,
} from '../api'

const STATUS_COLOR: Record<DeviationStatus, string> = {
  new: '#ffe1e1', in_progress: '#fff3cd', accepted: '#dbeafe', fixed: '#d8f5dd', ignored: '#eceff1',
}

export default function Deviations() {
  const nav = useNavigate()
  const [items, setItems] = useState<DeviationItem[]>([])
  const [users, setUsers] = useState<UserBrief[]>([])
  const [statusF, setStatusF] = useState('')
  const [codeF, setCodeF] = useState('')
  const [sel, setSel] = useState<Set<number>>(new Set())
  const [bulkStatus, setBulkStatus] = useState<DeviationStatus>('accepted')
  const [bulkAssignee, setBulkAssignee] = useState('')
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    setErr('')
    try {
      const q = new URLSearchParams()
      if (statusF) q.set('status', statusF)
      if (codeF) q.set('dev_code', codeF)
      setItems(await api.get<DeviationItem[]>(`/deviations?${q.toString()}`))
      setSel(new Set())
    } catch (e) {
      setErr((e as Error).message)
    }
  }, [statusF, codeF])

  useEffect(() => { load() }, [load])
  // список пользователей для назначения (доступен админу/бухгалтеру; иначе скрыт)
  useEffect(() => { api.get<UserBrief[]>('/users').then(setUsers).catch(() => setUsers([])) }, [])

  const toggle = (id: number) => setSel((s) => {
    const n = new Set(s)
    if (n.has(id)) n.delete(id)
    else n.add(id)
    return n
  })
  const toggleAll = () => setSel((s) => (s.size === items.length ? new Set() : new Set(items.map((i) => i.id))))

  const setStatus = async (id: number, st: DeviationStatus) => {
    setErr('')
    try { await api.patch(`/deviations/${id}`, { status: st }); await load() } catch (e) { setErr((e as Error).message) }
  }
  const setAssignee = async (id: number, val: string) => {
    setErr('')
    try { await api.patch(`/deviations/${id}`, { assignee_id: val ? Number(val) : null }); await load() } catch (e) { setErr((e as Error).message) }
  }

  const applyBulk = async (payload: { status?: string; assignee_id?: number }) => {
    if (!sel.size) return
    setBusy(true); setErr(''); setMsg('')
    try {
      const r = await api.post<{ updated: number; skipped: number }>(
        '/deviations/bulk', { ids: [...sel], ...payload })
      setMsg(`Обновлено: ${r.updated}${r.skipped ? `, пропущено: ${r.skipped}` : ''}`)
      await load()
    } catch (e) {
      setErr((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const userName = (u: UserBrief) => u.full_name || u.username

  return (
    <div>
      <div className="pagehead"><h2>Отклонения</h2></div>
      {err && <div className="error">{err}</div>}
      {msg && <div className="ok-box">{msg}</div>}

      <div className="searchbar">
        <label>Статус{' '}
          <select value={statusF} onChange={(e) => setStatusF(e.target.value)}>
            <option value="">все</option>
            {DEV_STATUS_ORDER.map((s) => <option key={s} value={s}>{DEV_STATUS_LABEL[s]}</option>)}
          </select>
        </label>
        <label>Тип{' '}
          <select value={codeF} onChange={(e) => setCodeF(e.target.value)}>
            <option value="">все</option>
            {Object.entries(DEV_LABELS).map(([c, l]) => <option key={c} value={c}>{l}</option>)}
          </select>
        </label>
      </div>

      {sel.size > 0 && (
        <div className="assignbar">
          <span>Выбрано: {sel.size}</span>
          <select value={bulkStatus} onChange={(e) => setBulkStatus(e.target.value as DeviationStatus)}>
            {DEV_STATUS_ORDER.map((s) => <option key={s} value={s}>{DEV_STATUS_LABEL[s]}</option>)}
          </select>
          <button disabled={busy} onClick={() => applyBulk({ status: bulkStatus })}>Статус</button>
          {users.length > 0 && (
            <>
              <select value={bulkAssignee} onChange={(e) => setBulkAssignee(e.target.value)}>
                <option value="">— ответственный —</option>
                {users.map((u) => <option key={u.id} value={u.id}>{userName(u)}</option>)}
              </select>
              <button disabled={busy || !bulkAssignee} onClick={() => applyBulk({ assignee_id: Number(bulkAssignee) })}>
                Назначить
              </button>
            </>
          )}
        </div>
      )}

      <table className="grid">
        <thead>
          <tr>
            <th style={{ width: 30 }}>
              <input type="checkbox" checked={sel.size > 0 && sel.size === items.length} onChange={toggleAll} />
            </th>
            <th>ФИО</th><th>Дата</th><th>Отклонение</th><th>Статус</th><th>Ответственный</th><th>Комм.</th>
          </tr>
        </thead>
        <tbody>
          {items.map((it) => (
            <tr key={it.id} className={sel.has(it.id) ? 'selrow' : ''}>
              <td><input type="checkbox" checked={sel.has(it.id)} onChange={() => toggle(it.id)} /></td>
              <td><button className="link" onClick={() => nav(`/employees/${it.employee_id}`)}>{it.employee_name ?? '?'}</button></td>
              <td>{it.work_date}</td>
              <td className="bad">{it.dev_label ?? it.dev_code}{it.detail ? ` · ${it.detail}` : ''}</td>
              <td>
                <select value={it.status} style={{ background: STATUS_COLOR[it.status] }}
                        onChange={(e) => setStatus(it.id, e.target.value as DeviationStatus)}>
                  {DEV_STATUS_ORDER.map((s) => <option key={s} value={s}>{DEV_STATUS_LABEL[s]}</option>)}
                </select>
              </td>
              <td>
                {users.length ? (
                  <select value={it.assignee_id ?? ''} onChange={(e) => setAssignee(it.id, e.target.value)}>
                    <option value="">—</option>
                    {users.map((u) => <option key={u.id} value={u.id}>{userName(u)}</option>)}
                  </select>
                ) : (it.assignee_name ?? '—')}
              </td>
              <td>{it.comment_count || ''}</td>
            </tr>
          ))}
          {!items.length && <tr><td colSpan={7} className="muted">Отклонений нет.</td></tr>}
        </tbody>
      </table>
    </div>
  )
}
