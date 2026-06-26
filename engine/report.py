# -*- coding: utf-8 -*-
"""Писатели аналитических листов (SCUD v0.3).

Все функции принимают открытый pandas.ExcelWriter (engine='xlsxwriter') и
данные (DayRecord / EmployeePeriod), создают отдельный лист и пишут ячейки
через xlsxwriter. Форматы создаются из workbook здесь же.
"""
from . import model


def report_formats(workbook):
    base = {
        "text_wrap": True, "align": "center", "valign": "vcenter",
        "border": 1, "border_color": "#B0B0B0", "font_color": "#000000",
    }

    def fmt(**ov):
        s = dict(base)
        s.update(ov)
        return workbook.add_format(s)

    return {
        "header": fmt(bold=True, fg_color="#D9E1F2"),
        "white": fmt(fg_color="#FFFFFF"),
        "left": fmt(fg_color="#FFFFFF", align="left"),
        "blue": fmt(fg_color="#DDEBF7"),
        "yellow": fmt(fg_color="#FFEB9C"),
        "good": fmt(fg_color="#C6EFCE"),
        "warn": fmt(fg_color="#FFEB9C"),
        "bad": fmt(bold=True, fg_color="#FFC7CE", align="left"),
        "bad_c": fmt(bold=True, fg_color="#FFC7CE"),
        "pct": fmt(fg_color="#FFFFFF", num_format="0%"),
        "num": fmt(fg_color="#FFFFFF", num_format="0.00"),
    }


def _date_key(d):
    try:
        p = str(d).split(".")
        return (p[2], p[1], p[0])
    except Exception:
        return (str(d),)


def _new_sheet(writer, name):
    ws = writer.book.add_worksheet(name)
    writer.sheets[name] = ws
    return ws


def write_deviations_sheet(writer, day_records, fmts, weekend_fn=None):
    """Лист «Отклонения»: только записи, требующие ручной проверки.

    Возвращает количество строк-отклонений."""
    ws = _new_sheet(writer, "Отклонения")
    headers = ["ФИО", "Дата", "Внутр. вход", "Внутр. выход",
               "ЛЭЗ вход", "ЛЭЗ выход", "Часы", "Отклонения"]
    widths = [32, 12, 11, 12, 9, 10, 7, 46]
    for c, (h, w) in enumerate(zip(headers, widths)):
        ws.set_column(c, c, w)
        ws.write(0, c, h, fmts["header"])

    items = []
    for name, recs in day_records.items():
        for dr in recs:
            if dr.deviations:
                items.append(dr)
    items.sort(key=lambda d: (d.name, _date_key(d.date)))

    row = 1
    for dr in items:
        labels = "; ".join(model.DEV_LABELS.get(c, c) for c in dr.deviations)
        ws.write(row, 0, dr.name, fmts["left"])
        ws.write(row, 1, dr.date,
                 fmts["blue"] if (weekend_fn and weekend_fn(dr.date)) else fmts["white"])
        ws.write(row, 2, dr.int_entry or "-", fmts["white"])
        ws.write(row, 3, dr.int_exit or "-", fmts["white"])
        ws.write(row, 4, dr.lez_entry or "-", fmts["white"])
        ws.write(row, 5, dr.lez_exit or "-", fmts["white"])
        ws.write(row, 6, (dr.worked_hours if (dr.entry and dr.exit) else "-"), fmts["white"])
        ws.write(row, 7, labels, fmts["bad"])
        row += 1

    if not items:
        ws.write(1, 0, "Отклонений не найдено", fmts["good"])
    ws.freeze_panes(1, 0)
    ws.autofilter(0, 0, max(row - 1, 1), len(headers) - 1)
    return len(items)


def _bad_chars(name):
    out = str(name)
    for ch in "[]:*?/\\":
        out = out.replace(ch, "-")
    return out.strip() or "лист"


def _safe_sheet_name(name, used):
    base = _bad_chars(name)[:31]
    cand = base
    i = 1
    while cand in used or not cand:
        suf = f"_{i}"
        cand = base[:31 - len(suf)] + suf
        i += 1
    used.add(cand)
    return cand


