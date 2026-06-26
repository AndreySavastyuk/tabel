# -*- coding: utf-8 -*-
"""Утилиты дат/времени, извлечённые из SCUD(fixed_time)_v0.3.py дословно.

Все три функции — без побочных эффектов и без глобалей.
  date_format  — нормализует строку 'ГГГГ-ММ-ДД ЧЧ:М' -> 'ДД.ММ.ГГГГ ЧЧ:ММ'
  date_former  — 'ДД.ММ.ГГГГ ЧЧ:ММ' -> datetime
  base_sort    — сортирует словарь событий {ФИО: {ключ_даты: событие}} по дате
"""
from datetime import datetime


def date_format(dt):
    dt = dt.split(" ")
    t = dt[1].split(":")
    tmpt = []
    for i in t:
        if len(str(i)) == 1:
            i = "0" + str(i)
        tmpt.append(i)
    t = tmpt
    if "-" in dt[0]:
        dt[0] = f'{dt[0].split("-")[2]}.{dt[0].split("-")[1]}.{dt[0].split("-")[0]}'
    dt = f'{dt[0]} {t[0]}:{t[1]}'
    return dt


def date_former(indate):
    try:
        indatem = str(indate)
        indatem = indate.split(" ")
        indatet = indatem[1].split(":")
        indatem = indatem[0]
        indatem = indatem.split(".")
        return datetime(day=int(indatem[0]), month=int(indatem[1]), year=int(indatem[2]),
                        hour=int(indatet[0]), minute=int(indatet[1]))
    except Exception as e:
        print("date_former", e)
        return indate


def base_sort(base):
    new_base = {}
    for keys, dicts in base.items():            # ФИО: словарь событий
        tmpdict = {}
        k = list(dicts.keys())
        count = 0
        while count != len(k):
            k[count] = f'{k[count].split(".")[2].split(" ")[0]}.{k[count].split(".")[1]}.{k[count].split(".")[0]} {k[count].split(".")[2].split(" ")[1]}'
            count += 1
        k.sort()
        count = 0
        while count != len(k):
            k[count] = f'{k[count].split(".")[2].split(" ")[0]}.{k[count].split(".")[1]}.{k[count].split(".")[0]} {k[count].split(".")[2].split(" ")[1]}'
            count += 1
        for i in k:
            tmpdict[i] = dicts[i]
        new_base[keys] = tmpdict
    return new_base
