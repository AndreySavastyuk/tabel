# -*- coding: utf-8 -*-
"""Pydantic-схемы запросов/ответов (v2). Денежные поля (hourly_rate) отдаются
только money-ролям — см. employee_out()."""
import re
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

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


# --- reference import (Excel -> DB) ---
class ReferenceCounts(BaseModel):
    departments: int
    schedules: int
    norms: int
    employees: int
    absences: int


class ReferenceImportResult(BaseModel):
    kind: str
    filename: str
    before: ReferenceCounts
    after: ReferenceCounts


# --- settings (кабинеты, пороги расчёта) ---
class CabinetOut(BaseModel):
    name: str
    count: int


class CabinetRename(BaseModel):
    old_name: str
    new_name: str


class ThresholdItem(BaseModel):
    key: str
    label: str
    unit: str
    value: float
    default: float


class ThresholdsIn(BaseModel):
    values: dict[str, float]


# --- bulk assign from file (ФИО -> отдел/график) ---
class AssignCandidate(BaseModel):
    employee_id: int
    full_name: str
    department_id: Optional[int] = None
    score: float


class AssignPreviewRow(BaseModel):
    row: int
    raw_name: str
    department_name: Optional[str] = None
    schedule_code: Optional[str] = None
    cabinet: Optional[str] = None
    status: str                       # matched | ambiguous | not_found
    match: Optional[AssignCandidate] = None
    candidates: list[AssignCandidate] = []


class AssignItem(BaseModel):
    employee_id: int
    department_name: Optional[str] = None
    schedule_code: Optional[str] = None
    cabinet: Optional[str] = None


class AssignApplyIn(BaseModel):
    items: list[AssignItem]


class AssignApplyResult(BaseModel):
    updated: int
    departments_created: list[str]
    schedules_created: list[str]


# --- name aliases / reconciliation ---
class AliasCandidate(BaseModel):
    employee_id: int
    full_name: str
    department_id: Optional[int] = None
    score: float
    canonical: bool


class UnresolvedAlias(BaseModel):
    id: int
    employee_id: int
    raw_name: str
    normalized_name: str
    source: Optional[str] = None
    candidates: list[AliasCandidate]


class MergeIn(BaseModel):
    target_employee_id: int


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
    # Период прогона: либо month 'YYYY-MM', либо диапазон period_from/period_to
    # (включительно). Не задан — legacy: весь диапазон данных.
    period: Optional[str] = None
    period_from: Optional[date] = None
    period_to: Optional[date] = None

    @model_validator(mode="after")
    def _check_period(self) -> "RunCreate":
        if self.period is not None:
            if not re.match(r"^\d{4}-\d{2}$", self.period):
                raise ValueError("period должен быть в формате YYYY-MM")
            if self.period_from is not None or self.period_to is not None:
                raise ValueError("Укажите либо period (месяц), либо period_from/period_to, не оба")
        elif self.period_from is not None or self.period_to is not None:
            if self.period_from is None or self.period_to is None:
                raise ValueError("Для диапазона нужны и period_from, и period_to")
            if self.period_from > self.period_to:
                raise ValueError("period_from позже period_to")
        return self


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    status: str
    upload_ids: Optional[list[int]] = None
    period_from: Optional[date] = None
    period_to: Optional[date] = None
    period_label: Optional[str] = None
    is_final: bool = False
    finalized_at: Optional[datetime] = None
    finalized_by: Optional[int] = None
    n_day_records: Optional[int] = None
    n_employees: Optional[int] = None
    error_text: Optional[str] = None
    created_at: datetime
    finished_at: Optional[datetime] = None


class DeviationItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    run_id: int
    employee_id: int
    employee_name: Optional[str] = None
    work_date: str
    dev_code: str
    dev_label: Optional[str] = None
    detail: Optional[str] = None
    status: str
    away_minutes: int = 0
    deduct_minutes: Optional[int] = None
    time_decision: str = "pending"
    is_present: bool
    assignee_id: Optional[int] = None
    assignee_name: Optional[str] = None
    dept_name: Optional[str] = None
    resolution_note: Optional[str] = None
    first_seen_at: datetime
    last_seen_at: datetime
    comment_count: int = 0


class DeviationCommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    author_id: Optional[int] = None
    author_name: Optional[str] = None
    body: Optional[str] = None
    old_status: Optional[str] = None
    new_status: Optional[str] = None
    created_at: datetime


class DeviationDetailOut(DeviationItemOut):
    comments: list[DeviationCommentOut] = []


