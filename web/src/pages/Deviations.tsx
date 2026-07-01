import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  api, DEV_LABELS, DEV_STATUS_LABEL, DEV_STATUS_ORDER,
  type DeviationItem, type DeviationStatus, type TimeDecision, type UserBrief,
} from '../api'
import { useAuth } from '../auth'

const STATUS_COLOR: Record<DeviationStatus, string> = {
  new: '#ffe1e1', in_progress: '#fff3cd', accepted: '#dbeafe', fixed: '#d8f5dd', ignored: '#eceff1',
}

type SortKey = 'status' | 'date' | 'name' | 'away'

// «DD.MM.YYYY» -> «YYYYMMDD» для хронологической сортировки строкой.
const dateKey = (d: string) => d.split('.').reverse().join('')
// Лейбл кода уже содержит «Выход с территории» — убираем повтор из detail
// (и на старых, ещё не пересчитанных, записях, где префикс мог сохраниться).
const cleanDetail = (d?: string | null) => (d ? d.replace(/Выход с территории /g, '') : '')
const fmtH = (m: number) => (m / 60).toFixed(1)

export default function Deviations() {
  const nav = useNavigate()
  const { user } = useAuth()
  const canDeduct = user?.role === 'admin_hr' || user?.role === 'accountant'
  const [items, setItems] = useState<DeviationItem[]>([])
  const [users, setUsers] = useState<UserBrief[]>([])
  const [statusF, setStatusF] = useState('')
  const [codeF, setCodeF] = useState('')
  const [nameF, setNameF] = useState('')
  const [sortKey, setSortKey] = useState<SortKey>('status')
  const [groupByName, setGroupByName] = useState(false)
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

  // Фильтр по ФИО + сортировка — на клиенте (список уже загружен целиком).
  const visible = useMemo(() => {
    const nf = nameF.trim().toLowerCase()
    const rows = nf
      ? items.filter((i) => (i.employee_name ?? '').toLowerCase().includes(nf))
      : items.slice()
    const byName = (a: DeviationItem, b: DeviationItem) =>
      (a.employee_name ?? '').localeCompare(b.employee_name ?? '', 'ru')
    if (sortKey === 'date') rows.sort((a, b) => dateKey(a.work_date).localeCompare(dateKey(b.work_date)))
    else if (sortKey === 'name') rows.sort((a, b) => byName(a, b) || dateKey(a.work_date).localeCompare(dateKey(b.work_date)))
    else if (sortKey === 'away') rows.sort((a, b) => (b.away_minutes || 0) - (a.away_minutes || 0) || byName(a, b))
    // 'status' — оставляем серверный порядок (status, work_date)
    return rows
  }, [items, nameF, sortKey])

  // Группировка по фамилии: карта employee -> строки + итог времени вне территории.
  const groups = useMemo(() => {
    if (!groupByName) return null
    const m = new Map<number, { name: string; items: DeviationItem[] }>()
    for (const it of visible) {
      const g = m.get(it.employee_id) ?? { name: it.employee_name ?? '?', items: [] }
      g.items.push(it)
      m.set(it.employee_id, g)
    }
    return [...m.entries()]
      .map(([employee_id, g]) => ({
        employee_id, name: g.name, items: g.items, count: g.items.length,
        totalAway: g.items.reduce((s, i) => s + (i.away_minutes || 0), 0),
      }))
      .sort((a, b) => a.name.localeCompare(b.name, 'ru'))
  }, [visible, groupByName])

  const toggle = (id: number) => setSel((s) => {
    const n = new Set(s)
    if (n.has(id)) n.delete(id)
    else n.add(id)
    return n
  })
  const allChecked = visible.length > 0 && visible.every((i) => sel.has(i.id))
  const toggleAll = () => setSel(allChecked ? new Set() : new Set(visible.map((i) => i.id)))

  const setStatus = async (id: number, st: DeviationStatus) => {
    setErr('')
    try { await api.patch(`/deviations/${id}`, { status: st }); await load() } catch (e) { setErr((e as Error).message) }
  }
  const setAssignee = async (id: number, val: string) => {
    setErr('')
    try { await api.patch(`/deviations/${id}`, { assignee_id: val ? Number(val) : null }); await load() } catch (e) { setErr((e as Error).message) }
  }
  const decide = async (id: number, td: TimeDecision) => {
    setErr('')
    try { await api.patch(`/deviations/${id}`, { time_decision: td }); await load() } catch (e) { setErr((e as Error).message) }
  }

  const applyBulk = async (payload: { status?: string; assignee_id?: number; time_decision?: TimeDecision }) => {
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

  // Ячейка «Отклонение»: для выхода с территории — интервалы столбиком.
  const devCell = (it: DeviationItem) => {
    if (it.dev_code === 'REENTRY_GAP') {
      const intervals = (it.detail ?? '').split('; ').filter(Boolean)
      return (
        <>
          {it.dev_label ?? it.dev_code}
          <div className="intervals">
            {intervals.map((s, i) => <div key={i}>{s}</div>)}
            <div className="muted">Итого: {it.away_minutes} мин ({fmtH(it.away_minutes)} ч)</div>
          </div>
        </>
      )
    }
    return <>{it.dev_label ?? it.dev_code}{it.detail ? ` · ${cleanDetail(it.detail)}` : ''}</>
  }

  // Ячейка «Вне территории»: решение о вычете (кадры/бухгалтер) + текущее состояние.
  const awayCell = (it: DeviationItem) => {
    if (it.dev_code !== 'REENTRY_GAP') return <span className="muted">—</span>
    const dec = it.time_decision
    return (
      <div className="awaycell">
        {dec === 'deducted'
          ? <span className="warn-txt" style={{ background: '#c6efce' }}>вычтено {it.deduct_minutes ?? it.away_minutes} мин</span>
          : dec === 'counted'
            ? <span className="muted">учтено как отработанное</span>
            : <span className="muted">не решено</span>}
        {canDeduct && (
          <div className="actions" style={{ marginTop: 4 }}>
            {dec === 'deducted'
              ? <button className="ghost" onClick={() => decide(it.id, 'counted')}>Отменить вычет</button>
              : <button className="ghost" onClick={() => decide(it.id, 'deducted')}>Вычесть из дня</button>}
          </div>
        )}
      </div>
    )
  }

  const row = (it: DeviationItem) => (
    <tr key={it.id} className={sel.has(it.id) ? 'selrow' : ''}>
      <td><input type="checkbox" checked={sel.has(it.id)} onChange={() => toggle(it.id)} /></td>
      <td><button className="link" onClick={() => nav(`/employees/${it.employee_id}`)}>{it.employee_name ?? '?'}</button></td>
      <td>{it.work_date}</td>
      <td className="bad">{devCell(it)}</td>
      <td>{awayCell(it)}</td>
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
  )

  return (
    <div>
      <div className="pagehead"><h2>Отклонения <span className="muted">({visible.length})</span></h2></div>
      {err && <div className="error">{err}</div>}
      {msg && <div className="ok-box">{msg}</div>}

      <p className="muted" style={{ margin: '0 0 12px', maxWidth: 960 }}>
        <b>«Вне территории»</b> — суммарное время выходов за территорию (ЛЭЗ) за день, интервалы показаны столбиком.
        Кадры/бухгалтер решают, <b>вычесть</b> ли это время из рабочего дня (влияет на отработанные часы и в своде, и в xlsx) или
        <b> учесть</b> как отработанное. <b>«Ответственный»</b> — кто назначен <b>разобрать</b> отклонение (не тот, кто его допустил).
      </p>

      <div className="searchbar" style={{ flexWrap: 'wrap', marginBottom: 12 }}>
        <input placeholder="Поиск по ФИО" value={nameF} onChange={(e) => setNameF(e.target.value)} />
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
        <label>Сортировка{' '}
          <select value={sortKey} onChange={(e) => setSortKey(e.target.value as SortKey)}>
            <option value="status">по статусу</option>
            <option value="date">по дате</option>
            <option value="name">по фамилии</option>
            <option value="away">по времени вне территории</option>
          </select>
        </label>
        <label className="chk">
          <input type="checkbox" checked={groupByName} onChange={(e) => setGroupByName(e.target.checked)} /> группировать по фамилии
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
          {canDeduct && (
            <>
              <span className="muted">| время вне территории:</span>
              <button disabled={busy} onClick={() => applyBulk({ time_decision: 'deducted' })}>Вычесть</button>
              <button disabled={busy} onClick={() => applyBulk({ time_decision: 'counted' })}>Учесть</button>
            </>
          )}
        </div>
      )}

      <table className="grid">
        <thead>
          <tr>
            <th style={{ width: 30 }}>
              <input type="checkbox" checked={allChecked} onChange={toggleAll} />
            </th>
            <th>ФИО</th><th>Дата</th><th>Отклонение</th>
            <th title="Суммарное время выходов за территорию и решение о вычете">Вне территории</th>
            <th>Статус</th>
            <th title="Кто назначен разобрать отклонение">Ответственный</th><th>Комм.</th>
          </tr>
        </thead>
        <tbody>
          {groups
            ? groups.map((g) => [
                <tr key={`g${g.employee_id}`} className="totalrow">
                  <td />
                  <td colSpan={7}>
                    {g.name} <span className="muted">· {g.count} откл.{g.totalAway ? ` · вне территории ${g.totalAway} мин` : ''}</span>
                  </td>
                </tr>,
                ...g.items.map(row),
              ])
            : visible.map(row)}
          {!visible.length && <tr><td colSpan={8} className="muted">Отклонений нет.</td></tr>}
        </tbody>
      </table>
    </div>
  )
}
