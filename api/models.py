# -*- coding: utf-8 -*-
"""ORM-модели (SQLAlchemy 2.0). Типы выбраны переносимыми между SQLite и
PostgreSQL: строковые «энумы», Numeric для часов/денег, JSON для свободных
структур. Идентичность сотрудника — через PK employees.id + employee_aliases
(вместо хрупкого сопоставления по ФИО в легаси)."""
from datetime import date, datetime, timezone

from sqlalchemy import (Boolean, Date, DateTime, ForeignKey, Index, Integer,
                        JSON, Numeric, String, Text, UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), index=True)          # constants.Role
    full_name: Mapped[str | None] = mapped_column(String(255))
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    department = relationship("Department")


class Department(Base):
    __tablename__ = "departments"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"))


class Schedule(Base):
    __tablename__ = "schedules"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    shift_start: Mapped[str | None] = mapped_column(String(5))         # "HH:MM"
    shift_len: Mapped[float | None] = mapped_column(Numeric(5, 2))     # часы
    lunch_start: Mapped[str | None] = mapped_column(String(5))
    lunch_end: Mapped[str | None] = mapped_column(String(5))

    norms = relationship("ScheduleNorm", back_populates="schedule",
                         cascade="all, delete-orphan")


class ScheduleNorm(Base):
    __tablename__ = "schedule_norms"
    __table_args__ = (UniqueConstraint("schedule_id", "month", name="uq_norm_sched_month"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    schedule_id: Mapped[int] = mapped_column(ForeignKey("schedules.id"), index=True)
    month: Mapped[str] = mapped_column(String(7))                      # "YYYY-MM"
    norm_hours: Mapped[float] = mapped_column(Numeric(6, 2))

    schedule = relationship("Schedule", back_populates="norms")


class Employee(Base):
    __tablename__ = "employees"
    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(255), index=True)
    normalized_name: Mapped[str] = mapped_column(String(255), index=True)
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"), index=True)
    cabinet: Mapped[str | None] = mapped_column(String(64))
    schedule_id: Mapped[int | None] = mapped_column(ForeignKey("schedules.id"))
    fixed_time: Mapped[str | None] = mapped_column(String(5))          # "HH:MM"
    lez_controlled: Mapped[bool] = mapped_column(Boolean, default=False)
    arrives_by_car: Mapped[bool] = mapped_column(Boolean, default=False)  # заезжает на машине — не сверять с ЛЭЗ
    overtime_tracked: Mapped[bool] = mapped_column(Boolean, default=False)  # ведём учёт переработок
    hourly_rate: Mapped[float | None] = mapped_column(Numeric(10, 2))  # ₽/час (деньги)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    department = relationship("Department")
    schedule = relationship("Schedule")
    aliases = relationship("EmployeeAlias", back_populates="employee",
                          cascade="all, delete-orphan")


class EmployeeAlias(Base):
    __tablename__ = "employee_aliases"
    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    raw_name: Mapped[str] = mapped_column(String(255), index=True)
    normalized_name: Mapped[str] = mapped_column(String(255), index=True)
    source: Mapped[str | None] = mapped_column(String(20))             # constants.AliasSource
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3))
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)

    employee = relationship("Employee", back_populates="aliases")


class Absence(Base):
    __tablename__ = "absences"
    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    type: Mapped[str] = mapped_column(String(20))                      # constants.AbsenceType
    date_from: Mapped[date] = mapped_column(Date)
    date_to: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(12), default="approved")  # отгул → submitted
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)
    note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    employee = relationship("Employee")


class HolidayCalendar(Base):
    __tablename__ = "holiday_calendar"
    id: Mapped[int] = mapped_column(primary_key=True)
    cal_date: Mapped[date] = mapped_column(Date, unique=True, index=True)
    kind: Mapped[str] = mapped_column(String(20))                      # constants.HolidayKind
    note: Mapped[str | None] = mapped_column(String(255))


class AppSetting(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)


