# -*- coding: utf-8 -*-
"""Юнит: флаг «Заезжает на машине» гасит отклонение «Только внутренняя (нет ЛЭЗ)».

Человек заезжает на территорию через автопроезд и не отмечается на проходной
ЛЭЗ. Такой день (есть внутренняя отметка, нет ЛЭЗ) НЕ должен попадать в
отклонение DEV_ONLY_INTERNAL — даже если в другие дни он проходит ЛЭЗ
(dual_tracked=True) или формально помечен «Контроль ЛЭЗ».

Запуск:  python -m pytest tests/test_arrives_by_car.py -q
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import compute, model as emodel


def _internal_only_day(**kw):
    """День только с внутренней отметкой (без ЛЭЗ), часы правдоподобны."""
    dr = emodel.DayRecord(name="иванов и и", date="02.06.2026")
    dr.int_entry, dr.int_exit = "08:00", "17:00"
    dr.entry, dr.exit = "08:00", "17:00"       # выбраны из внутренней
    dr.worked_hours = 8.0
    for k, v in kw.items():
        setattr(dr, k, v)
    return dr


def test_only_internal_flagged_without_car_flag():
    # Базлайн: dual_tracked → день «только внутренняя» помечается.
    dr = _internal_only_day(dual_tracked=True)
    codes = compute.evaluate_deviations(dr)
    assert emodel.DEV_ONLY_INTERNAL in codes


def test_car_flag_suppresses_only_internal_over_dual_tracked():
    dr = _internal_only_day(dual_tracked=True, arrives_by_car=True)
    codes = compute.evaluate_deviations(dr)
    assert emodel.DEV_ONLY_INTERNAL not in codes


def test_car_flag_suppresses_only_internal_over_lez_controlled():
    dr = _internal_only_day(lez_controlled=True, arrives_by_car=True)
    codes = compute.evaluate_deviations(dr)
    assert emodel.DEV_ONLY_INTERNAL not in codes


def test_car_flag_does_not_hide_real_problems():
    # Флаг гасит только «нет ЛЭЗ», а не остальные проверки: нулевые часы всё
    # равно помечаются как неправдоподобные.
    dr = _internal_only_day(dual_tracked=True, arrives_by_car=True)
    dr.int_exit = dr.exit = "08:00"
    dr.worked_hours = 0.0
    codes = compute.evaluate_deviations(dr)
    assert emodel.DEV_ONLY_INTERNAL not in codes
    assert emodel.DEV_IMPLAUSIBLE in codes
