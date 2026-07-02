import { type ReactNode } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useAuth } from '../auth'
import Settings from './Settings'
import Departments from './Departments'
import Schedules from './Schedules'
import Assign from './Assign'
import Import from './Import'
import Aliases from './Aliases'

type Tab = { key: string; label: string; el: ReactNode; adminOnly?: boolean }

// Единый раздел «Администрирование»: справочники и настройки вкладками, чтобы не
// плодить пункты в боковом меню. Тяжёлые редакторы (Назначение/Импорт/Настройки/
// Разбор ФИО) — только Кадры/Админ; справочники (Отделы/Графики/Календарь) видны всем.
const ALL_TABS: Tab[] = [
  { key: 'departments', label: 'Отделы', el: <Departments /> },
  { key: 'schedules', label: 'Графики', el: <Schedules /> },
  { key: 'assign', label: 'Назначение', el: <Assign />, adminOnly: true },
  { key: 'import', label: 'Импорт', el: <Import />, adminOnly: true },
  { key: 'aliases', label: 'Разбор ФИО', el: <Aliases />, adminOnly: true },
  { key: 'settings', label: 'Настройки', el: <Settings />, adminOnly: true },
]

export default function Admin() {
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin_hr'
  const [sp, setSp] = useSearchParams()
  const tabs = ALL_TABS.filter((t) => isAdmin || !t.adminOnly)
  const req = sp.get('tab')
  const active = req && tabs.some((t) => t.key === req) ? req : tabs[0].key
  const cur = tabs.find((t) => t.key === active) ?? tabs[0]

  return (
    <div>
      <div className="pagehead"><h2>Администрирование</h2></div>
      <div className="tabs">
        {tabs.map((t) => (
          <button key={t.key} className={`tab ${t.key === active ? 'active' : ''}`}
                  onClick={() => setSp({ tab: t.key })}>
            {t.label}
          </button>
        ))}
      </div>
      {/* key на обёртке — переключение вкладки монтирует раздел заново (свежие данные,
          и не грузим все разделы сразу) */}
      <div key={cur.key} className="admin-panel">{cur.el}</div>
    </div>
  )
}
