# -*- coding: utf-8 -*-
"""Чистые вычисления табеля (SCUD v0.3, Фаза 2).

Все функции — без побочных эффектов и без глобалей, чтобы их можно было
покрыть юнит-тестами. Время передаётся строками 'HH:MM'.
"""
import calendar
from datetime import date, datetime, timedelta

from . import model


def _to_min(hhmm):
    """'HH:MM' -> минуты от полуночи. Бросает ValueError на мусоре."""
    parts = str(hhmm).split(":")
    return int(parts[0]) * 60 + int(parts[1])


def _overlap_minutes(a1, a2, b1, b2):
    """Длина пересечения отрезков [a1,a2] и [b1,b2] в минутах (>=0)."""
    lo = max(a1, b1)
    hi = min(a2, b2)
    return max(0, hi - lo)


def compute_lunch_hours(entry, exit, lunch_window):
    """Часы обеда к вычету = длительность пересечения окна обеда [L1,L2]
    с рабочим интервалом [вход, выход]. Пришёл после окна / ушёл до — 0.

    entry/exit:   'HH:MM' (или None)
    lunch_window: (L1, L2) строки 'HH:MM' (или None)
    """
    if not entry or not exit or not lunch_window:
        return 0.0
    try:
        e1, e2 = _to_min(entry), _to_min(exit)
        l1, l2 = _to_min(lunch_window[0]), _to_min(lunch_window[1])
    except (ValueError, IndexError, TypeError):
        return 0.0
    mins = _overlap_minutes(e1, e2, l1, l2)
    if e2 < e1:                      # смена через полночь
        e2 += 24 * 60
        # обеденное окно может попадать на «вторую» половину суток —
        # проверяем сдвинутое на сутки положение окна и берём максимум.
        mins = max(
            _overlap_minutes(e1, e2, l1, l2),
            _overlap_minutes(e1, e2, l1 + 24 * 60, l2 + 24 * 60),
        )
    return round(mins / 60.0, 2)


def compute_lateness_min(entry, shift_start, grace=0):
    """Минуты опоздания относительно начала смены (с учётом грейса). <=0 -> 0."""
    if not entry or not shift_start:
        return 0
    try:
        late = _to_min(entry) - _to_min(shift_start) - int(grace)
    except (ValueError, IndexError, TypeError):
        return 0
    return late if late > 0 else 0


def compute_overtime_hours(worked_hours, shift_len):
    """Часы переработки = отработано сверх длительности смены. <=0 -> 0."""
    if not shift_len or worked_hours is None:
        return 0.0
    try:
        ot = float(worked_hours) - float(shift_len)
    except (ValueError, TypeError):
        return 0.0
    return round(ot, 2) if ot > 0 else 0.0


def parse_ddmmyyyy(s):
    """'DD.MM.YYYY' -> datetime.date или None."""
    try:
        return datetime.strptime(str(s).strip(), "%d.%m.%Y").date()
    except (ValueError, TypeError):
        return None


def month_key_of(d):
    """datetime.date -> 'YYYY-MM'."""
    return f"{d.year:04d}-{d.month:02d}"


def gap_minutes(t_out, t_in):
    """Разрыв между выходом t_out и входом t_in в минутах (через полночь — +сутки)."""
    try:
        a, b = _to_min(t_out), _to_min(t_in)
    except (ValueError, IndexError, TypeError):
        return 0
    if b < a:
        b += 24 * 60
    return b - a


def _abs_gap(a, b):
    """|a - b| в минутах или None, если что-то не парсится."""
    try:
        return abs(_to_min(a) - _to_min(b))
    except (ValueError, IndexError, TypeError):
        return None


def lez_reentry_gaps(lez_events, threshold_min):
    """[(t_out, t_in, минут)] для разрывов выход->следующий вход на ЛЭЗ > порога.

    Только отметки ЛЭЗ (детекция «вышел с территории завода и вернулся»)."""
    out = []
    last_out = None
    for t, e in (lez_events or []):
        el = str(e).lower()
        if el.startswith("выход"):
            last_out = t
        elif el.startswith("вход"):
            if last_out is not None:
                g = gap_minutes(last_out, t)
                if g > threshold_min:
                    out.append((last_out, t, g))
                last_out = None
    return out


def date_span_of(day_records):
    """(date_min, date_max) по всем датам записей или None."""
    dates = []
    for recs in day_records.values():
        for dr in recs:
            d = parse_ddmmyyyy(dr.date)
            if d:
                dates.append(d)
    if not dates:
        return None
    return min(dates), max(dates)


