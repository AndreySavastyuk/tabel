# -*- coding: utf-8 -*-
"""Pydantic-схемы запросов/ответов (v2). Денежные поля (hourly_rate) отдаются
только money-ролям — см. employee_out()."""
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from .constants import (AbsenceStatus, AbsenceType, HolidayKind, Role,
                        UploadSource)


# --- auth ---
class LoginIn(BaseModel):
    username: str
    password: str


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    role: Role
    full_name: Optional[str] = None
    department_id: Optional[int] = None
    is_active: bool


# --- departments ---
class DepartmentIn(BaseModel):
    name: str
    parent_id: Optional[int] = None


class DepartmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    parent_id: Optional[int] = None


# --- schedules / norms ---
class ScheduleNormIn(BaseModel):
    month: str = Field(pattern=r"^\d{4}-\d{2}$")
    norm_hours: float


class ScheduleNormOut(ScheduleNormIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class ScheduleIn(BaseModel):
    code: str
    shift_start: Optional[str] = None
    shift_len: Optional[float] = None
    lunch_start: Optional[str] = None
    lunch_end: Optional[str] = None


class ScheduleOut(ScheduleIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


# --- employees ---
class EmployeeCreate(BaseModel):
    full_name: str
    department_id: Optional[int] = None
    cabinet: Optional[str] = None
    schedule_id: Optional[int] = None
    fixed_time: Optional[str] = None
    lez_controlled: bool = False
    hourly_rate: Optional[float] = None
    is_active: bool = True


class EmployeeUpdate(BaseModel):
    full_name: Optional[str] = None
    department_id: Optional[int] = None
    cabinet: Optional[str] = None
    schedule_id: Optional[int] = None
    fixed_time: Optional[str] = None
    lez_controlled: Optional[bool] = None
    hourly_rate: Optional[float] = None
    is_active: Optional[bool] = None


class EmployeeBulkAssign(BaseModel):
    """Массовое присвоение. Поля, отсутствующие в запросе, не трогаются;
    явный null — очищает значение."""
    ids: list[int]
    department_id: Optional[int] = None
    cabinet: Optional[str] = None
    schedule_id: Optional[int] = None


class CalendarEntryIn(BaseModel):
    cal_date: date
    kind: HolidayKind
    note: Optional[str] = None


class CalendarEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    cal_date: date
    kind: HolidayKind
    note: Optional[str] = None


class CalendarNorm(BaseModel):
    month: str
    work_days: int
    short_days: int
    norm_5x2: float


class MonthSummary(BaseModel):
    month: str
    work_days: int
    worked_total: float
    overtime_total: float
    late_days: int
    late_minutes: int
    absence_days: int
    norm_hours: Optional[float] = None
    balance: Optional[float] = None
    percent: Optional[float] = None


class EmployeeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    full_name: str
    normalized_name: str
    department_id: Optional[int] = None
    cabinet: Optional[str] = None
    schedule_id: Optional[int] = None
    fixed_time: Optional[str] = None
    lez_controlled: bool
    hourly_rate: Optional[float] = None      # вырезается для не-money ролей
    is_active: bool


def employee_out(emp, role: Role) -> EmployeeOut:
    """Сериализация сотрудника с учётом роли: ставка скрыта для всех, кроме
    money-ролей (Кадры/Бухгалтер)."""
    from .constants import MONEY_ROLES
    out = EmployeeOut.model_validate(emp)
    if role not in MONEY_ROLES:
        out.hourly_rate = None
    return out


# --- absences (используется с Фазы 4, схема готова) ---
class AbsenceIn(BaseModel):
    employee_id: int
    type: AbsenceType
    date_from: date
    date_to: date
    note: Optional[str] = None


class AbsenceUpdate(BaseModel):
    type: Optional[AbsenceType] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    note: Optional[str] = None


class AbsenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    employee_id: int
    employee_name: Optional[str] = None
    type: AbsenceType
    date_from: date
    date_to: date
    status: AbsenceStatus
    approved_by: Optional[int] = None
    note: Optional[str] = None
    created_at: Optional[datetime] = None


# --- uploads / runs (Фаза 2) ---
class UploadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    filename: str
    source: UploadSource
    status: str
    uploaded_at: datetime


class RunCreate(BaseModel):
    upload_ids: list[int]


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    status: str
    upload_ids: Optional[list[int]] = None
    n_day_records: Optional[int] = None
    n_employees: Optional[int] = None
    error_text: Optional[str] = None
    created_at: datetime
    finished_at: Optional[datetime] = None


class DayRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    employee_id: int
    employee_name: Optional[str] = None
    work_date: str
    is_weekend: bool
    int_entry: Optional[str] = None
    int_exit: Optional[str] = None
    lez_entry: Optional[str] = None
    lez_exit: Optional[str] = None
    entry: Optional[str] = None
    exit: Optional[str] = None
    entry_source: Optional[str] = None
    exit_source: Optional[str] = None
    start_fixed: bool = False
    lunch_deducted: float = 0.0
    worked_hours: float
    lateness_min: int
    overtime_h: float
    absence: Optional[str] = None
    dept_name: Optional[str] = None
    cabinet: Optional[str] = None
    deviations: list = []


class PeriodOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    employee_id: int
    employee_name: Optional[str] = None
    dept_name: Optional[str] = None
    schedule_code: Optional[str] = None
    worked_total: float
    credited_total: float
    period_norm: float
    percent: float
    bucket: Optional[str] = None
    late_count: int
    late_minutes: int
    overtime_total: float
    overtime_pay: Optional[float] = None
