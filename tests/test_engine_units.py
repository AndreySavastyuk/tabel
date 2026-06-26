# -*- coding: utf-8 -*-
"""Юнит/интеграционные тесты движка (перенос _test_compute.py + _test_phase4.py
на пакет engine/). Гейт Фазы 0: контракт движка не изменился.

Запуск:  python tests/test_engine_units.py
"""
import os
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import openpyxl

from engine import compute, model, refdata, report, shifts


def approx(a, b, t=0.011):
    return abs(a - b) <= t


# ---------------------------------------------------------------------------
# Часть 1 — compute (сценарии из _test_compute.py)
# ---------------------------------------------------------------------------
assert approx(compute.compute_lunch_hours("08:00", "17:00", ("12:00", "12:30")), 0.5)
assert approx(compute.compute_lunch_hours("12:40", "21:00", ("12:00", "12:30")), 0.0)
assert approx(compute.compute_lunch_hours("12:10", "21:00", ("12:00", "12:30")), 0.33)
assert approx(compute.compute_lunch_hours("08:00", "12:15", ("12:00", "12:30")), 0.25)
assert approx(compute.compute_lunch_hours(None, "17:00", ("12:00", "12:30")), 0.0)
assert approx(compute.compute_lunch_hours("23:00", "07:00", ("00:00", "00:30")), 0.5)  # ночная

assert compute.compute_lateness_min("08:15", "08:00") == 15
assert compute.compute_lateness_min("08:15", "08:00", 10) == 5
assert compute.compute_lateness_min("07:50", "08:00") == 0
assert compute.compute_lateness_min("08:00", None) == 0

assert approx(compute.compute_overtime_hours(9, 8), 1.0)
assert approx(compute.compute_overtime_hours(7, 8), 0.0)
assert approx(compute.compute_overtime_hours(8.25, 8), 0.25)

assert compute.gap_minutes("12:00", "12:45") == 45
assert compute.gap_minutes("23:50", "00:10") == 20
print("compute unit tests: PASS")


# ---------------------------------------------------------------------------
# Часть 2 — build_day_records (интеграция, вкл. ночную смену)
# ---------------------------------------------------------------------------
ref = refdata.RefData()
name = "Тестов Тест Тестович"
ref.schedule_by_name[name] = "5x2"
ref.dept_by_name[name] = "Цех1"
ref.lez_controlled[name] = True
ref.lunch["5x2"] = ("12:00", "12:30")
ref.shift_start["5x2"] = "08:00"
ref.shift_len["5x2"] = 8
ref.absences[name] = [("отпуск", date(2026, 4, 1), date(2026, 4, 1))]

rebuild = {name: [{"date": "01.04.2026"}]}
internal = {name: {
    "01.04.2026 08:15": "Вход", "01.04.2026 17:00": "Выход",      # дневная
    "02.04.2026 20:00": "Вход", "03.04.2026 07:30": "Выход",      # ночная через полночь
}}
lez = {name: {"01.04.2026 08:10": "Вход", "01.04.2026 17:05": "Выход"}}

recs = {r.date: r for r in shifts.build_day_records(rebuild, internal, lez, ref=ref)[name]}
r0 = recs["01.04.2026"]
assert approx(r0.lunch_deducted, 0.5), r0.lunch_deducted
assert approx(r0.worked_hours, 8.25), r0.worked_hours
assert r0.lateness_min == 15, r0.lateness_min
assert approx(r0.overtime_h, 0.25), r0.overtime_h
assert r0.dept == "Цех1" and r0.schedule == "5x2" and r0.lez_controlled
assert r0.int_entry == "08:15" and r0.lez_entry == "08:10", (r0.int_entry, r0.lez_entry)
assert r0.absence == "отпуск", r0.absence
rn = recs["02.04.2026"]
assert approx(rn.raw_hours, 11.5), rn.raw_hours
assert rn.int_entry == "20:00" and rn.int_exit == "07:30", (rn.int_entry, rn.int_exit)
print("build_day_records integration: PASS (вкл. ночную смену)")


