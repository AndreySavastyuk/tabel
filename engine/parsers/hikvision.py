# -*- coding: utf-8 -*-
"""Парсер report.xls (Hikvision, HTML-подобный xls). Перенос hikvision()."""
from ..names import name_format
from ..timeutil import date_format
from . import reader


def parse(path, base, points):
    """Наполняет base[ФИО][ключ] = 'Вход'/'Выход' и points[...] = контроллер."""
    for row in reader.read_old_xls(path):
        A = row.get("D").split(" ")[0]
        C = name_format(row.get("B"))
        E = row.get("D").split(" ")[1]
        G = row.get("E").replace("Приход", "Вход").replace("Уход", "Выход").replace("Нет", "Вход")
        if base.get(C) is None:
            base[C] = {}
        base[C][date_format(f'{A} {E}')] = G
        d = date_format(f'{A} {E}')
        points[f'{C} {d}'] = row.get("F")
    return base
