import { NavLink, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { type ReactNode, useEffect, useState } from 'react'
import { api, ROLE_LABEL } from './api'
import { useAuth } from './auth'
import Login from './pages/Login'
import Employees from './pages/Employees'
import Departments from './pages/Departments'
import Schedules from './pages/Schedules'
import Runs from './pages/Runs'
import RunView from './pages/RunView'
import RunDiff from './pages/RunDiff'
import Absences from './pages/Absences'
import Deviations from './pages/Deviations'
import EmployeeCard from './pages/EmployeeCard'
import EmployeeReport from './pages/EmployeeReport'
import Calendar from './pages/Calendar'
import Import from './pages/Import'
import Aliases from './pages/Aliases'
import Assign from './pages/Assign'
import Settings from './pages/Settings'
import Admin from './pages/Admin'
import Overtime from './pages/Overtime'
import MonthClose from './pages/MonthClose'

type IconName =
  | 'close'
  | 'runs'
  | 'deviations'
  | 'absences'
  | 'employees'
  | 'overtime'
  | 'calendar'
  | 'admin'

const ICON_PATHS: Record<IconName, string[]> = {
  close: ['M5 4h10l2 3v13H3V7l2-3Z', 'M7 9h10', 'M7 13h7', 'M7 17h5'],
  runs: ['M4 5h16v14H4z', 'M8 9h8', 'M8 13h5', 'M8 17h8'],
  deviations: ['M12 3 2.8 19h18.4L12 3Z', 'M12 8v5', 'M12 16h.01'],
  absences: ['M7 4h10v16H7z', 'M9 8h6', 'M9 12h6', 'M9 16h4'],
  employees: ['M16 18c0-2.2-1.8-4-4-4s-4 1.8-4 4', 'M12 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z', 'M18 10a2.5 2.5 0 1 0 0-5', 'M20 18c0-1.6-.9-3-2.2-3.7'],
  overtime: ['M12 6v6l4 2', 'M21 12a9 9 0 1 1-3.2-6.9'],
  calendar: ['M5 5h14v15H5z', 'M8 3v4', 'M16 3v4', 'M5 10h14'],
  admin: ['M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z', 'M19 12a7 7 0 0 0-.1-1l2-1.5-2-3.5-2.4 1a7.3 7.3 0 0 0-1.7-1L14.5 3h-5l-.3 3a7.3 7.3 0 0 0-1.7 1l-2.4-1-2 3.5L5.1 11a7 7 0 0 0 0 2l-2 1.5 2 3.5 2.4-1a7.3 7.3 0 0 0 1.7 1l.3 3h5l.3-3a7.3 7.3 0 0 0 1.7-1l2.4 1 2-3.5-2-1.5c.1-.3.1-.7.1-1Z'],
}

function NavIcon({ name }: { name: IconName }) {
  return (
    <svg className="navicon" viewBox="0 0 24 24" aria-hidden="true">
      {ICON_PATHS[name].map((d) => <path key={d} d={d} />)}
    </svg>
  )
}

function NavItem({
  to,
  label,
  icon,
  badge,
  match = [],
}: {
  to: string
  label: string
  icon: IconName
  badge?: number | null
  match?: string[]
}) {
  const location = useLocation()
  const isMatched = match.some((p) => location.pathname === p || location.pathname.startsWith(`${p}/`))
  return (
    <NavLink to={to} title={label} className={({ isActive }) => (isActive || isMatched ? 'active' : '')}>
      <span className="navitem-main">
        <NavIcon name={icon} />
        <span className="nav-label">{label}</span>
      </span>
      {badge ? <span className="pill nav-badge">{badge}</span> : null}
    </NavLink>
  )
}

function Layout({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth()
  const [aliasCount, setAliasCount] = useState<number | null>(null)
  const [devOpen, setDevOpen] = useState<number | null>(null)
  useEffect(() => {
    if (user?.role !== 'admin_hr') return
    api.get<{ unresolved: number }>('/aliases/count')
      .then((r) => setAliasCount(r.unresolved))
      .catch(() => { /* бейдж не критичен */ })
  }, [user])
  useEffect(() => {
    api.get<{ open: number }>('/deviations/count')
      .then((r) => setDevOpen(r.open))
      .catch(() => { /* бейдж не критичен */ })
  }, [user])
  if (!user) return null
  const isAdmin = user.role === 'admin_hr'
  const canClose = isAdmin || user.role === 'accountant'
  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">ТС</span>
          <span className="brand-text">Табель&nbsp;СКУД</span>
        </div>
        <nav className="sidenav">
          <div className="navgroup">
            <div className="navgroup-title">Работа</div>
            {canClose && <NavItem to="/close" label="Закрытие месяца" icon="close" />}
            <NavItem to="/runs" label="Прогоны" icon="runs" />
            <NavItem to="/deviations" label="Отклонения" icon="deviations" badge={devOpen} />
            <NavItem to="/absences" label="Отсутствия" icon="absences" />
          </div>
          <div className="navgroup">
            <div className="navgroup-title">Персонал</div>
            <NavItem to="/employees" label="Сотрудники" icon="employees" />
            <NavItem to="/overtime" label="Переработки" icon="overtime" />
          </div>
          <div className="navgroup">
            <div className="navgroup-title">Справочники и настройки</div>
            <NavItem to="/calendar" label="Календарь" icon="calendar" />
            <NavItem
              to="/admin"
              label="Администрирование"
              icon="admin"
              badge={aliasCount}
              match={['/departments', '/schedules', '/assign', '/import', '/aliases', '/settings']}
            />
          </div>
        </nav>
        <div className="sidefoot">
          <div className="user-avatar">{(user.full_name || user.username).slice(0, 1).toUpperCase()}</div>
          <div className="who">
            <span className="who-name">{user.full_name || user.username}</span>
            <span className="muted">{ROLE_LABEL[user.role]}</span>
          </div>
          <button className="ghost" onClick={logout}>Выйти</button>
        </div>
      </aside>
      <main className="main">
        <div className="content">{children}</div>
      </main>
    </div>
  )
}

export default function App() {
  const { user, loading } = useAuth()
  if (loading) return <div className="center muted">Загрузка…</div>
  if (!user) {
    return (
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    )
  }
  return (
    <Layout>
      <Routes>
        <Route path="/runs" element={<Runs />} />
        <Route path="/runs/:id" element={<RunView />} />
        <Route path="/runs/:id/diff/:other" element={<RunDiff />} />
        <Route path="/absences" element={<Absences />} />
        <Route path="/deviations" element={<Deviations />} />
        <Route path="/employees" element={<Employees />} />
        <Route path="/employees/:id" element={<EmployeeCard />} />
        <Route path="/employees/:id/report" element={<EmployeeReport />} />
        <Route path="/overtime" element={<Overtime />} />
        {/* Раздел «Администрирование» — вкладки; отдельные маршруты сохранены
            для глубоких ссылок (напр. из центра закрытия месяца). */}
        <Route path="/admin" element={<Admin />} />
        <Route path="/departments" element={<Departments />} />
        <Route path="/schedules" element={<Schedules />} />
        <Route path="/calendar" element={<Calendar />} />
        <Route path="/import" element={<Import />} />
        <Route path="/aliases" element={<Aliases />} />
        <Route path="/assign" element={<Assign />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/close" element={<MonthClose />} />
        <Route path="*" element={<Navigate to="/runs" replace />} />
      </Routes>
    </Layout>
  )
}
