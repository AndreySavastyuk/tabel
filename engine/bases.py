# -*- coding: utf-8 -*-
"""Оркестратор парсинга сырых выгрузок (аналог bases_creator, без глобалей).

build_bases(wp) воспроизводит последовательность bases_creator:
  StorK.csv -> SIGUR.xlsx -> report.xls(опц.) -> base_sort -> ЛЭЗ/lez.xlsx
и возвращает (base, lezbase, points) — те же структуры, что ждёт
shifts.build_day_records. Без *_classes/allbase (нужны только легаси find_emp).
"""
import os

from . import timeutil
from .parsers import hikvision, lez, reader, sigur, stork


def build_bases(wp):
    base, lezbase, points = {}, {}, {}

    rows = reader.read_csv(os.path.join(wp, "StorK.csv"))
    if rows is not None:
        stork.parse(rows, base, points)

    sig = reader.read_xlsx(os.path.join(wp, "SIGUR.xlsx"))
    sigur.parse(sig, base, points)

    rep = os.path.join(wp, "report.xls")
    if os.path.exists(rep):
        try:
            hikvision.parse(rep, base, points)
        except Exception as e:
            print("hikvision:", e)

    base = timeutil.base_sort(base)

    lz = reader.read_xlsx(os.path.join(wp, "ЛЭЗ", "lez.xlsx"))
    lez.parse(lz, lezbase, points)

    return base, lezbase, points
