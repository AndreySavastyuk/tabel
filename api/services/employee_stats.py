# -*- coding: utf-8 -*-
"""Сводка по сотруднику для карточки: помесячно (по всем прогонам) + дни месяца.

Если один и тот же день встречается в нескольких прогонах (перезапуски/наложения
периодов) — берётся запись из САМОГО ПОЗДНЕГО прогона. Месяц = из даты дня."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import DayRecordRow, Employee, PipelineRun, ScheduleNorm
from . import time_adjust


def _month_of(work_date: str) -> str:
    d, m, y = work_date.split(".")
    return f"{y}-{m}"


def _dedup_latest(db: Session, employee_id: int, month: str | None = None):
    """DayRecordRow по сотруднику, по одному на дату. Приоритет: финальный
    (утверждённый) прогон периода; иначе самый поздний. Тай-брейк детерминирован:
    при равном created_at побеждает больший run_id."""
    rows = db.execute(
        select(DayRecordRow, PipelineRun.created_at, PipelineRun.is_final)
        .join(PipelineRun, PipelineRun.id == DayRecordRow.run_id)
        .where(DayRecordRow.employee_id == employee_id)).all()
    by_date: dict = {}
    for r, created, is_final in rows:
        if month and _month_of(r.work_date) != month:
            continue
        key = (1 if is_final else 0, created, r.run_id)
        cur = by_date.get(r.work_date)
        if cur is None or key > cur[1]:
            by_date[r.work_date] = (r, key)
    return [r for r, _ in by_date.values()]


def latest_run_for_day(db: Session, employee_id: int, work_date: str,
                       run_id: int | None = None):
    """(DayRecordRow, PipelineRun) выбранного дня. По умолчанию — самый поздний
    прогон с детерминированным тай-брейком (created_at, run_id). ``run_id``
    фиксирует конкретный прогон. Возвращает (None, None), если дня нет.

    Семантика стабильна для будущей эволюции (приоритет финального прогона):
    потребители (карточка, объяснение дня) зовут один helper."""
    stmt = (select(DayRecordRow, PipelineRun)
            .join(PipelineRun, PipelineRun.id == DayRecordRow.run_id)
            .where(DayRecordRow.employee_id == employee_id,
                   DayRecordRow.work_date == work_date))
    if run_id is not None:
        stmt = stmt.where(DayRecordRow.run_id == run_id)
    rows = db.execute(stmt).all()
    if not rows:
        return None, None
    dr, run = max(rows, key=lambda rr: (1 if rr[1].is_final else 0, rr[1].created_at, rr[1].id))
    return dr, run


def monthly_summaries(db: Session, employee_id: int) -> list[dict]:
    rows = _dedup_latest(db, employee_id)
    emp = db.get(Employee, employee_id)
    norms: dict = {}
    if emp and emp.schedule_id:
        for n in db.scalars(select(ScheduleNorm).where(ScheduleNorm.schedule_id == emp.schedule_id)):
            norms[n.month] = float(n.norm_hours)

    dmap = time_adjust.deduction_map(db)
    months: dict = {}
    for r in rows:
        mk = _month_of(r.work_date)
        a = months.setdefault(mk, {"work_days": 0, "worked": 0.0, "ot": 0.0,
                                   "late_days": 0, "late_min": 0, "absent": 0})
        # вычет времени вне территории (решение кадров/бухгалтера) уменьшает часы
        worked = time_adjust.apply_day(r.worked_hours, dmap.get((employee_id, r.work_date), 0))
        if r.entry and r.exit and worked > 0:
            a["worked"] += worked
            a["work_days"] += 1
        a["ot"] += float(r.overtime_h)
        if r.lateness_min > 0:
            a["late_days"] += 1
            a["late_min"] += r.lateness_min
        if r.absence:
            a["absent"] += 1

    out = []
    for mk in sorted(months, reverse=True):
        a = months[mk]
        worked = round(a["worked"], 2)
        norm = norms.get(mk)
        out.append({
            "month": mk,
            "work_days": a["work_days"],
            "worked_total": worked,
            "overtime_total": round(a["ot"], 2),
            "late_days": a["late_days"],
            "late_minutes": a["late_min"],
            "absence_days": a["absent"],
            "norm_hours": norm,
            "balance": round(worked - norm, 2) if norm else None,
            "percent": round(worked / norm * 100, 1) if norm else None,
        })
    return out


def daily_records(db: Session, employee_id: int, month: str):
    rows = _dedup_latest(db, employee_id, month=month)
    rows.sort(key=lambda r: tuple(reversed(r.work_date.split("."))))
    return rows
