import { NavLink, Navigate, Route, Routes } from 'react-router-dom'
import { type ReactNode } from 'react'
import { ROLE_LABEL } from './api'
import { useAuth } from './auth'
import Login from './pages/Login'
import Employees from './pages/Employees'
import Departments from './pages/Departments'
import Schedules from './pages/Schedules'
import Runs from './pages/Runs'
import RunView from './pages/RunView'
import Absences from './pages/Absences'
import EmployeeCard from './pages/EmployeeCard'
import Calendar from './pages/Calendar'

function Layout({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth()
  if (!user) return null
  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">Табель&nbsp;СКУД</div>
        <nav>
          <NavLink to="/runs">Прогоны</NavLink>
          <NavLink to="/absences">Отсутствия</NavLink>
          <NavLink to="/employees">Сотрудники</NavLink>
          <NavLink to="/departments">Отделы</NavLink>
          <NavLink to="/schedules">Графики</NavLink>
          <NavLink to="/calendar">Календарь</NavLink>
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
        <Route path="/absences" element={<Absences />} />
        <Route path="/employees" element={<Employees />} />
        <Route path="/employees/:id" element={<EmployeeCard />} />
        <Route path="/departments" element={<Departments />} />
        <Route path="/schedules" element={<Schedules />} />
        <Route path="/calendar" element={<Calendar />} />
        <Route path="*" element={<Navigate to="/runs" replace />} />
      </Routes>
    </Layout>
  )
}
