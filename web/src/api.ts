// Тонкий клиент к API. Токен — в localStorage. Базовый путь /api проксируется
// Vite на бэкенд (см. vite.config.ts).
const BASE = '/api'

export function getToken(): string | null {
  return localStorage.getItem('token')
}
export function setTokens(access: string, refresh: string) {
  localStorage.setItem('token', access)
  localStorage.setItem('refresh', refresh)
}
export function clearTokens() {
  localStorage.removeItem('token')
  localStorage.removeItem('refresh')
}

async function req<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { ...(opts.headers as Record<string, string>) }
  const t = getToken()
  if (t) headers['Authorization'] = `Bearer ${t}`
  const res = await fetch(BASE + path, { ...opts, headers })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const j = await res.json()
      detail = j.detail ?? detail
    } catch {
      /* ignore */
    }
    if (res.status === 401) clearTokens()
    throw new Error(detail)
  }
  const ct = res.headers.get('content-type') || ''
  return (ct.includes('json') ? res.json() : res.text()) as Promise<T>
}

export const api = {
  get: <T>(p: string) => req<T>(p),
  post: <T>(p: string, body: unknown) =>
    req<T>(p, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
  patch: <T>(p: string, body: unknown) =>
    req<T>(p, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
  put: <T>(p: string, body: unknown) =>
    req<T>(p, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
  del: <T>(p: string) => req<T>(p, { method: 'DELETE' }),

  async login(username: string, password: string) {
    const form = new URLSearchParams()
    form.set('username', username)
    form.set('password', password)
    const res = await fetch(BASE + '/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: form,
    })
    if (!res.ok) throw new Error('Неверный логин или пароль')
    return (await res.json()) as { access_token: string; refresh_token: string }
  },
}

// --- типы ответов API ---
export interface User {
  id: number
  username: string
  role: 'admin_hr' | 'accountant' | 'dept_head'
  full_name?: string | null
  department_id?: number | null
}
export interface Employee {
  id: number
  full_name: string
  normalized_name: string
  department_id?: number | null
  cabinet?: string | null
  schedule_id?: number | null
  fixed_time?: string | null
  lez_controlled: boolean
  hourly_rate?: number | null
  is_active: boolean
}
export interface Department {
  id: number
  name: string
  parent_id?: number | null
}
export interface Schedule {
  id: number
  code: string
  shift_start?: string | null
  shift_len?: number | null
  lunch_start?: string | null
  lunch_end?: string | null
}
export interface ScheduleNorm {
  id: number
  month: string
  norm_hours: number
}
export type HolidayKind = 'weekend' | 'holiday' | 'dayoff' | 'workday_override'
export interface CalendarEntry {
  id: number
  cal_date: string // YYYY-MM-DD
  kind: HolidayKind
  note?: string | null
}
export interface CalendarNorm {
  month: string
  work_days: number
  short_days: number
  norm_5x2: number
}

export interface MonthSummary {
  month: string
  work_days: number
  worked_total: number
  overtime_total: number
  late_days: number
  late_minutes: number
  absence_days: number
  norm_hours?: number | null
  balance?: number | null
  percent?: number | null
}

export const ROLE_LABEL: Record<User['role'], string> = {
  admin_hr: 'Кадры/Админ',
  accountant: 'Бухгалтер',
  dept_head: 'Руководитель отдела',
}

// --- Фаза 2/3: загрузки, прогоны, результаты ---
export type UploadSource = 'stork' | 'sigur' | 'hikvision' | 'lez'

export interface UploadRow {
  id: number
  filename: string
  source: UploadSource
  status: string
  uploaded_at: string
}
export interface Run {
  id: number
  status: 'queued' | 'running' | 'done' | 'failed'
  upload_ids?: number[] | null
  n_day_records?: number | null
  n_employees?: number | null
  error_text?: string | null
  created_at: string
  finished_at?: string | null
}
export interface DayRecord {
  employee_id: number
  employee_name?: string | null
  work_date: string
  is_weekend: boolean
  int_entry?: string | null
  int_exit?: string | null
  lez_entry?: string | null
  lez_exit?: string | null
  entry?: string | null
  exit?: string | null
  entry_source?: string | null
  exit_source?: string | null
  start_fixed: boolean
  lunch_deducted: number
  worked_hours: number
  lateness_min: number
  overtime_h: number
  absence?: string | null
  dept_name?: string | null
  cabinet?: string | null
  deviations: string[]
}
export interface Period {
  employee_id: number
  employee_name?: string | null
  dept_name?: string | null
  schedule_code?: string | null
  worked_total: number
  credited_total: number
  period_norm: number
  percent: number
  bucket?: string | null
  late_count: number
  late_minutes: number
  overtime_total: number
  overtime_pay?: number | null
}

export type AbsenceType = 'отпуск' | 'больничный' | 'командировка' | 'отгул'
export const ABSENCE_TYPES: AbsenceType[] = ['отпуск', 'больничный', 'командировка', 'отгул']

export interface Absence {
  id: number
  employee_id: number
  employee_name?: string | null
  type: AbsenceType
  date_from: string
  date_to: string
  status: 'draft' | 'submitted' | 'approved' | 'rejected'
  approved_by?: number | null
  note?: string | null
  created_at?: string | null
}
export const ABSENCE_STATUS_LABEL: Record<Absence['status'], string> = {
  draft: 'черновик', submitted: 'на подтверждении', approved: 'учтено', rejected: 'отклонено',
}

function authHeader(): Record<string, string> {
  const t = getToken()
  return t ? { Authorization: `Bearer ${t}` } : {}
}

export async function uploadFile(source: UploadSource, file: File): Promise<UploadRow> {
  const fd = new FormData()
  fd.set('source', source)
  fd.set('file', file)
  const res = await fetch(BASE + '/uploads', { method: 'POST', headers: authHeader(), body: fd })
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Ошибка загрузки')
  return res.json()
}

export async function downloadExport(runId: number) {
  const res = await fetch(`${BASE}/runs/${runId}/export/timesheet.xlsx`, { headers: authHeader() })
  if (!res.ok) throw new Error('Не удалось скачать файл')
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `tabel_run${runId}.xlsx`
  a.click()
  URL.revokeObjectURL(url)
}

// Коды отклонений -> русские подписи (зеркало engine.model.DEV_LABELS).
export const DEV_LABELS: Record<string, string> = {
  ONLY_INTERNAL: 'Только внутренняя система (нет ЛЭЗ)',
  ONLY_LEZ: 'Только ЛЭЗ (нет внутренней)',
  MISSING_ENTRY: 'Нет входа',
  MISSING_EXIT: 'Нет выхода',
  TIME_MISMATCH: 'Расхождение времени систем',
  IMPLAUSIBLE_HOURS: 'Нулевые/неправдоподобные часы',
  REENTRY_GAP: 'Выход с территории',
}
export const devLabel = (code: string) => DEV_LABELS[code] ?? code
