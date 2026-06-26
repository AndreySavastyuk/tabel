# -*- coding: utf-8 -*-
"""Парсер SIGUR.xlsx (внутренняя СКУД). Перенос ceh() без глобалей.

Данные ожидаются на листе с ключом 99 (как в выгрузке SIGUR). Если листа нет
или файл не прочитался — источник просто пропускается (как в легаси)."""
from ..names import name_format
from ..timeutil import date_format
from .reader import sheet_rows


def parse(xl_data, base, points):
    """Наполняет base[ФИО][ключ] = направление и points[...] = 'NC_SIGUR'."""
    rows = sheet_rows(xl_data)
    if not rows:
        return base
    A = C = E = G = None
    for row in rows:
        if row.get("G") and row.get("G") != "направление":
            A = row.get("A", A)
            C = name_format(row.get("C", C))
            E = row.get("E", E)
            G = row.get("G", G)
            if base.get(C) is None:
                base[C] = {}
            base[C][date_format(f'{A} {E}')] = G
            d = date_format(f'{A} {E}')
            points[f'{C} {d}'] = "NC_SIGUR"
    return base