# ---------------------------------------------------------------------------
# Фаза 2: загрузки, прогоны, результаты
# ---------------------------------------------------------------------------
class Upload(Base):
    __tablename__ = "uploads"
    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(255))
    source: Mapped[str] = mapped_column(String(20))          # constants.UploadSource
    stored_path: Mapped[str] = mapped_column(String(500))
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(12), default="received")  # received/parsed/failed
    error_text: Mapped[str | None] = mapped_column(Text)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    period_from: Mapped[date | None] = mapped_column(Date)
    period_to: Mapped[date | None] = mapped_column(Date)
    period_label: Mapped[str | None] = mapped_column(String(7), index=True)  # "YYYY-MM" для месячного прогона
    is_final: Mapped[bool] = mapped_column(Boolean, default=False, index=True)  # утверждённый прогон периода
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime)
    finalized_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(12), default="queued")  # queued/running/done/failed
    thresholds: Mapped[dict | None] = mapped_column(JSON)
    upload_ids: Mapped[list | None] = mapped_column(JSON)
    n_day_records: Mapped[int | None] = mapped_column(Integer)
    n_employees: Mapped[int | None] = mapped_column(Integer)
    error_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)


class AccessEvent(Base):
    __tablename__ = "access_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("pipeline_runs.id"), index=True)
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), index=True)
    raw_name: Mapped[str] = mapped_column(String(255))
    event_ts: Mapped[datetime] = mapped_column(DateTime)
    kind: Mapped[str] = mapped_column(String(10))            # Вход/Выход/направление
    source: Mapped[str] = mapped_column(String(10))          # internal/LEZ
    system: Mapped[str | None] = mapped_column(String(20))   # StorK/NC_SIGUR/LEZ/...