def write_department_sheets(writer, day_records, fmts, weekend_fn=None, used_names=None):
    """По одному листу на (отдел, кабинет). Большие отделы (производство и т.п.)
    дробятся по кабинетам — отдельный лист на каждый кабинет; отделы без
    кабинетов остаются одним листом. Часы считаются с вычетом обеда. Возвращает
    список имён созданных листов."""
    used = used_names if used_names is not None else set()
    groups = {}
    for name, recs in day_records.items():
        dept = (recs[0].dept if recs else None) or "Без отдела"
        cab = (recs[0].cabinet if recs else None) or None
        groups.setdefault((dept, cab), []).append((name, recs))

    # Если ничего не задано (все «Без отдела» без кабинета) — листы не плодим:
    # это дублировало бы «Фиксированное время».
    if len(groups) <= 1 and ("Без отдела", None) in groups:
        return []

    created = []
    for (dept, cab) in sorted(groups, key=lambda k: (k[0], k[1] or "")):
        title = f"{dept} - {cab}" if cab else f"Отдел {dept}"
        sheet = _safe_sheet_name(title, used)
        ws = _new_sheet(writer, sheet)
        for c, w in enumerate([32, 12, 7, 7, 6, 7]):
            ws.set_column(c, c, w)
        row = 0
        for name, recs in sorted(groups[(dept, cab)], key=lambda x: x[0]):
            for c, h in enumerate(["ФИО", "Дата", "Вход", "Выход", "Обед", "Часы"]):
                ws.write(row, c, h, fmts["header"])
            row += 1
            start = row
            for dr in recs:
                ws.write(row, 0, name, fmts["left"])
                ws.write(row, 1, dr.date,
                         fmts["blue"] if (weekend_fn and weekend_fn(dr.date)) else fmts["white"])
                # вход
                if dr.entry is None:
                    ws.write(row, 2, "-", fmts["bad_c"])
                elif dr.start_fixed:
                    ws.write(row, 2, dr.entry, fmts["good"])
                elif dr.entry_source == "LEZ":
                    ws.write(row, 2, dr.entry, fmts["yellow"])
                else:
                    ws.write(row, 2, dr.entry, fmts["white"])
                # выход
                if dr.exit is None:
                    ws.write(row, 3, "-", fmts["bad_c"])
                elif dr.exit_source == "LEZ":
                    ws.write(row, 3, dr.exit, fmts["yellow"])
                else:
                    ws.write(row, 3, dr.exit, fmts["white"])
                # обед + часы
                ws.write(row, 4, dr.lunch_deducted or 0, fmts["num"])
                if dr.entry and dr.exit:
                    # +IF(выход<вход;24;0) — корректно для ночных смен через полночь
                    rr = row + 1
                    ws.write(row, 5,
                             f"=ROUND((D{rr}-C{rr})*24,2)+IF(D{rr}<C{rr},24,0)-E{rr}",
                             fmts["num"])
                else:
                    ws.write(row, 5, "-", fmts["bad_c"])
                row += 1
            ws.write(row, 0, name, fmts["white"])
            ws.write(row, 1, " ", fmts["white"])
            ws.write(row, 2, " ", fmts["white"])
            ws.write(row, 3, " ", fmts["white"])
            ws.write(row, 4, "Итого:", fmts["header"])
            ws.write(row, 5, f"=SUM(F{start+1}:F{row})", fmts["header"])
            row += 2
        created.append(sheet)
    return created