def inject_absence_records(day_records, ref, day_span, weekend_fn=None):
    """Добавляет записи-отсутствия за дни периода, где у сотрудника нет
    отметок, но есть уважительная причина (ref.absences). Так отпускники/
    больничные/командировочные попадают в свод (норму) и не выглядят как
    прогул. Выходные пропускаем. Возвращает число добавленных записей."""
    if not ref or not day_span or not ref.absences:
        return 0
    d0, d1 = day_span
    added = 0
    for name, spans in ref.absences.items():
        existing = {r.date for r in day_records.get(name, [])}
        sched = ref.schedule(name)
        dn = ref.shift_len.get(sched, 0.0) if sched else 0.0
        for typ, a, b in spans:
            cur = max(a, d0)
            end = min(b, d1)
            while cur <= end:
                ds = cur.strftime("%d.%m.%Y")
                is_we = bool(weekend_fn(ds)) if weekend_fn else False
                if ds not in existing and not is_we:
                    dr = model.DayRecord(name=name, date=ds)
                    dr.is_weekend = is_we
                    dr.absence = typ
                    dr.dept = ref.dept(name)
                    dr.cabinet = ref.cabinet(name)
                    dr.schedule = sched
                    dr.day_norm = dn
                    dr.lez_controlled = ref.is_lez_controlled(name)
                    day_records.setdefault(name, []).append(dr)
                    existing.add(ds)
                    added += 1
                cur += timedelta(days=1)
    return added


def count_working_days(day_span, weekend_fn=None):
    """Число будних дней (не сб/вс) в диапазоне [d0, d1]."""
    if not day_span:
        return 0
    d0, d1 = day_span
    n = 0
    cur = d0
    while cur <= d1:
        ds = cur.strftime("%d.%m.%Y")
        if not (weekend_fn and weekend_fn(ds)):
            n += 1
        cur += timedelta(days=1)
    return n


def period_norm_factors(d0, d1, weekend_fn=None):
    """{'YYYY-MM': доля рабочих дней периода [d0, d1] в этом месяце}.

    factor = рабочих_дней(период ∩ месяц) / рабочих_дней(весь месяц). Месяц,
    покрытый периодом ЦЕЛИКОМ, даёт factor == 1.0 — норма не масштабируется
    (инвариант: полный месяц ⇒ результат идентичен прежнему). Для неполного
    месяца норма умножается на долю рабочих дней (решение: пропорция по дням)."""
    factors = {}
    if not d0 or not d1:
        return factors
    y, mo = d0.year, d0.month
    while (y, mo) <= (d1.year, d1.month):
        ndays = calendar.monthrange(y, mo)[1]
        full = inside = 0
        for dd in range(1, ndays + 1):
            cur = date(y, mo, dd)
            if weekend_fn and weekend_fn(cur.strftime("%d.%m.%Y")):
                continue
            full += 1
            if d0 <= cur <= d1:
                inside += 1
        factors[month_key_of(date(y, mo, 1))] = (inside / full) if full else 1.0
        y, mo = (y + 1, 1) if mo == 12 else (y, mo + 1)
    return factors


def period_months_of(day_records):
    """Множество месяцев 'YYYY-MM', встречающихся в записях."""
    months = set()
    for recs in day_records.values():
        for dr in recs:
            d = parse_ddmmyyyy(dr.date)
            if d:
                months.add(month_key_of(d))
    return sorted(months)


def bucket_of(percent):
    """Доля отработанного -> группа для листа бухгалтерии."""
    if percent < 25:
        return "<25%"
    if percent < 50:
        return "25-50%"
    if percent < 75:
        return "50-75%"
    return ">75%"


