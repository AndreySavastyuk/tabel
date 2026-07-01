# -*- coding: utf-8 -*-
"""Вычет времени вне территории из отработанных часов — единый слой поверх
неизменного вывода движка.

Решение принимается на отклонении REENTRY_GAP (кадры/бухгалтер) и хранится
run-независимо (пережить перепрогон). Здесь — чтение этих решений и применение
их одинаково во всех потребителях (свод прогона, дневные ячейки, xlsx-экспорт,
карточка сотрудника), чтобы числа на экране и в выгрузке совпадали.

Ключевой инвариант: дневной вычет ограничен отработанными часами дня
(нельзя «уйти» дольше, чем присутствовал), а свод сотрудника = сумма именно
этих ограниченных дневных вычетов. Тогда лист по отделу и лист «Бухгалтерия»
не разъезжаются."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from engine import model as emodel

from ..constants import TimeDecision
from ..models import DayRecordRow, DeviationItem


def deducted_hours(minutes) -> float:
    """Минуты вычета -> часы (2 знака)."""
    return round((minutes or 0) / 60.0, 2)


def deduction_map(db: Session) -> dict:
    """{(employee_id, work_date): вычитаемые минуты} по всем решениям «вычесть».

    Run-независимо: ключ (сотрудник, дата). Потребитель ищет по (emp, дате) дня."""
    out: dict = {}
    for eid, wd, mins in db.execute(
            select(DeviationItem.employee_id, DeviationItem.work_date,
                   DeviationItem.deduct_minutes)
            .where(DeviationItem.dev_code == emodel.DEV_REENTRY,
                   DeviationItem.is_present.is_(True),
                   DeviationItem.time_decision == TimeDecision.deducted.value,
                   DeviationItem.deduct_minutes.isnot(None))):
        if mins:
            out[(eid, wd)] = out.get((eid, wd), 0) + int(mins)
    return out


def apply_day(worked_hours: float, minutes: int) -> float:
    """Отработанные часы дня за вычетом отлучек (не ниже 0)."""
    return round(max(0.0, float(worked_hours or 0) - deducted_hours(minutes)), 2)


def run_applied_by_employee(db: Session, run_id: int, dmap: dict | None = None) -> dict:
    """{employee_id: вычтено часов} по прогону — сумма ДНЕВНЫХ вычетов, каждый из
    которых ограничен отработанными часами дня. Совпадает с суммой правок дневных
    ячеек, поэтому свод и листы по отделам согласованы."""
    dmap = deduction_map(db) if dmap is None else dmap
    out: dict = {}
    for eid, wd, worked in db.execute(
            select(DayRecordRow.employee_id, DayRecordRow.work_date,
                   DayRecordRow.worked_hours).where(DayRecordRow.run_id == run_id)):
        m = dmap.get((eid, wd))
        if not m:
            continue
        applied = min(deducted_hours(m), float(worked or 0))
        if applied > 0:
            out[eid] = round(out.get(eid, 0.0) + applied, 2)
    return out