# ---------------------------------------------------------------------------
# Часть 3 — свод периодов + аналитические листы (из _test_phase4.py)
# ---------------------------------------------------------------------------
def day(d, worked=None, absence=None, late=0, ot=0.0, dn=8.0, lunch=0.0):
    dr = model.DayRecord(name="", date=d)
    if absence:
        dr.absence = absence
    else:
        dr.entry, dr.exit = "08:00", "17:00"
        dr.worked_hours = worked
        dr.lunch_deducted = lunch
    dr.day_norm = dn
    dr.lateness_min = late
    dr.overtime_h = ot
    return dr


ref2 = refdata.RefData()
for n, dept in [("Иванов", "Цех1"), ("Петров", "Офис"), ("Сидоров", "Цех1")]:
    ref2.dept_by_name[n] = dept
    ref2.schedule_by_name[n] = "5x2"
ref2.norms[("5x2", "2026-04")] = 160
ref2.shift_len["5x2"] = 8

ri = [day(f"{d:02d}.04.2026", worked=8.0) for d in range(1, 9)]
ri += [day(f"{d:02d}.04.2026", absence="отпуск") for d in range(9, 14)]
rp = [day(f"{d:02d}.04.2026", worked=8.0) for d in range(1, 5)]
rp[0].lateness_min = 20
rp[1].overtime_h = 1.5
rs = [day(f"{d:02d}.04.2026", worked=8.0) for d in range(1, 23)]
for r in ri:
    r.name, r.dept, r.cabinet = "Иванов", "Цех1", "Каб1"
for r in rp:
    r.name, r.dept = "Петров", "Офис"
for r in rs:
    r.name, r.dept, r.cabinet = "Сидоров", "Цех1", "Каб2"
records = {"Иванов": ri, "Петров": rp, "Сидоров": rs}

periods = compute.build_employee_periods(records, ref=ref2, months=["2026-04"])
assert abs(periods["Иванов"].percent - 65.0) < 0.1, periods["Иванов"].percent
assert periods["Иванов"].bucket == "50-75%", periods["Иванов"].bucket
assert abs(periods["Петров"].percent - 20.0) < 0.1, periods["Петров"].percent
assert periods["Петров"].bucket == "<25%", periods["Петров"].bucket
assert abs(periods["Сидоров"].percent - 110.0) < 0.1, periods["Сидоров"].percent
assert periods["Сидоров"].bucket == ">75%", periods["Сидоров"].bucket
assert periods["Петров"].late_count == 1 and periods["Петров"].late_minutes == 20
assert abs(periods["Петров"].overtime_total - 1.5) < 0.01
print("period aggregation: PASS")

import pandas as pd

out = os.path.join(HERE, "_test_engine_units.xlsx")
empty = pd.DataFrame([[" "]], columns=["x"])
with pd.ExcelWriter(out, engine="xlsxwriter") as writer:
    empty.to_excel(writer, sheet_name="_")
    wb = writer.book
    fmts = report.report_formats(wb)
    used = {"_"}
    report.write_department_sheets(writer, records, fmts, used_names=used)
    report.write_accounting_sheet(writer, periods, fmts)
    report.write_norms_sheet(writer, periods, fmts)
    report.write_late_overtime_sheet(writer, periods, fmts)

wb2 = openpyxl.load_workbook(out)
names = wb2.sheetnames
cab_sheets = [s for s in names if "Цех1" in s]
assert len(cab_sheets) == 2, cab_sheets
assert any("Офис" in s for s in names), names
assert "Бухгалтерия (аванс)" in names
assert "Нормы" in names
assert "Опоздания и переработки" in names
acc = wb2["Бухгалтерия (аванс)"]
assert [c.value for c in acc[2]][0] == "Петров"
print("analytic sheets: PASS")

print("ALL ENGINE UNIT TESTS PASS")
