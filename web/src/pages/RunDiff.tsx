import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api, type DayDiff, type RunDiff as RunDiffData } from '../api'

const fmt = (v: unknown) =>
  v === null || v === undefined ? '—' : Array.isArray(v) ? (v.join(', ') || '—') : String(v)

const present = (f?: { from: unknown; to: unknown }) => (f ? (f.to ?? f.from) : undefined)

export default function RunDiff() {
  const { id, other } = useParams()
  const nav = useNavigate()
  const [data, setData] = useState<RunDiffData | null>(null)
  const [err, setErr] = useState('')

  useEffect(() => {
    api.get<RunDiffData>(`/runs/${id}/diff/${other}`)
      .then(setData)
      .catch((e) => setErr((e as Error).message))
  }, [id, other])

  if (err) return <div className="error">{err}</div>
  if (!data) return <div className="muted">Загрузка…</div>

  const empty = !data.n_changed && !data.n_added && !data.n_removed
  return (
    <div>
      <div className="pagehead">
        <h2>Сравнение прогонов №{data.base_run_id} и №{data.other_run_id}</h2>
        <button className="ghost" onClick={() => nav(`/runs/${data.base_run_id}`)}>← К прогону</button>
      </div>
      <p className="muted">
        Изменено: {data.n_changed} · добавлено (в №{data.other_run_id}): {data.n_added} ·
        удалено (было в №{data.base_run_id}): {data.n_removed}
      </p>
      {empty && <div className="ok-box">Прогоны идентичны по дням сотрудников.</div>}
      {data.changed.length > 0 && <ChangedTable rows={data.changed} />}
      {data.added.length > 0 && <PresenceTable title={`Добавлено (есть в №${data.other_run_id})`} rows={data.added} />}
      {data.removed.length > 0 && <PresenceTable title={`Удалено (было в №${data.base_run_id})`} rows={data.removed} />}
    </div>
  )
}

function ChangedTable({ rows }: { rows: DayDiff[] }) {
  return (
    <div className="deptblock">
      <h3>Изменено</h3>
      <table className="grid">
        <thead><tr><th>ФИО</th><th>Дата</th><th>Поле</th><th>Было</th><th>Стало</th></tr></thead>
        <tbody>
          {rows.flatMap((r) => Object.entries(r.fields).map(([f, v]) => (
            <tr key={`${r.employee_id}_${r.work_date}_${f}`}>
              <td>{r.employee_name}</td>
              <td>{r.work_date}</td>
              <td>{f}</td>
              <td className="warn-cell">{fmt(v.from)}</td>
              <td className="fix">{fmt(v.to)}</td>
            </tr>
          )))}
        </tbody>
      </table>
    </div>
  )
}

function PresenceTable({ title, rows }: { title: string; rows: DayDiff[] }) {
  return (
    <div className="deptblock">
      <h3>{title}</h3>
      <table className="grid">
        <thead><tr><th>ФИО</th><th>Дата</th><th>Часы</th><th>Отсутствие</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={`${r.employee_id}_${r.work_date}`}>
              <td>{r.employee_name}</td>
              <td>{r.work_date}</td>
              <td>{fmt(present(r.fields.worked_hours))}</td>
              <td>{fmt(present(r.fields.absence))}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
