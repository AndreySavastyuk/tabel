# -*- coding: utf-8 -*-
"""Выходные/праздники.

`get_calendar` + `legacy_weekend` — дословный перенос DateWorker.get_calendar и
SCUD.weekend(): нужны для байт-в-байт совместимости со старым выводом (Фаза 0).

`make_weekend_fn(nonworking_dates)` — НОВОЕ: строит weekend_fn по явному
множеству нерабочих дат (выходные + праздники из БД holiday_calendar), заменяя
непрозрачный расчёт DateWorker. Используется веб-конвейером начиная с Фазы 2.
"""
from datetime import date as _date


def get_calendar(mydate):
    """'ММ.ГГГГ' -> сетка месяца (список недель по 7 ячеек, ' ' для пустых).
    Дословный перенос DateWorker.get_calendar."""
    try:
        ves = False
        mydate = mydate.split(".")
        mydate[0] = int(mydate[0])
        mydate[1] = int(mydate[1])
        daydict = {1: 31, 3: 31, 4: 30, 5: 31, 6: 31, 7: 30, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31}
        if mydate[1] % 4 == 0:
            daydict[2] = 29
            ves = True
        else:
            daydict[2] = 28
        days = (mydate[1] - 1) * 365 + (mydate[1] - 1) // 4
        for i in range(1, mydate[0] + 1):
            days = days + daydict[i]
        week = days // 7 * 7
        week = days - week
        week = week + 4
        if not ves and mydate[0] == 2:
            week += 3
        if ves and mydate[0] == 2:
            week += 2
        if mydate[0] > 2 and daydict[mydate[0]] == 30:
            week += 1
        if week > 7:
            week = week - 7
        calendar = []
        tmp = []
        for i in range(1, week):
            tmp.append(" ")
        for i in range(1, daydict[mydate[0]] + 1):
            tmp.append(str(i))
            if len(tmp) == 7:
                calendar.append(tmp)
                tmp = []
        if len(tmp) != 7 and len(tmp) > 0:
            while len(tmp) != 7:
                tmp.append(" ")
            calendar.append(tmp)
        return calendar
    except Exception:
        return None


def legacy_weekend(md):
    """'ДД.ММ.ГГГГ' -> True, если суббота/воскресенье. Дословный перенос
    SCUD.weekend() (колонки 5/6 сетки = сб/вс)."""
    try:
        md = md.split(".")
        tw = get_calendar(f'{md[1]}.{md[2]}')
        for i in tw:
            if int(i[5]) == int(md[0]) or int(i[6]) == int(md[0]):
                return True
        return False
    except Exception:
        return False


def make_weekend_fn(nonworking_dates):
    """Строит weekend_fn(ds 'ДД.ММ.ГГГГ') -> bool по множеству нерабочих дат.

    nonworking_dates — iterable datetime.date (выходные + праздники).
    Заменяет DateWorker: источник нерабочих дней становится явным (БД)."""
    s = set(nonworking_dates or ())

    def fn(ds):
        try:
            d, m, y = str(ds).split(".")
            return _date(int(y), int(m), int(d)) in s
        except Exception:
            return False

    return fn


def make_calendar_weekend_fn(nonworking=None, overrides=None):
    """weekend_fn(ds 'ДД.ММ.ГГГГ') -> bool с производственным календарём.

    Нерабочий день = (суббота/воскресенье ИЛИ праздник/перенесённый выходной)
    И НЕ перенос на рабочий день. Сб/вс вычисляются автоматически, в БД хранятся
    лишь исключения (праздники, перенесённые выходные, рабочие субботы).

      nonworking — iterable datetime.date (праздники + перенесённые выходные)
      overrides  — iterable datetime.date (рабочие дни, выпавшие на сб/вс)"""
    nw = set(nonworking or ())
    ov = set(overrides or ())

    def fn(ds):
        try:
            d, m, y = str(ds).split(".")
            dt = _date(int(y), int(m), int(d))
        except Exception:
            return False
        if dt in ov:
            return False                 # рабочий день (перенос)
        if dt in nw:
            return True                  # праздник / перенесённый выходной
        return dt.weekday() >= 5         # сб/вс

    return fn
