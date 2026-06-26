# -*- coding: utf-8 -*-
"""Парсер ЛЭЗ/lez.xlsx (проходная завода). Перенос lez() без глобалей.

Данные на листе с ключом 99. Блок сотрудника начинается со строки
'Номер ключа:' и заканчивается 'Всего времени:'."""
from ..names import name_format
from ..timeutil import date_format
from .reader import sheet_rows


def parse(xl_data, lezbase, points):
    """Наполняет lezbase[ФИО][ключ] = 'Вход'/'Выход' и points[...] = 'LEZ'."""
    rows = sheet_rows(xl_data)
    if not rows:
        return lezbase
    name = None
    for row in rows:
        if row.get("G") == "Номер ключа:":
            name = name_format(row.get("A"))
        if row.get("I") == "Всего времени:":
            name = None
        if name and row.get("A") != "Устройство входа":
            if lezbase.get(name) is None:
                lezbase[name] = {}
            if row.get("E") and row.get("F"):
                lezbase[name][date_format(f'{row.get("E")} {row.get("F")}')] = "Вход"
                d = date_format(f'{row.get("E")} {row.get("F")}')
                points[f'{name} {d}'] = "LEZ"
            if row.get("J") and row.get("K"):
                lezbase[name][date_format(f'{row.get("J")} {row.get("K")}')] = "Выход"
                d = date_format(f'{row.get("J")} {row.get("K")}')
                points[f'{name} {d}'] = "LEZ"
    return lezbase
