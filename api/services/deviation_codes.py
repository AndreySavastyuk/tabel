# -*- coding: utf-8 -*-
"""Стабильная нормализация кода отклонения (общее основание для очереди
отклонений, центра закрытия и diff прогонов).

Движок (engine/compute.evaluate_deviations) кладёт в ``DayRecordRow.deviations``
смесь: 6 машинных кодов (``ONLY_INTERNAL`` и т.п.) — как есть, и re-entry — как
ОТФОРМАТИРОВАННУЮ строку ``f"Выход с территории {mins} мин (...)"``
(engine/compute.py:332), уникальную для каждого дня. Чтобы группировать/
дедуплицировать отклонения между перезапусками прогона, нужен run-независимый
код. Эти функции вычисляют его ПОВЕРХ неизменной строки — движок и xlsx-вывод
не трогаются (parity сохраняется).

ВАЖНО: re-entry распознаётся по литеральному префиксу строки, а НЕ по значению
``DEV_LABELS[DEV_REENTRY]`` ('Выход с территории > 30 мин') — оно со строкой
'Выход с территории 45 мин (...)' не совпадает."""
from engine import model as emodel

# Машинные коды отклонений из движка — уже стабильны, возвращаются как есть.
_MACHINE_CODES = frozenset({
    emodel.DEV_ONLY_INTERNAL, emodel.DEV_ONLY_LEZ, emodel.DEV_MISSING_ENTRY,
    emodel.DEV_MISSING_EXIT, emodel.DEV_TIME_MISMATCH, emodel.DEV_IMPLAUSIBLE,
    emodel.DEV_REENTRY,
})

# Префикс фактической re-entry-строки из engine/compute.py:332.
_REENTRY_PREFIX = "Выход с территории "


def dev_code(item: str) -> str:
    """Стабильный машинный код отклонения из элемента ``deviations``."""
    if item in _MACHINE_CODES:
        return item
    if item.startswith(_REENTRY_PREFIX):
        return emodel.DEV_REENTRY
    return item


def detail_of(item: str) -> str | None:
    """Человекочитаемая детализация (минуты/время) для re-entry; иначе None.

    Возвращает ТОЛЬКО значимую часть без префикса «Выход с территории »
    ('45 мин (12:00→12:50)'). Лейбл кода в UI уже содержит «Выход с
    территории», поэтому хранить префикс в detail — это дублирование."""
    if item not in _MACHINE_CODES and item.startswith(_REENTRY_PREFIX):
        return item[len(_REENTRY_PREFIX):]
    return None