class DeviationPatch(BaseModel):
    status: Optional[str] = None
    assignee_id: Optional[int] = None
    note: Optional[str] = None
    time_decision: Optional[str] = None      # только кадры/бухгалтер
    deduct_minutes: Optional[int] = None      # сколько минут вычесть (по умолч. — вся сумма)


class DeviationBulkIn(BaseModel):
    ids: list[int]
    status: Optional[str] = None
    assignee_id: Optional[int] = None
    note: Optional[str] = None
    time_decision: Optional[str] = None      # только кадры/бухгалтер


class DeviationCommentIn(BaseModel):
    body: str


class DayDiff(BaseModel):
    employee_id: int
    employee_name: Optional[str] = None
    work_date: str
    fields: dict = {}                # {имя_поля: {"from": ..., "to": ...}}


class RunDiffOut(BaseModel):
    base_run_id: int
    other_run_id: int
    n_added: int
    n_removed: int
    n_changed: int
    added: list[DayDiff] = []
    removed: list[DayDiff] = []
    changed: list[DayDiff] = []


# --- центр закрытия месяца ---
class MonthPeriodOut(BaseModel):
    period: str                       # "YYYY-MM"
    status: str                       # open/closing/closed
    active_run_id: Optional[int] = None
    n_runs: int = 0
    last_run_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None


class ChecklistItem(BaseModel):
    key: str
    label: str
    ok: bool
    count: int = 0
    blocking: bool = False            # мешает закрытию (hard gate)
    link: Optional[str] = None


class ClosingSummaryOut(BaseModel):
    period: str
    status: str
    run: Optional[RunOut] = None
    uploads: dict = {}                # {total, by_status}
    aliases_unresolved: int = 0
    no_department: int = 0
    no_schedule: int = 0
    absences_pending: int = 0
    deviations: dict = {}             # {total, open, by_code}
    lost_names: int = 0
    export_ready: bool = False
    checklist: list[ChecklistItem] = []


class PeriodCloseIn(BaseModel):
    run_id: Optional[int] = None
    force: bool = False               # закрыть, несмотря на не-blocking предупреждения


class PeriodReopenIn(BaseModel):
    note: Optional[str] = None


class PeriodActiveRunIn(BaseModel):
    run_id: int


class UserBrief(BaseModel):
    """Краткая карточка пользователя (для назначения ответственного)."""
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    full_name: Optional[str] = None
    role: str


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
    # Вычет времени вне территории (решение по отклонению REENTRY_GAP этого дня).
    deduct_minutes: int = 0
    effective_hours: Optional[float] = None   # worked_hours за вычетом отлучек (None = нет вычета)
    lateness_min: int
    overtime_h: float
    absence: Optional[str] = None
    dept_name: Optional[str] = None
    cabinet: Optional[str] = None
    deviations: list = []
    # Расширение для объяснения дня (колонки уже в day_records).
    raw_hours: float = 0.0
    original_start: Optional[str] = None
    day_norm: float = 0.0
    schedule_code: Optional[str] = None


class RawEvent(BaseModel):
    """Сырое событие СКУД/ЛЭЗ за день (для трассировки расчёта)."""
    event_ts: datetime
    time: str                       # "HH:MM"
    kind: str                       # Вход/Выход/направление
    source: str                     # internal/LEZ
    system: Optional[str] = None    # StorK/NC_SIGUR/LEZ/...


class ScheduleBrief(BaseModel):
    code: Optional[str] = None
    shift_start: Optional[str] = None
    shift_len: Optional[float] = None
    lunch_start: Optional[str] = None
    lunch_end: Optional[str] = None


class FormulaStep(BaseModel):
    key: str                        # машинный ключ шага (raw_hours/lunch/...)
    label: str
    value: float
    unit: str                       # "ч" | "мин"
    detail: Optional[str] = None


class RunBrief(BaseModel):
    id: int
    created_at: datetime
    status: str


class DayExplainOut(BaseModel):
    """Полное объяснение расчёта одного дня (read-only трассировка)."""
    day: DayRecordOut
    raw_events: list[RawEvent] = []
    schedule: Optional[ScheduleBrief] = None
    thresholds: dict = {}
    thresholds_source: str          # run_snapshot | current
    formula: list[FormulaStep] = []
    run: RunBrief


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
    deducted_hours: float = 0.0   # вычтено времени вне территории за период (уже учтено в worked_total)
    late_count: int
    late_minutes: int
    overtime_total: float
    overtime_pay: Optional[float] = None