class DayRecordRow(Base):
    """Сериализованный engine.model.DayRecord (один день сотрудника прогона)."""
    __tablename__ = "day_records"
    __table_args__ = (UniqueConstraint("run_id", "employee_id", "work_date",
                                       name="uq_day_run_emp_date"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("pipeline_runs.id"), index=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    work_date: Mapped[str] = mapped_column(String(10))      # "DD.MM.YYYY"
    is_weekend: Mapped[bool] = mapped_column(Boolean, default=False)
    int_entry: Mapped[str | None] = mapped_column(String(5))
    int_exit: Mapped[str | None] = mapped_column(String(5))
    lez_entry: Mapped[str | None] = mapped_column(String(5))
    lez_exit: Mapped[str | None] = mapped_column(String(5))
    entry: Mapped[str | None] = mapped_column(String(5))
    exit: Mapped[str | None] = mapped_column(String(5))
    entry_source: Mapped[str | None] = mapped_column(String(10))
    exit_source: Mapped[str | None] = mapped_column(String(10))
    start_fixed: Mapped[bool] = mapped_column(Boolean, default=False)
    original_start: Mapped[str | None] = mapped_column(String(5))
    raw_hours: Mapped[float] = mapped_column(Numeric(6, 2), default=0)
    lunch_deducted: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    worked_hours: Mapped[float] = mapped_column(Numeric(6, 2), default=0)
    schedule_code: Mapped[str | None] = mapped_column(String(64))
    dept_name: Mapped[str | None] = mapped_column(String(255))
    cabinet: Mapped[str | None] = mapped_column(String(64))
    lez_controlled: Mapped[bool] = mapped_column(Boolean, default=False)
    dual_tracked: Mapped[bool] = mapped_column(Boolean, default=False)
    day_norm: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    absence: Mapped[str | None] = mapped_column(String(20))
    lateness_min: Mapped[int] = mapped_column(Integer, default=0)
    overtime_h: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    deviations: Mapped[list] = mapped_column(JSON, default=list)


class PeriodSummary(Base):
    """Сериализованный engine.model.EmployeePeriod (свод сотрудника за прогон)."""
    __tablename__ = "period_summaries"
    __table_args__ = (UniqueConstraint("run_id", "employee_id", name="uq_period_run_emp"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("pipeline_runs.id"), index=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    schedule_code: Mapped[str | None] = mapped_column(String(64))
    dept_name: Mapped[str | None] = mapped_column(String(255))
    worked_total: Mapped[float] = mapped_column(Numeric(8, 2), default=0)
    credited_total: Mapped[float] = mapped_column(Numeric(8, 2), default=0)
    period_norm: Mapped[float] = mapped_column(Numeric(8, 2), default=0)
    absence_days: Mapped[dict] = mapped_column(JSON, default=dict)
    late_count: Mapped[int] = mapped_column(Integer, default=0)
    late_minutes: Mapped[int] = mapped_column(Integer, default=0)
    overtime_total: Mapped[float] = mapped_column(Numeric(7, 2), default=0)
    percent: Mapped[float] = mapped_column(Numeric(6, 1), default=0)
    bucket: Mapped[str | None] = mapped_column(String(10))
    overtime_pay: Mapped[float | None] = mapped_column(Numeric(12, 2))   # Фаза 5 (деньги)


# ---------------------------------------------------------------------------
# Фаза 3: рабочая очередь отклонений (жизненный цикл поверх эфемерных deviations)
# ---------------------------------------------------------------------------
class DeviationItem(Base):
    """Отклонение со стабильным ключом (employee_id|work_date|dev_code),
    переживающим перезапуск прогона: статусы/комментарии/ответственный не
    сбрасываются при пересчёте day_records. is_present=False — отклонение
    исчезло из последнего прогона (данные поправили), но хранится для аудита."""
    __tablename__ = "deviation_items"
    __table_args__ = (
        UniqueConstraint("dedup_key", name="uq_deviation_dedup"),
        Index("ix_deviation_items_status_dept", "status", "department_id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    dedup_key: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("pipeline_runs.id"), index=True)  # последний наблюдавший
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"), index=True)  # скоуп руководителя
    work_date: Mapped[str] = mapped_column(String(10))             # "DD.MM.YYYY"
    dev_code: Mapped[str] = mapped_column(String(40), index=True)  # стабильный код (REENTRY_GAP и т.п.)
    detail: Mapped[str | None] = mapped_column(Text)               # интервалы отлучек для re-entry
    status: Mapped[str] = mapped_column(String(12), default="new")  # constants.DeviationStatus
    # Время вне территории (отлучки ЛЭЗ) и решение по нему. Влияет на зарплатные
    # часы: time_decision='deducted' вычитает deduct_minutes из рабочего дня.
    away_minutes: Mapped[int] = mapped_column(Integer, default=0)   # суммарно за день, мин
    deduct_minutes: Mapped[int | None] = mapped_column(Integer)     # сколько вычесть (None — не решено)
    time_decision: Mapped[str] = mapped_column(String(12), default="pending")  # constants.TimeDecision
    is_present: Mapped[bool] = mapped_column(Boolean, default=True)
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    dept_name: Mapped[str | None] = mapped_column(String(255))     # денорм для отображения
    resolution_note: Mapped[str | None] = mapped_column(Text)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)
    resolved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime)

    comments = relationship("DeviationComment", back_populates="deviation",
                            cascade="all, delete-orphan", order_by="DeviationComment.id")


class PeriodState(Base):
    """Состояние закрытия месяца. Единица закрытия — цельный месяц 'YYYY-MM'.
    active_run_id — выбранный «финальный/текущий» прогон периода (иначе берётся
    is_final или последний done)."""
    __tablename__ = "period_states"
    id: Mapped[int] = mapped_column(primary_key=True)
    period: Mapped[str] = mapped_column(String(7), unique=True, index=True)  # "YYYY-MM"
    active_run_id: Mapped[int | None] = mapped_column(ForeignKey("pipeline_runs.id"), index=True)
    status: Mapped[str] = mapped_column(String(12), default="open")  # constants.PeriodCloseStatus
    closed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime)
    reopened_at: Mapped[datetime | None] = mapped_column(DateTime)
    note: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class DeviationComment(Base):
    """Комментарий/история смены статуса отклонения (аудит-трейл)."""
    __tablename__ = "deviation_comments"
    id: Mapped[int] = mapped_column(primary_key=True)
    deviation_id: Mapped[int] = mapped_column(ForeignKey("deviation_items.id"), index=True)
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str | None] = mapped_column(Text)
    old_status: Mapped[str | None] = mapped_column(String(12))
    new_status: Mapped[str | None] = mapped_column(String(12))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    deviation = relationship("DeviationItem", back_populates="comments")
