# -*- coding: utf-8 -*-
"""Разбиение событий на смены и построение DayRecord (SCUD v0.3).

Извлечено из SCUD(fixed_time)_v0.3.py дословно, с одним изменением: глобальные
зависимости (`model.THRESHOLDS`, `weekend()`) переданы параметрами `thresholds`
и `weekend_fn`, поэтому модуль чист и не зависит от tkinter/глобалей.

build_day_records строит model.DayRecord ИЗ СЫРЫХ событий обеих систем
(внутренние СКУД vs ЛЭЗ) РАЗДЕЛЬНО, с разбиением на смены по datetime — поэтому
ночные смены (вход вечером, выход следующим утром) считаются корректно.
"""
from datetime import datetime

from . import compute, model
from .timeutil import date_former


def apply_fixed_start_time(start_time, name, fixed_employees):
    """Если сотрудник в списке и пришёл раньше фикс. времени — подменяет start_time.

    start_time:      строка "DD.MM.YYYY HH:MM" либо False / " -"
    name:            ФИО, уже прошедшее name_format()
    fixed_employees: словарь {ФИО: "ЧЧ:ММ"}

    Возвращает кортеж (новый_start_time, был_ли_изменён)."""
    if not start_time or start_time is False or start_time == " -":
        return start_time, False
    if not fixed_employees or name not in fixed_employees:
        return start_time, False
    try:
        parts = start_time.split(" ")
        if len(parts) < 2:
            return start_time, False
        date_part, time_part = parts[0], parts[1]
        fix_hh, fix_mm = fixed_employees[name].split(":")
        fix_hh, fix_mm = int(fix_hh), int(fix_mm)
        act_hh, act_mm = time_part.split(":")[0], time_part.split(":")[1]
        act_hh, act_mm = int(act_hh), int(act_mm)
        # Строгое неравенство: при равенстве — оставляем фактическое (не помечаем).
        if (act_hh, act_mm) < (fix_hh, fix_mm):
            return f'{date_part} {fix_hh:02d}:{fix_mm:02d}', True
        return start_time, False
    except Exception as e:
        print(f'apply_fixed_start_time: ошибка для {name} ({start_time}): {e}')
        return start_time, False


def _events_dt(per_system_base, name):
    """[(datetime, событие)] сотрудника по одной системе, отсортировано."""
    out = []
    d = (per_system_base or {}).get(name) or {}
    for key, ev in d.items():
        dt = date_former(key)
        if isinstance(dt, datetime):
            out.append((dt, str(ev)))
    out.sort(key=lambda x: x[0])
    return out


def _detect_shifts(events, gap_min, max_shift_min):
    """[(datetime, событие)] -> [(вход_dt, выход_dt|None)].

    Смена = непрерывное присутствие. Перерыв больше gap_min начинает новую
    смену (так ночные смены вечер->утро разделяются, а обед/короткая отлучка
    внутри смены — сливаются в один интервал, как первый-вход/последний-выход).
    Интервал длиннее max_shift_min обрезается (вероятно забыли отметить выход)."""
    # 1) элементарные пары вход->ближайший выход по времени
    pairs = []
    cur_in = None
    for dt, kind in events:
        k = str(kind).lower()
        if k.startswith("вход"):
            if cur_in is None:
                cur_in = dt
        elif k.startswith("выход"):
            if cur_in is not None:
                pairs.append([cur_in, dt])
                cur_in = None
    if cur_in is not None:
        pairs.append([cur_in, None])
    if not pairs:
        return []
    # 2) слияние соседних пар с маленьким разрывом (обед/отлучка внутри смены)
    merged = [pairs[0]]
    for p in pairs[1:]:
        last = merged[-1]
        if (last[1] is not None and p[0] is not None
                and (p[0] - last[1]).total_seconds() / 60.0 < gap_min):
            last[1] = p[1]
        else:
            merged.append(p)
    # 3) кап на длительность смены
    result = []
    for i, o in merged:
        if i and o and (o - i).total_seconds() / 60.0 > max_shift_min:
            o = None
        result.append((i, o))
    return result


