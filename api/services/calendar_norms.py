# -*- coding: utf-8 -*-
"""Помесячная норма часов 5/2 из производственного календаря.

5/2 (8-часовой день, 40-часовая неделя): рабочие дни × 8; предпраздничный
рабочий день короче на 1 час (ст. 95 ТК) — но ТОЛЬКО перед праздничным днём,
НЕ перед перенесённым выходным. Рабочий день = (будни/перенос) и не нерабочий.
"""
from calendar import monthrange
from datetime import date, timedelta

DAY_HOURS_52 = 8.0


def monthly_norms(holidays, dayoffs, overrides, year: int,
                  day_hours_52: float = DAY_HOURS_52) -> list[dict]:
    hol = set(holidays or ())
    nonwork = hol | set(dayoffs or ())      # праздники + перенесённые выходные
    ov = set(overrides or ())
    out = []
    for m in range(1, 13):
        dim = monthrange(year, m)[1]
        work_days = 0
        short_days = 0
        norm52 = 0.0
        for d in range(1, dim + 1):
            dt = date(year, m, d)
            weekend = dt.weekday() >= 5
            working = (dt in ov) or (not weekend and dt not in nonwork)
            if not working:
                continue
            work_days += 1
            h = day_hours_52
            nxt = dt + timedelta(days=1)
            if nxt in hol and nxt not in ov:        # предпраздничный (только перед праздником)
                h -= 1.0
                short_days += 1
            norm52 += h
        out.append({
            "month": f"{year}-{m:02d}",
            "work_days": work_days,
            "short_days": short_days,
            "norm_5x2": round(norm52, 1),
        })
    return out


def monthly_norms_db(db, year: int) -> list[dict]:
    from .refdata_from_db import load_calendar_kinds
    holidays, dayoffs, overrides = load_calendar_kinds(db)
    return monthly_norms(holidays, dayoffs, overrides, year)
