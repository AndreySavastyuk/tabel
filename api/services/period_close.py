# -*- coding: utf-8 -*-
"""Центр закрытия месяца: серверная агрегация готовности (COUNT-ы), выбор
активного прогона периода и фиксация закрытия.

Жёсткие блокеры закрытия (решение владельца): незавершённый прогон, нерешённые
ФИО, сотрудники без графика и без отдела. Остальное (неподтверждённые отгулы,
открытые отклонения, потерянные ФИО) — предупреждения, не блокируют."""
import calendar
from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..constants import PeriodCloseStatus
from ..models import (Absence, AccessEvent, DeviationItem, Employee,
                      EmployeeAlias, PeriodState, PipelineRun, Upload)
from ..schemas import ChecklistItem, ClosingSummaryOut, MonthPeriodOut, RunOut


def _month_bounds(period: str):
    y, m = (int(x) for x in period.split("-"))
    return date(y, m, 1), date(y, m, calendar.monthrange(y, m)[1])


def active_run(db: Session, period: str, run_id=None):
    """Активный прогон периода: явный run_id → period_states.active_run_id →
    финальный → последний done (детерминированный тай-брейк)."""
    if run_id is not None:
        return db.get(PipelineRun, run_id)
    ps = db.scalar(select(PeriodState).where(PeriodState.period == period))
    if ps and ps.active_run_id:
        r = db.get(PipelineRun, ps.active_run_id)
        if r:
            return r
    fin = db.scalar(select(PipelineRun).where(
        PipelineRun.period_label == period, PipelineRun.is_final.is_(True)))
    if fin:
        return fin
    runs = db.scalars(select(PipelineRun).where(
        PipelineRun.period_label == period, PipelineRun.status == "done")).all()
    if not runs:
        return None
    return max(runs, key=lambda r: (r.created_at, r.id))


def list_periods(db: Session, limit: int = 24):
    rows = db.execute(
        select(PipelineRun.period_label, func.count(), func.max(PipelineRun.created_at))
        .where(PipelineRun.period_label.is_not(None))
        .group_by(PipelineRun.period_label)
        .order_by(PipelineRun.period_label.desc()).limit(limit)).all()
    states = {ps.period: ps for ps in db.scalars(select(PeriodState))}
    out = []
    for period, n_runs, last_at in rows:
        ps = states.get(period)
        out.append(MonthPeriodOut(
            period=period, status=(ps.status if ps else PeriodCloseStatus.open.value),
            active_run_id=(ps.active_run_id if ps else None),
            n_runs=n_runs, last_run_at=last_at, closed_at=(ps.closed_at if ps else None)))
    return out


def build_closing_summary(db: Session, period: str, run_id=None) -> ClosingSummaryOut:
    run = active_run(db, period, run_id)
    d0, d1 = _month_bounds(period)

    up_counts = {s: c for s, c in db.execute(
        select(Upload.status, func.count()).group_by(Upload.status))}
    uploads = {"total": sum(up_counts.values()), "by_status": up_counts}

    aliases = db.scalar(select(func.count()).select_from(EmployeeAlias)
                        .where(EmployeeAlias.confirmed.is_(False))) or 0
    no_dep = db.scalar(select(func.count()).select_from(Employee)
                       .where(Employee.is_active.is_(True), Employee.department_id.is_(None))) or 0
    no_sched = db.scalar(select(func.count()).select_from(Employee)
                         .where(Employee.is_active.is_(True), Employee.schedule_id.is_(None))) or 0
    abs_pending = db.scalar(select(func.count()).select_from(Absence).where(
        Absence.status == "submitted", Absence.date_from <= d1, Absence.date_to >= d0)) or 0

    dev_total = dev_open = lost = 0
    by_code = {}
    if run:
        for code, st, c in db.execute(
                select(DeviationItem.dev_code, DeviationItem.status, func.count())
                .where(DeviationItem.run_id == run.id, DeviationItem.is_present.is_(True))
                .group_by(DeviationItem.dev_code, DeviationItem.status)):
            by_code[code] = by_code.get(code, 0) + c
            dev_total += c
            if st in ("new", "in_progress"):
                dev_open += c
        lost = db.scalar(select(func.count(func.distinct(AccessEvent.raw_name))).where(
            AccessEvent.run_id == run.id, AccessEvent.employee_id.is_(None))) or 0

    run_done = bool(run and run.status == "done")
    export_ready = run_done and aliases == 0 and no_sched == 0 and no_dep == 0

    checklist = [
        ChecklistItem(key="run", label="Прогон завершён", ok=run_done,
                      count=(0 if run_done else 1), blocking=True,
                      link=(f"/runs/{run.id}" if run else None)),
        ChecklistItem(key="aliases", label="Разобраны ФИО", ok=(aliases == 0),
                      count=aliases, blocking=True, link="/aliases"),
        ChecklistItem(key="no_schedule", label="Всем назначен график", ok=(no_sched == 0),
                      count=no_sched, blocking=True, link="/employees"),
        ChecklistItem(key="no_department", label="Всем назначен отдел", ok=(no_dep == 0),
                      count=no_dep, blocking=True, link="/employees"),
        ChecklistItem(key="absences", label="Подтверждены отгулы", ok=(abs_pending == 0),
                      count=abs_pending, blocking=False, link="/absences"),
        ChecklistItem(key="deviations", label="Разобраны отклонения", ok=(dev_open == 0),
                      count=dev_open, blocking=False, link="/deviations"),
        ChecklistItem(key="lost_names", label="Нет потерянных ФИО", ok=(lost == 0),
                      count=lost, blocking=False, link="/aliases"),
    ]

    ps = db.scalar(select(PeriodState).where(PeriodState.period == period))
    return ClosingSummaryOut(
        period=period, status=(ps.status if ps else PeriodCloseStatus.open.value),
        run=(RunOut.model_validate(run) if run else None),
        uploads=uploads, aliases_unresolved=aliases, no_department=no_dep,
        no_schedule=no_sched, absences_pending=abs_pending,
        deviations={"total": dev_total, "open": dev_open, "by_code": by_code},
        lost_names=lost, export_ready=export_ready, checklist=checklist)


def _get_or_create_state(db: Session, period: str) -> PeriodState:
    ps = db.scalar(select(PeriodState).where(PeriodState.period == period))
    if ps is None:
        ps = PeriodState(period=period, status=PeriodCloseStatus.open.value)
        db.add(ps)
    return ps


def set_active_run(db: Session, period: str, run_id: int):
    run = db.get(PipelineRun, run_id)
    if run is None or run.period_label != period:
        return None
    ps = _get_or_create_state(db, period)
    ps.active_run_id = run_id
    db.commit()
    return ps


def close_period(db: Session, period: str, run_id=None, force=False, closed_by=None):
    """Закрыть месяц. При наличии жёстких блокеров — (None, blockers)."""
    summary = build_closing_summary(db, period, run_id)
    blockers = [c for c in summary.checklist if c.blocking and not c.ok]
    if blockers:
        return None, blockers
    run = active_run(db, period, run_id)
    ps = _get_or_create_state(db, period)
    ps.status = PeriodCloseStatus.closed.value
    if run:
        ps.active_run_id = run.id
    ps.closed_by = closed_by
    ps.closed_at = datetime.now(timezone.utc)
    db.commit()
    return ps, []


def reopen_period(db: Session, period: str, note=None):
    ps = _get_or_create_state(db, period)
    ps.status = PeriodCloseStatus.open.value
    ps.reopened_at = datetime.now(timezone.utc)
    if note:
        ps.note = note
    db.commit()
    return ps
