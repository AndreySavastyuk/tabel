import { NavLink, Navigate, Route, Routes } from 'react-router-dom'
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
import Calendar from './pages/Calendar'
import Import from './pages/Import'
import Aliases from './pages/Aliases'
import Assign from './pages/Assign'
import Settings from './pages/Settings'
import MonthClose from './pages/MonthClose'

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
      <header className="topbar">
        <div className="brand">Табель&nbsp;СКУД</div>
        <nav>
          {canClose && <NavLink to="/close">Закрытие&nbsp;месяца</NavLink>}
          <NavLink to="/runs">Прогоны</NavLink>
          <NavLink to="/deviations">
            Отклонения{devOpen ? ` (${devOpen})` : ''}
          </NavLink>
          <NavLink to="/absences">Отсутствия</NavLink>
          <NavLink to="/employees">Сотрудники</NavLink>
          <NavLink to="/departments">Отделы</NavLink>
          <NavLink to="/schedules">Графики</NavLink>
          <NavLink to="/calendar">Календарь</NavLink>
          {isAdmin && (
            <NavLink to="/aliases">
              Разбор&nbsp;ФИО{aliasCount ? ` (${aliasCount})` : ''}
            </NavLink>
          )}
          {isAdmin && <NavLink to="/assign">Назначение</NavLink>}
          {isAdmin && <NavLink to="/import">Импорт</NavLink>}
          {isAdmin && <NavLink to="/settings">Настройки</NavLink>}
        </nav>
        <div className="userbox">
          <span className="muted">
            {user.username} · {ROLE_LABEL[user.role]}
          </span>
          <button onClick={logout}>Выйти</button>
        </div>
      </header>
      <main className="content">{children}</main>
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
