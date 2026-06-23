# -*- coding: utf-8 -*-
"""Юнит- и интеграционные тесты Фазы 2 (compute + build_day_records)."""
import importlib.util
import os
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import compute
import refdata


def approx(a, b, t=0.011):
    return abs(a - b) <= t


# --- compute_lunch_hours (сценарии из решения 3) ---
assert approx(compute.compute_lunch_hours("08:00", "17:00", ("12:00", "12:30")), 0.5)
assert approx(compute.compute_lunch_hours("12:40", "21:00", ("12:00", "12:30")), 0.0)
assert approx(compute.compute_lunch_hours("12:10", "21:00", ("12:00", "12:30")), 0.33)
assert approx(compute.compute_lunch_hours("08:00", "12:15", ("12:00", "12:30")), 0.25)
assert approx(compute.compute_lunch_hours(None, "17:00", ("12:00", "12:30")), 0.0)
assert approx(compute.compute_lunch_hours("23:00", "07:00", ("00:00", "00:30")), 0.5)  # ночная

# --- опоздания ---
assert compute.compute_lateness_min("08:15", "08:00") == 15
assert compute.compute_lateness_min("08:15", "08:00", 10) == 5
assert compute.compute_lateness_min("07:50", "08:00") == 0
assert compute.compute_lateness_min("08:00", None) == 0

# --- переработки ---
assert approx(compute.compute_overtime_hours(9, 8), 1.0)
assert approx(compute.compute_overtime_hours(7, 8), 0.0)
assert approx(compute.compute_overtime_hours(8.25, 8), 0.25)

# --- разрыв на ЛЭЗ ---
assert compute.gap_minutes("12:00", "12:45") == 45
assert compute.gap_minutes("23:50", "00:10") == 20
print("compute unit tests: PASS")


# --- интеграция build_day_records с синтетическим справочником ---
spec = importlib.util.spec_from_file_location(
    "scud", os.path.join(HERE, "SCUD(fixed_time)_v0.3.py")
)
scud = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scud)

ref = refdata.RefData()
name = "Тестов Тест Тестович"
ref.schedule_by_name[name] = "5x2"
ref.dept_by_name[name] = "Цех1"
ref.lez_controlled[name] = True
ref.lunch["5x2"] = ("12:00", "12:30")
ref.shift_start["5x2"] = "08:00"
ref.shift_len["5x2"] = 8
ref.absences[name] = [("отпуск", date(2026, 4, 1), date(2026, 4, 1))]

# build_day_records теперь строит записи из СЫРЫХ событий (rebuild задаёт лишь
# набор сотрудников). Дневная смена + ночная смена через полночь.
rebuild = {name: [{"date": "01.04.2026"}]}
internal = {name: {
    "01.04.2026 08:15": "Вход", "01.04.2026 17:00": "Выход",      # дневная
    "02.04.2026 20:00": "Вход", "03.04.2026 07:30": "Выход",      # ночная через полночь
}}
lez = {name: {"01.04.2026 08:10": "Вход", "01.04.2026 17:05": "Выход"}}

recs = {r.date: r for r in scud.build_day_records(
    rebuild, internal, lez, ref=ref)[name]}
r0 = recs["01.04.2026"]
assert approx(r0.lunch_deducted, 0.5), r0.lunch_deducted
assert approx(r0.worked_hours, 8.25), r0.worked_hours
assert r0.lateness_min == 15, r0.lateness_min
assert approx(r0.overtime_h, 0.25), r0.overtime_h
assert r0.dept == "Цех1" and r0.schedule == "5x2" and r0.lez_controlled
assert r0.int_entry == "08:15" and r0.lez_entry == "08:10", (r0.int_entry, r0.lez_entry)
assert r0.absence == "отпуск", r0.absence
# ночная смена 20:00 -> 07:30 = 11.5 ч (а не ноль/минус)
rn = recs["02.04.2026"]
assert approx(rn.raw_hours, 11.5), rn.raw_hours
assert rn.int_entry == "20:00" and rn.int_exit == "07:30", (rn.int_entry, rn.int_exit)
print("integration test: PASS (вкл. ночную смену)")
print("ALL PHASE 2 TESTS PASS")