def build_day_records(rebuild, internal_base, lez_base, ref=None,
                      fixed_employees=None, apply_fixed=True,
                      thresholds=None, weekend_fn=None):
    """{ФИО: [DayRecord]} из сырых событий с разбиением на смены по datetime.

    thresholds — словарь порогов (по умолчанию model.THRESHOLDS).
    weekend_fn — fn('DD.MM.YYYY') -> bool (по умолчанию «никогда не выходной»)."""
    th = thresholds if thresholds is not None else model.THRESHOLDS
    we = weekend_fn if weekend_fn is not None else (lambda ds: False)
    gap_min = th.get("shift_gap_min", 300)
    max_min = th.get("max_shift_min", 960)
    grace = th["lateness_grace_min"]
    names = set(rebuild or {})            # тот же набор сотрудников, что в легаси
    records = {}
    for name in names:
        int_shifts = _detect_shifts(_events_dt(internal_base, name), gap_min, max_min)
        lez_events = _events_dt(lez_base, name)
        lez_shifts = _detect_shifts(lez_events, gap_min, max_min)
        # смены, индексированные по дате ВХОДА (первая смена дня)
        int_by_date, lez_by_date = {}, {}
        for i, o in int_shifts:
            int_by_date.setdefault(i.strftime("%d.%m.%Y"), (i, o))
        for i, o in lez_shifts:
            lez_by_date.setdefault(i.strftime("%d.%m.%Y"), (i, o))
        recs = []
        for ds in sorted(set(int_by_date) | set(lez_by_date),
                         key=lambda d: tuple(reversed(d.split(".")))):
            dr = model.DayRecord(name=name, date=ds)
            dr.is_weekend = we(ds)
            isin = int_by_date.get(ds)
            lzin = lez_by_date.get(ds)
            if isin:
                dr.int_entry = isin[0].strftime("%H:%M")
                dr.int_exit = isin[1].strftime("%H:%M") if isin[1] else None
            if lzin:
                dr.lez_entry = lzin[0].strftime("%H:%M")
                dr.lez_exit = lzin[1].strftime("%H:%M") if lzin[1] else None
            # Сырые отметки ЛЭЗ ВНУТРИ смены (для детекции отлучек > 30 мин).
            # Ограничиваем окном смены, иначе у ночных смен «утренний выход
            # одной смены + вечерний вход следующей» давал ложную отлучку.
            if lzin:
                w0, w1 = lzin[0], (lzin[1] or lzin[0])
                dr.lez_events = [(dt.strftime("%H:%M"), kind)
                                 for dt, kind in lez_events if w0 <= dt <= w1]

            # выбранные вход/выход: внутренняя система приоритетна, ЛЭЗ — резерв
            cin = isin[0] if isin else (lzin[0] if lzin else None)
            cin_src = "internal" if isin else ("LEZ" if lzin else None)
            if isin and isin[1] is not None:
                cout, cout_src = isin[1], "internal"
            elif lzin and lzin[1] is not None:
                cout, cout_src = lzin[1], "LEZ"
            else:
                cout, cout_src = None, None

            # фиксированное время прихода (как в find_emp): если пришёл раньше
            if apply_fixed and fixed_employees and cin is not None:
                s = cin.strftime("%d.%m.%Y %H:%M")
                news, changed = apply_fixed_start_time(s, name, fixed_employees)
                if changed:
                    dr.start_fixed = True
                    dr.original_start = cin.strftime("%H:%M")
                    cin = date_former(news)

            dr.entry = cin.strftime("%H:%M") if cin else None
            dr.exit = cout.strftime("%H:%M") if cout else None
            dr.entry_source = cin_src if cin else None
            dr.exit_source = cout_src if cout else None
            if cin and cout:
                dr.raw_hours = round((cout - cin).total_seconds() / 3600.0, 2)
                dr.worked_hours = dr.raw_hours

            # --- справочные вычисления ---
            if ref is not None:
                sched = ref.schedule(name)
                dr.dept = ref.dept(name)
                dr.cabinet = ref.cabinet(name)
                dr.schedule = sched
                dr.lez_controlled = ref.is_lez_controlled(name)
                window = ref.lunch.get(sched) if sched else None
                if dr.entry and dr.exit and window:
                    dr.lunch_deducted = compute.compute_lunch_hours(dr.entry, dr.exit, window)
                    dr.worked_hours = round(dr.raw_hours - dr.lunch_deducted, 2)
                shift_start = ref.shift_start.get(sched) if sched else None
                dr.lateness_min = compute.compute_lateness_min(dr.entry, shift_start, grace)
                shift_len = ref.shift_len.get(sched) if sched else None
                dr.day_norm = float(shift_len) if shift_len else 0.0
                dr.overtime_h = compute.compute_overtime_hours(dr.worked_hours, shift_len)
                dd = compute.parse_ddmmyyyy(ds)
                if dd is not None:
                    dr.absence = ref.absence_on(name, dd)
            recs.append(dr)

        # dual-tracking + отклонения
        has_int = any(r.int_entry or r.int_exit for r in recs)
        has_lez = any(r.lez_entry or r.lez_exit for r in recs)
        dual = has_int and has_lez
        for r in recs:
            r.dual_tracked = dual
            compute.evaluate_deviations(r, th)
        records[name] = recs
    return records
