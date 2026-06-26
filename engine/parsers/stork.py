# -*- coding: utf-8 -*-
"""Парсер StorK.csv (внутренняя СКУД). Перенос office() без глобалей."""
from ..names import name_format
from ..timeutil import date_format


def parse(rows, base, points):
    """Наполняет base[ФИО][ключ] = 'Вход'/'Выход' и points[...] = 'StorK'."""
    for row in (rows or []):
        if len(row) >= 9 and (row[5] != "" or row[7] != "" or row[4] != ""):
            if row[4] != "Дата" and row[5] != "Время":
                if base.get(name_format(row[0])) is None:
                    base[name_format(row[0])] = {}
                if len(row) == 12:
                    if row[5] != "":
                        base[name_format(row[0])][date_format(f'{row[4]} {row[5]}')] = row[7]
                        d = date_format(f'{row[4]} {row[5]}')
                        n = name_format(row[0])
                        points[f'{n} {d}'] = "StorK"
                    if row[8] != "":
                        base[name_format(row[0])][date_format(f'{row[4]} {row[8]}')] = row[11]
                        d = date_format(f'{row[4]} {row[8]}')
                        n = name_format(row[0])
                        points[f'{n} {d}'] = "StorK"
                elif len(row) == 10:
                    if row[4] != "":
                        base[name_format(row[0])][date_format(f'{row[3]} {row[4]}')] = row[6]
                        d = date_format(f'{row[3]} {row[4]}')
                        n = name_format(row[0])
                        points[f'{n} {d}'] = "StorK"
                    if row[7] != "":
                        base[name_format(row[0])][date_format(f'{row[3]} {row[7]}')] = row[9]
                        d = date_format(f'{row[3]} {row[7]}')
                        n = name_format(row[0])
                        points[f'{n} {d}'] = "StorK"
                else:
                    print("stork: неожиданная длина строки StorK", len(row), row)
    return base