def write_accounting_sheet(writer, periods, fmts):
    """Лист «Бухгалтерия (аванс)»: все сотрудники по доле отработанного,
    <50% выделены красным. Сортировка по % по возрастанию (нормированные
    сначала, без нормы — в конце)."""
    ws = _new_sheet(writer, "Бухгалтерия (аванс)")
    headers = ["ФИО", "Отдел", "Отработано, ч", "Зачёт отсут., ч",
               "Норма, ч", "% отработано", "Группа"]
    widths = [32, 18, 13, 14, 11, 13, 10]
    for c, (h, w) in enumerate(zip(headers, widths)):
        ws.set_column(c, c, w)
        ws.write(0, c, h, fmts["header"])

    items = list(periods.values())
    # нормированные по % asc, затем без нормы
    items.sort(key=lambda e: (0 if e.period_norm > 0 else 1,
                              e.percent if e.period_norm > 0 else 0, e.name))
    row = 1
    for ep in items:
        has_norm = ep.period_norm > 0
        low = has_norm and ep.percent < 50
        base = fmts["bad"] if low else fmts["left"]
        ws.write(row, 0, ep.name, base)
        ws.write(row, 1, ep.dept or "Без отдела", fmts["bad"] if low else fmts["white"])
        ws.write(row, 2, ep.worked_total, fmts["num"])
        ws.write(row, 3, round(ep.credited_total - ep.worked_total, 2), fmts["num"])
        ws.write(row, 4, ep.period_norm if has_norm else "—", fmts["white"])
        if has_norm:
            ws.write(row, 5, ep.percent / 100.0, fmts["bad_c"] if low else fmts["pct"])
        else:
            ws.write(row, 5, "нет нормы", fmts["warn"])
        ws.write(row, 6, ep.bucket, fmts["bad_c"] if low else fmts["white"])
        row += 1
    ws.freeze_panes(1, 0)
    ws.autofilter(0, 0, max(row - 1, 1), len(headers) - 1)
    return len(items)


def write_norms_sheet(writer, periods, fmts):
    """Лист «Нормы»: отработано+зачёт vs норма за период, +/- формулой."""
    ws = _new_sheet(writer, "Нормы")
    headers = ["ФИО", "Отдел", "График", "Отработано, ч", "Зачёт отсут., ч",
               "Зачтено, ч", "Норма, ч", "+/- к норме"]
    widths = [32, 18, 12, 13, 14, 11, 11, 12]
    for c, (h, w) in enumerate(zip(headers, widths)):
        ws.set_column(c, c, w)
        ws.write(0, c, h, fmts["header"])
    items = sorted(periods.values(), key=lambda e: (e.dept or "", e.name))
    row = 1
    for ep in items:
        r = row + 1
        ws.write(row, 0, ep.name, fmts["left"])
        ws.write(row, 1, ep.dept or "Без отдела", fmts["left"])
        ws.write(row, 2, ep.schedule or "—", fmts["white"])
        ws.write(row, 3, ep.worked_total, fmts["num"])
        ws.write(row, 4, round(ep.credited_total - ep.worked_total, 2), fmts["num"])
        ws.write(row, 5, f"=D{r}+E{r}", fmts["num"])           # зачтено
        if ep.period_norm > 0:
            ws.write(row, 6, ep.period_norm, fmts["white"])
            ws.write(row, 7, f"=F{r}-G{r}", fmts["num"])       # +/-
        else:
            ws.write(row, 6, "—", fmts["warn"])
            ws.write(row, 7, "—", fmts["warn"])
        row += 1
    ws.freeze_panes(1, 0)
    ws.autofilter(0, 0, max(row - 1, 1), len(headers) - 1)
    return len(items)


def write_late_overtime_sheet(writer, periods, fmts):
    """Лист «Опоздания и переработки»: свод по сотруднику за период."""
    ws = _new_sheet(writer, "Опоздания и переработки")
    headers = ["ФИО", "Отдел", "Опозданий, дней", "Σ опозданий, мин",
               "Переработка, ч"]
    widths = [32, 18, 15, 16, 14]
    for c, (h, w) in enumerate(zip(headers, widths)):
        ws.set_column(c, c, w)
        ws.write(0, c, h, fmts["header"])
    items = [e for e in periods.values() if e.late_count > 0 or e.overtime_total > 0]
    items.sort(key=lambda e: (-e.late_count, -e.overtime_total, e.name))
    row = 1
    for ep in items:
        ws.write(row, 0, ep.name, fmts["left"])
        ws.write(row, 1, ep.dept or "Без отдела", fmts["left"])
        ws.write(row, 2, ep.late_count, fmts["warn"] if ep.late_count else fmts["white"])
        ws.write(row, 3, ep.late_minutes, fmts["white"])
        ws.write(row, 4, ep.overtime_total, fmts["warn"] if ep.overtime_total else fmts["white"])
        row += 1
    if not items:
        ws.write(1, 0, "Опозданий и переработок не найдено (графики не заданы?)", fmts["good"])
    ws.freeze_panes(1, 0)
    ws.autofilter(0, 0, max(row - 1, 1), len(headers) - 1)
    return len(items)
