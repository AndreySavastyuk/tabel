# -*- coding: utf-8 -*-
"""Поквартальный свод переработок по сотрудникам за год.

Переработка за день (overtime_h, отработано сверх длительности смены) уже
посчитана движком и лежит в day_records. Здесь — агрегация по кварталам (Q1–Q4)
за год: по одному значению на (сотрудник, дата) из АКТУАЛЬНОГО прогона
(финальный → самый поздний), затем сумма по кварталам."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Department, DayRecordRow, Employee, PipelineRun


def _year_quarter(work_date: str) -> tuple[int, int]:
    """('DD.MM.YYYY') -> (год, квартал 1..4)."""
    _, m, y = work_date.split(".")
    return int(y), (int(m) - 1) // 3 + 1


def available_years(db: Session) -> list[int]:
    """Годы, за которые есть day_records (для селектора), по убыванию."""
    years = set()
    for (wd,) in db.execute(select(DayRecordRow.work_date).distinct()):
        try:
            years.add(int(wd.split(".")[2]))
        except (IndexError, ValueError):
            continue
    return sorted(years, reverse=True)


def overtime_report(db: Session, year: int, department_id: int | None = None) -> list[dict]:
    """[{employee, dept, tracked, q1..q4, total}] за год. Дедуп дня по актуальному
    прогону (финальный → max created_at → max run_id). department_id ограничивает
    выборку (скоуп руководителя)."""
    rows = db.execute(
        select(DayRecordRow.employee_id, DayRecordRow.work_date, DayRecordRow.overtime_h,
               PipelineRun.created_at, PipelineRun.is_final, DayRecordRow.run_id)
        .join(PipelineRun, PipelineRun.id == DayRecordRow.run_id)).all()
    best: dict = {}   # (eid, wd) -> (sortkey, overtime, quarter)
    for eid, wd, ot, created, is_final, rid in rows:
        y, q = _year_quarter(wd)
        if y != year:
            continue
        key = (1 if is_final else 0, created, rid)
        cur = best.get((eid, wd))
        if cur is None or key > cur[0]:
            best[(eid, wd)] = (key, float(ot or 0.0), q)

    agg: dict = {}    # eid -> [q1, q2, q3, q4]
    for (eid, _wd), (_key, ot, q) in best.items():
        if ot > 0:
            agg.setdefault(eid, [0.0, 0.0, 0.0, 0.0])[q - 1] += ot
    if not agg:
        return []

    emps = {e.id: e for e in db.scalars(select(Employee).where(Employee.id.in_(list(agg))))}
    depts = {d.id: d.name for d in db.scalars(select(Department))}
    out = []
    for eid, qs in agg.items():
        e = emps.get(eid)
        if e is None:
            continue
        if department_id is not None and e.department_id != department_id:
            continue
        out.append({
            "employee_id": eid,
            "employee_name": e.full_name,
            "dept_name": depts.get(e.department_id),
            "overtime_tracked": bool(e.overtime_tracked),
            "q1": round(qs[0], 2), "q2": round(qs[1], 2),
            "q3": round(qs[2], 2), "q4": round(qs[3], 2),
            "total": round(sum(qs), 2),
        })
    out.sort(key=lambda r: (not r["overtime_tracked"], -r["total"], r["employee_name"]))
    return out
