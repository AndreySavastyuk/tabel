# -*- coding: utf-8 -*-
"""Объяснение расчёта одного дня одного сотрудника: сырые события СКУД/ЛЭЗ,
выбор входа/выхода, вычет обеда, фиксированное время, норма дня, применённые
пороги и пошаговая формула.

Всё строится из УЖЕ сохранённых значений day_records (движок НЕ пересчитывается)
— это трассировка результата, а не повторный расчёт. Прогон выбирается тем же
helper'ом, что и карточка сотрудника (latest_run_for_day), чтобы объяснение
совпадало с отображаемыми цифрами.

Ограничение MVP: сырые события фильтруются по КАЛЕНДАРНЫМ суткам work_date.
Для ночных смен движок сопоставляет события окну смены, поэтому набор событий
в объяснении может отличаться — это помечается на UI."""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from engine import model as emodel

from ..models import AccessEvent, Employee, Schedule
from ..schemas import (DayExplainOut, DayRecordOut, FormulaStep, RawEvent,
                       RunBrief, ScheduleBrief)
from .employee_stats import latest_run_for_day
from .refdata_from_db import load_thresholds


def _parse_day(work_date: str):
    try:
        return datetime.strptime(work_date, "%d.%m.%Y").date()
    except ValueError:
        return None


def _build_formula(dr) -> list[FormulaStep]:
    """Пошаговая формула из сохранённых чисел дня (без пересчёта движком)."""
    raw_h = float(dr.raw_hours or 0)
    lunch = float(dr.lunch_deducted or 0)
    worked = float(dr.worked_hours or 0)
    steps = [
        FormulaStep(key="raw_hours", label="Время в здании (выход − вход)",
                    value=round(raw_h, 2), unit="ч"),
        FormulaStep(key="lunch", label="Вычет обеда",
                    value=-round(lunch, 2), unit="ч"),
        FormulaStep(key="worked", label="Отработано",
                    value=round(worked, 2), unit="ч"),
    ]
    if dr.lateness_min:
        steps.append(FormulaStep(key="lateness", label="Опоздание",
                                 value=float(dr.lateness_min), unit="мин"))
    if dr.overtime_h:
        steps.append(FormulaStep(key="overtime", label="Переработка",
                                 value=round(float(dr.overtime_h), 2), unit="ч"))
    return steps


def build_day_explanation(db: Session, employee_id: int, work_date: str,
                          run_id: int | None = None) -> DayExplainOut | None:
    dr, run = latest_run_for_day(db, employee_id, work_date, run_id=run_id)
    if dr is None or run is None:
        return None

    emp = db.get(Employee, employee_id)
    day = DayRecordOut.model_validate(dr)
    day.employee_name = emp.full_name if emp else None

    # Сырые события за календарные сутки work_date.
    d = _parse_day(work_date)
    raw: list[RawEvent] = []
    if d is not None:
        evs = db.scalars(
            select(AccessEvent).where(AccessEvent.run_id == run.id,
                                      AccessEvent.employee_id == employee_id)).all()
        evs = sorted((e for e in evs if e.event_ts.date() == d),
                     key=lambda e: e.event_ts)
        raw = [RawEvent(event_ts=e.event_ts, time=e.event_ts.strftime("%H:%M"),
                        kind=e.kind, source=e.source, system=e.system) for e in evs]

    # График — по снимку прогона (schedule_code), не по текущему Employee.
    schedule = None
    if dr.schedule_code:
        s = db.scalar(select(Schedule).where(Schedule.code == dr.schedule_code))
        if s is not None:
            schedule = ScheduleBrief(
                code=s.code, shift_start=s.shift_start,
                shift_len=float(s.shift_len) if s.shift_len is not None else None,
                lunch_start=s.lunch_start, lunch_end=s.lunch_end)

    # Пороги — снимок прогона, иначе текущие (с пометкой источника).
    if run.thresholds:
        thresholds = dict(run.thresholds)
        thresholds_source = "run_snapshot"
    else:
        thresholds = {**emodel.THRESHOLDS, **load_thresholds(db)}
        thresholds_source = "current"

    return DayExplainOut(
        day=day, raw_events=raw, schedule=schedule,
        thresholds=thresholds, thresholds_source=thresholds_source,
        formula=_build_formula(dr),
        run=RunBrief(id=run.id, created_at=run.created_at, status=run.status))
