import { useState } from 'react'
import { Link } from 'react-router-dom'
import { importReference, type ReferenceImportResult, type ReferenceKind } from '../api'
import { useAuth } from '../auth'

const KINDS: { kind: ReferenceKind; label: string; hint: string }[] = [
  { kind: 'employees', label: 'Справочник сотрудников', hint: 'ФИО, Отдел, Кабинет, График, Фикс.время, Контроль ЛЭЗ' },
  { kind: 'norms', label: 'Графики и нормы', hint: 'График, Месяц, Норма, Начало смены, Длит.смены, Обед нач/кон' },
  { kind: 'absences', label: 'Отсутствия', hint: 'ФИО, Тип, Дата с, Дата по' },
  { kind: 'trips', label: 'Командировки', hint: 'ФИО, Дата с, Дата по' },
]

const COUNT_LABELS: Record<string, string> = {
  departments: 'Отделы', schedules: 'Графики', norms: 'Нормы',
  employees: 'Сотрудники', absences: 'Отсутствия',
}

export default function Import() {
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin_hr'
  const [busy, setBusy] = useState<ReferenceKind | null>(null)
  const [err, setErr] = useState('')
  const [results, setResults] = useState<ReferenceImportResult[]>([])

  if (!isAdmin) {
    return (
      <div>
        <div className="pagehead"><h2>Импорт справочников</h2></div>
        <div className="muted">Импорт доступен только роли «Кадры/Админ».</div>
      </div>
    )
  }

  const onFile = async (kind: ReferenceKind, file: File | undefined) => {
    if (!file) return
    setErr('')
    setBusy(kind)
    try {
      const r = await importReference(kind, file)
      setResults((rs) => [r, ...rs])
    } catch (e) {
      setErr((e as Error).message)
    } finally {
      setBusy(null)
    }
  }

  return (
    <div>
      <div className="pagehead"><h2>Импорт справочников</h2></div>
      <p className="muted">
        Загрузите файлы Excel — данные добавятся/обновятся в базе (идемпотентно).
        Заголовки распознаются нечётко, точные названия колонок не требуются.
        После импорта пересоберите табель на странице «Прогоны».
      </p>
      <div className="muted" style={{ marginBottom: 8 }}>
        Рабочий процесс: <strong>Импорт</strong> → <Link to="/assign">Назначение</Link> →{' '}
        <Link to="/runs">Прогон</Link> → <Link to="/aliases">Разбор&nbsp;ФИО</Link>
      </div>
      {err && <div className="error">{err}</div>}

      <div className="card panel">
        {KINDS.map(({ kind, label, hint }) => (
          <div key={kind} className="absrow" style={{ alignItems: 'center' }}>
            <label className="grow">
              <strong>{label}</strong>
              <div className="muted" style={{ fontSize: 12 }}>{hint}</div>
            </label>
            <input type="file" accept=".xlsx" disabled={busy !== null}
                   onChange={(e) => { onFile(kind, e.target.files?.[0]); e.target.value = '' }} />
            {busy === kind && <span className="muted">Импорт…</span>}
          </div>
        ))}
      </div>

      {results.length > 0 && (
        <div className="card panel">
          <h3>Результаты импорта</h3>
          <table className="grid">
            <thead>
              <tr><th>Файл</th><th>Тип</th><th>Изменения в справочниках</th></tr>
            </thead>
            <tbody>
              {results.map((r, i) => (
                <tr key={i}>
                  <td>{r.filename}</td>
                  <td>{KINDS.find((k) => k.kind === r.kind)?.label ?? r.kind}</td>
                  <td>
                    {Object.keys(COUNT_LABELS).map((key) => {
                      const b = r.before[key as keyof typeof r.before]
                      const a = r.after[key as keyof typeof r.after]
                      if (a === b) return null
                      return (
                        <span key={key} className="badge" style={{ marginRight: 8 }}>
                          {COUNT_LABELS[key]}: {b} → {a}
                        </span>
                      )
                    })}
                    {Object.keys(COUNT_LABELS).every(
                      (key) => r.before[key as keyof typeof r.before] === r.after[key as keyof typeof r.after],
                    ) && <span className="muted">без изменений (данные уже актуальны)</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
