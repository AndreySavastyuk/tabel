# -*- coding: utf-8 -*-
"""Сборка engine.refdata.RefData и сопутствующих структур ИЗ БД.

Цель — отдать движку ровно ту же форму данных, что раньше читалась из
ЛЭЗ/*.xlsx, чтобы build_day_records/build_employee_periods работали без
изменений. Воспроизводит семантику refdata.load_reference_data: «Без отдела»
и пустые значения НЕ кладутся в словари (их закрывает фолбэк RefData)."""
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from engine.refdata import RefData

from ..models import (Absence, AppSetting, Employee, HolidayCalendar, Schedule,
                      ScheduleNorm)

NO_DEPT = "Без отдела"
THRESHOLDS_KEY = "thresholds"


def build_refdata(db: Session) -> RefData:
    ref = RefData()

    code_by_id = {}
    for s in db.scalars(select(Schedule)).all():
        code_by_id[s.id] = s.code
        if s.shift_start:
            ref.shift_start[s.code] = s.shift_start
        if s.shift_len is not None:
            ref.shift_len[s.code] = float(s.shift_len)
        if s.lunch_start and s.lunch_end:
            ref.lunch[s.code] = (s.lunch_start, s.lunch_end)

    for n in db.scalars(select(ScheduleNorm)).all():
        code = code_by_id.get(n.schedule_id)
        if code:
            ref.norms[(code, n.month)] = float(n.norm_hours)

    norm_by_id = {}
    for e in db.scalars(select(Employee)).all():
        nm = e.normalized_name
        norm_by_id[e.id] = nm
        dept = e.department.name if e.department else None
        if dept and dept != NO_DEPT:
            ref.dept_by_name[nm] = dept
        if e.cabinet:
            ref.cabinet_by_name[nm] = e.cabinet
        if e.schedule:
            ref.schedule_by_name[nm] = e.schedule.code
        if e.fixed_time:
            ref.fixed_times[nm] = e.fixed_time
        ref.lez_controlled[nm] = bool(e.lez_controlled)

    # В зачёт нормы идут ТОЛЬКО подтверждённые отсутствия. отпуск/больничный/
    # командировка создаются сразу approved (факты от кадров/бухгалтерии),
    # отгул — submitted до подтверждения админом/кадрами.
    for a in db.scalars(select(Absence).where(Absence.status == "approved")).all():
        nm = norm_by_id.get(a.employee_id)
        if nm:
            ref.absences.setdefault(nm, []).append((a.type, a.date_from, a.date_to))

    return ref


def build_fixed_times(db: Session) -> dict:
    """{normalized_name: 'HH:MM'} — отдельный аргумент fixed_employees движка."""
    return {e.normalized_name: e.fixed_time
            for e in db.scalars(select(Employee)).all() if e.fixed_time}


def load_nonworking_dates(db: Session) -> set[date]:
    """Нерабочие даты (выходные/праздники) для engine.calendar.make_weekend_fn.
    workday_override (рабочий день, выпавший на сб/вс) исключается."""
    rows = db.scalars(
        select(HolidayCalendar.cal_date)
        .where(HolidayCalendar.kind != "workday_override")).all()
    return set(rows)


def load_calendar(db: Session) -> tuple[set[date], set[date]]:
    """(нерабочие, переносы-на-рабочий) для make_calendar_weekend_fn.

    Нерабочие = праздники + перенесённые выходные (kind holiday/dayoff).
    Сб/вс вычисляются автоматически, в БД хранятся только эти исключения."""
    nonworking, overrides = set(), set()
    for d, kind in db.execute(select(HolidayCalendar.cal_date, HolidayCalendar.kind)):
        if kind == "workday_override":
            overrides.add(d)
        elif kind in ("holiday", "dayoff"):
            nonworking.add(d)
    return nonworking, overrides


def load_calendar_kinds(db: Session) -> tuple[set[date], set[date], set[date]]:
    """(праздники, перенесённые выходные, переносы-на-рабочий) — раздельно.
    Праздники нужны отдельно для предпраздничного сокращения (−1 ч)."""
    holidays, dayoffs, overrides = set(), set(), set()
    for d, kind in db.execute(select(HolidayCalendar.cal_date, HolidayCalendar.kind)):
        if kind == "holiday":
            holidays.add(d)
        elif kind == "dayoff":
            dayoffs.add(d)
        elif kind == "workday_override":
            overrides.add(d)
    return holidays, dayoffs, overrides


def load_thresholds(db: Session) -> dict:
    """Пользовательские пороги из app_settings['thresholds'] (или {})."""
    row = db.get(AppSetting, THRESHOLDS_KEY)
    return dict(row.value) if row and isinstance(row.value, dict) else {}
