# -*- coding: utf-8 -*-
"""Excel-экспорт: восстанавливает DayRecord/EmployeePeriod из БД и кормит
писатели engine.report — те же листы, что строит legacy start()/pipeline.
Порядок листов и логика идентичны pipeline.write_analytic_workbook."""
from io import BytesIO

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from engine import compute, model, report
from engine.calendar import make_calendar_weekend_fn

from ..models import DayRecordRow, Employee, PeriodSummary
from . import time_adjust
from .refdata_from_db import load_calendar


def _emp_names(db: Session) -> dict:
    return {e.id: e.normalized_name for e in db.scalars(select(Employee)).all()}


def _records_from_db(db: Session, run_id: int, dmap: dict) -> dict:
    names = _emp_names(db)
    recs: dict = {}
    rows = db.scalars(
        select(DayRecordRow).where(DayRecordRow.run_id == run_id)
        .order_by(DayRecordRow.id)).all()
    for r in rows:
        dr = model.DayRecord(name=names.get(r.employee_id, ""), date=r.work_date)
        dr.is_weekend = r.is_weekend
        dr.int_entry, dr.int_exit = r.int_entry, r.int_exit
        dr.lez_entry, dr.lez_exit = r.lez_entry, r.lez_exit
        dr.entry, dr.exit = r.entry, r.exit
        dr.entry_source, dr.exit_source = r.entry_source, r.exit_source
        dr.start_fixed, dr.original_start = r.start_fixed, r.original_start
        dr.raw_hours = float(r.raw_hours)
        dr.lunch_deducted = float(r.lunch_deducted)
        # Вычет времени вне территории (решение кадров/бухгалтера) — уменьшает
        # отработанные часы дня. Ограничен часами дня (см. time_adjust.apply_day).
        m = dmap.get((r.employee_id, r.work_date), 0)
        dr.worked_hours = time_adjust.apply_day(r.worked_hours, m) if m else float(r.worked_hours)
        dr.schedule, dr.dept, dr.cabinet = r.schedule_code, r.dept_name, r.cabinet
        dr.lez_controlled, dr.dual_tracked = r.lez_controlled, r.dual_tracked
        dr.day_norm = float(r.day_norm)
        dr.absence = r.absence
        dr.lateness_min = r.lateness_min
        dr.overtime_h = float(r.overtime_h)
        dr.deviations = list(r.deviations or [])
        recs.setdefault(dr.name, []).append(dr)
    # Сотрудники прогона без валидных смен имеют свод, но 0 day_records.
    # В прямом пути они присутствуют как records[name]=[] (пустая строка в
    # листе отдела) — воспроизводим это, иначе листы по отделам разъедутся.
    for (eid,) in db.execute(
            select(PeriodSummary.employee_id).where(PeriodSummary.run_id == run_id)):
        recs.setdefault(names.get(eid, ""), [])
    return recs


def _periods_from_db(db: Session, run_id: int, applied: dict) -> dict:
    names = _emp_names(db)
    out: dict = {}
    for p in db.scalars(select(PeriodSummary).where(PeriodSummary.run_id == run_id)).all():
        ep = model.EmployeePeriod(name=names.get(p.employee_id, ""))
        ep.schedule, ep.dept = p.schedule_code, p.dept_name
        ep.worked_total = float(p.worked_total)
        ep.credited_total = float(p.credited_total)
        ep.period_norm = float(p.period_norm)
        ep.absence_days = dict(p.absence_days or {})
        ep.late_count = p.late_count
        ep.late_minutes = p.late_minutes
        ep.overtime_total = float(p.overtime_total)
        ep.percent = float(p.percent)
        ep.bucket = p.bucket or ""
        # Тот же вычет, что и по дням (сумма ограниченных дневных вычетов) —
        # лист по отделу и лист «Бухгалтерия» остаются согласованными.
        ded = applied.get(p.employee_id, 0.0)
        if ded:
            ep.worked_total = round(ep.worked_total - ded, 2)
            ep.credited_total = round(ep.credited_total - ded, 2)
            if ep.period_norm > 0:
                ep.percent = round(ep.credited_total / ep.period_norm * 100.0, 1)
                ep.bucket = compute.bucket_of(ep.percent)
        out[ep.name] = ep
    return out


def write_workbook_from(records: dict, periods: dict, weekend_fn) -> BytesIO:
    """Строит аналитический xlsx из готовых DayRecord/EmployeePeriod."""
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        wb = writer.book
        fmts = report.report_formats(wb)
        used: set = set()
        report.write_deviations_sheet(writer, records, fmts, weekend_fn=weekend_fn)
        used.add("Отклонения")
        report.write_department_sheets(writer, records, fmts, weekend_fn=weekend_fn, used_names=used)
        report.write_accounting_sheet(writer, periods, fmts)
        report.write_norms_sheet(writer, periods, fmts)
        report.write_late_overtime_sheet(writer, periods, fmts)
    buf.seek(0)
    return buf


def write_workbook(db: Session, run_id: int) -> BytesIO:
    """Аналитический xlsx прогона из БД (с учётом вычетов времени вне территории)."""
    dmap = time_adjust.deduction_map(db)
    applied = time_adjust.run_applied_by_employee(db, run_id, dmap)
    records = _records_from_db(db, run_id, dmap)
    periods = _periods_from_db(db, run_id, applied)
    weekend_fn = make_calendar_weekend_fn(*load_calendar(db))
    return write_workbook_from(records, periods, weekend_fn)