def build_employee_periods(day_records, ref=None, months=None, thresholds=None,
                           working_days=None, norm_factors=None):
    """Свёртка по сотруднику за период -> {ФИО: EmployeePeriod}.

    Решение заказчика: отсутствия (отпуск/больничный/командировка)
    ЗАСЧИТЫВАЮТСЯ как отработанное — зачёт = кол-во дней × дневная норма
    (длительность смены графика). Тогда «% отработано» отпускника ≈ 100%,
    а метка <50% означает реальный недоработ без уважительной причины."""
    months = months if months is not None else period_months_of(day_records)
    periods = {}
    for name, recs in day_records.items():
        ep = model.EmployeePeriod(name=name)
        ep.schedule = ref.schedule(name) if ref else None
        ep.dept = ref.dept(name) if ref else "Без отдела"
        worked = 0.0
        day_norm = 0.0
        absset = {}
        late = 0
        late_min = 0
        ot = 0.0
        cap = (thresholds or model.THRESHOLDS)["implausible_hours_max"]
        for dr in recs:
            worked_day = (
                dr.entry and dr.exit and isinstance(dr.worked_hours, (int, float))
                and dr.worked_hours > 0
            )
            if worked_day:
                # неправдоподобные дни (выход раньше входа -> отрицательные часы,
                # либо абсурдно большие) не тащим в сумму: они и так помечены
                # в «Отклонениях». Берём только положительные, с верхним капом.
                worked += min(dr.worked_hours, cap)
            if dr.day_norm:
                day_norm = dr.day_norm
            # день засчитываем как отсутствие ТОЛЬКО если в этот день реально не
            # работал (иначе двойной счёт: и часы, и зачёт нормы).
            if dr.absence and not worked_day:
                absset[dr.absence] = absset.get(dr.absence, 0) + 1
            if dr.lateness_min > 0:
                late += 1
                late_min += dr.lateness_min
            ot += dr.overtime_h or 0.0
        ep.worked_total = round(worked, 2)
        ep.absence_days = absset
        ep.late_count = late
        ep.late_minutes = late_min
        ep.overtime_total = round(ot, 2)

        pn = 0.0
        if ep.schedule and ref:
            for m in months:
                v = ref.norms.get((ep.schedule, m), 0.0)
                if norm_factors is not None:
                    # неполный месяц: норма пропорциональна доле рабочих дней.
                    v *= norm_factors.get(m, 1.0)
                pn += v
        ep.period_norm = round(pn, 2)

        # Зачёт отсутствий. Предпочтительно — через дневную норму, выведенную
        # из нормы периода и числа будних дней (тогда полное отсутствие за
        # период даёт ровно 100% и не зависит от рассогласования длит. смены).
        # Если working_days неизвестно — откатываемся на длительность смены.
        total_abs_days = sum(absset.values())
        if working_days and ep.period_norm > 0:
            daily = ep.period_norm / working_days
        else:
            daily = day_norm or 0.0
        credit = round(total_abs_days * daily, 2)
        ep.credited_total = round(worked + credit, 2)
        if ep.period_norm > 0:
            ep.percent = round(ep.credited_total / ep.period_norm * 100.0, 1)
            ep.bucket = bucket_of(ep.percent)
        else:
            ep.percent = 0.0
            ep.bucket = "—"          # нет нормы (график не задан)
        periods[name] = ep
    return periods


def evaluate_deviations(dr, thresholds=None):
    """Заполняет dr.deviations кодами отклонений. Возвращает список кодов.

    Использует РАЗДЕЛЬНЫЕ отметки систем (int_* / lez_*), а не итоговые.
    Дни с уважительным отсутствием (dr.absence) не помечаются как «нет
    отметки» / «только одна система»."""
    th = thresholds or model.THRESHOLDS
    dev = []
    excused = dr.absence is not None

    int_present = bool(dr.int_entry and dr.int_exit)
    lez_present = bool(dr.lez_entry and dr.lez_exit)
    has_int = bool(dr.int_entry or dr.int_exit)
    has_lez = bool(dr.lez_entry or dr.lez_exit)

    # 1) пропуски входа/выхода (по итоговым отметкам табеля)
    if not excused and (has_int or has_lez):
        if dr.entry is None:
            dev.append(model.DEV_MISSING_ENTRY)
        if dr.exit is None:
            dev.append(model.DEV_MISSING_EXIT)

    # 2) кросс-проверка двух систем — только для сотрудников, которые реально
    #    отслеживаются ОБЕИМИ системами (dual_tracked) или явно помечены
    #    «Контроль ЛЭЗ». Иначе цеховых рабочих (только ЛЭЗ) и офисных (только
    #    внутренняя) залило бы ложными срабатываниями.
    cross = dr.dual_tracked or dr.lez_controlled
    if int_present and not lez_present:
        # отметка во внутренней есть, в ЛЭЗ нет — кандидат на «за отсутствующего».
        if cross and not excused:
            dev.append(model.DEV_ONLY_INTERNAL)
    elif lez_present and not int_present:
        if dr.dual_tracked and not excused:
            dev.append(model.DEV_ONLY_LEZ)
    elif int_present and lez_present:
        de = _abs_gap(dr.int_entry, dr.lez_entry)
        dx = _abs_gap(dr.int_exit, dr.lez_exit)
        lim = th["time_mismatch_min"]
        if (de is not None and de > lim) or (dx is not None and dx > lim):
            dev.append(model.DEV_TIME_MISMATCH)

    # 3) нулевые/неправдоподобные часы
    if dr.entry and dr.exit and dr.worked_hours is not None:
        w = dr.worked_hours
        if w <= th["implausible_hours_min"] or w > th["implausible_hours_max"]:
            dev.append(model.DEV_IMPLAUSIBLE)

    # 4) повторный вход на территорию (ЛЭЗ) > порога — с фактической длительностью
    for t_out, t_in, mins in lez_reentry_gaps(dr.lez_events, th["reentry_gap_min"]):
        dev.append(f"Выход с территории {mins} мин ({t_out}→{t_in})")

    dr.deviations = dev
    return dev
