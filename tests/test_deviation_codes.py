# -*- coding: utf-8 -*-
"""Юнит: стабильная нормализация кода отклонения.

Ключевая защита от регрессии: re-entry распознаётся по ФАКТИЧЕСКОЙ строке из
engine/compute.py:332 ('Выход с территории {mins} мин (...)'), а НЕ по значению
DEV_LABELS[DEV_REENTRY] ('Выход с территории > 30 мин') — оно со строкой не
совпадает, и матч по лейблу всегда давал бы False.

Запуск:  python -m pytest tests/test_deviation_codes.py -q
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from api.services.deviation_codes import detail_of, dev_code
from engine import model as emodel


def test_machine_codes_pass_through():
    for code in (emodel.DEV_ONLY_INTERNAL, emodel.DEV_ONLY_LEZ,
                 emodel.DEV_MISSING_ENTRY, emodel.DEV_MISSING_EXIT,
                 emodel.DEV_TIME_MISMATCH, emodel.DEV_IMPLAUSIBLE,
                 emodel.DEV_REENTRY):
        assert dev_code(code) == code
        assert detail_of(code) is None


def test_reentry_actual_string_normalized():
    item = "Выход с территории 45 мин (12:00→12:50)"
    assert dev_code(item) == emodel.DEV_REENTRY == "REENTRY_GAP"
    # detail — только значимая часть без префикса (лейбл кода уже его содержит).
    assert detail_of(item) == "45 мин (12:00→12:50)"


def test_reentry_label_is_not_the_stored_string():
    label = emodel.DEV_LABELS[emodel.DEV_REENTRY]   # 'Выход с территории > 30 мин'
    assert label != "Выход с территории 45 мин (12:00→12:50)"
    # Матч по префиксу: любая фактическая re-entry-строка нормализуется.
    assert dev_code("Выход с территории 5 мин (08:00→08:05)") == "REENTRY_GAP"


def test_unknown_passes_through():
    assert dev_code("ЧТО-ТО ИНОЕ") == "ЧТО-ТО ИНОЕ"
    assert detail_of("ЧТО-ТО ИНОЕ") is None
