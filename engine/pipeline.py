# -*- coding: utf-8 -*-
"""Оркестратор расчёта табеля без состояния (аналог аналитического блока
SCUD.start(), но без tkinter/глобалей/мутации Сотрудники.txt).

Это будущий services/ingestion.py: на вход — рабочая папка с выгрузками и
справочниками, на выход — DayRecord/EmployeePeriod и аналитический xlsx.
Старые листы «Выгрузка»/«Фиксированное время» (на базе find_emp) НЕ строит —
они заменяются нормализованной моделью DayRecord.
"""
import os

import pandas as pd

from . import bases, compute, model, refdata, report, shifts
from .calendar import legacy_weekend
from .employees import load_fixed_start_employees
from .names import name_format


def compute_day_records(wp, ref=None, fixed=None, weekend_fn=None, thresholds=None,
                        names=None):
    """Строит {ФИО: [DayRecord]} из выгрузок в папке wp.

    names — необязательное множество ФИО-фильтр (для точного воспроизведения
    выборки сотрудников легаси start(): активные из Сотрудники.txt). Если None —
    берутся ВСЕ сотрудники с отметками (base ∪ lezbase).

    Возвращает (records, ref, points, weekend_fn, thresholds)."""
    if weekend_fn is None:
        weekend_fn = legacy_weekend
    if thresholds is None:
        thresholds = {**model.THRESHOLDS, **refdata.load_settings(wp)}
    if ref is None:
        ref = refdata.load_reference_data(wp, name_normalizer=name_format)
    if fixed is None:
        fixed = load_fixed_start_employees(wp, name_format)

    base, lezbase, points = bases.build_bases(wp)
    allnames = set(base) | set(lezbase)
    if names is not None:
        allnames &= set(names)
    rebuild = {n: [] for n in allnames}
    records = shifts.build_day_records(
        rebuild, base, lezbase, ref=ref, fixed_employees=fixed, apply_fixed=True,
        thresholds=thresholds, weekend_fn=weekend_fn,
    )
    return records, ref, points, weekend_fn, thresholds


def build_periods(records, ref, weekend_fn, thresholds):
    """Добавляет записи-отсутствия и сворачивает в {ФИО: EmployeePeriod}.

    ВНИМАНИЕ: мутирует records (как start()): добавляет дни-отсутствия."""
    span = compute.date_span_of(records)
    compute.inject_absence_records(records, ref, span, weekend_fn=weekend_fn)
    work_days = compute.count_working_days(span, weekend_fn=weekend_fn)
    periods = compute.build_employee_periods(
        records, ref=ref, working_days=work_days, thresholds=thresholds)
    return periods


def write_analytic_workbook(wp, out_path, names=None):
    """Строит аналитический xlsx (Отклонения / по отделам / Бухгалтерия /
    Нормы / Опоздания) — те же листы, что start() добавляет в «Общую выгрузку».
    Порядок операций идентичен start() (отклонения ДО inject_absence).
    names — фильтр сотрудников (см. compute_day_records)."""
    records, ref, points, we, th = compute_day_records(wp, names=names)
    with pd.ExcelWriter(out_path, engine="xlsxwriter") as writer:
        wb = writer.book
        fmts = report.report_formats(wb)
        used = set()
        report.write_deviations_sheet(writer, records, fmts, weekend_fn=we)
        used.add("Отклонения")
        # inject_absence ПОСЛЕ листа отклонений (как в start)
        periods = build_periods(records, ref, we, th)
        report.write_department_sheets(writer, records, fmts, weekend_fn=we, used_names=used)
        report.write_accounting_sheet(writer, periods, fmts)
        report.write_norms_sheet(writer, periods, fmts)
        report.write_late_overtime_sheet(writer, periods, fmts)
    return out_path
