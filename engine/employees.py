# -*- coding: utf-8 -*-
"""Чтение ЛЭЗ/Сотрудники.txt (фиксированное время прихода).

Перенос SCUD.load_fixed_start_employees без глобалей. В веб-версии (Фаза 1+)
эти данные переедут в БД (employees.fixed_time), но для Фазы 0/совместимости
загрузчик нужен как есть."""
import os

EMPLOYEES_FILENAME = "Сотрудники.txt"


def load_fixed_start_employees(wp, name_format):
    """{ФИО (name_format): 'ЧЧ:ММ'} по активным строкам с суффиксом '=ЧЧ:ММ'.
    Удалённые ('!'/'!-') пропускаются."""
    fixed = {}
    path = os.path.join(wp, "ЛЭЗ", EMPLOYEES_FILENAME)
    try:
        with open(path, encoding="utf_8_sig") as fh:
            for line in fh.readlines():
                line = line.strip()
                if not line or line.startswith("!"):
                    continue
                if "=" not in line:
                    continue
                name_part, time_part = line.split("=", 1)
                name_part = name_part.strip()
                time_part = time_part.strip()
                if name_part and time_part:
                    fixed[name_format(name_part)] = time_part
    except Exception as e:
        print(f'load_fixed_start_employees: {e}')
    return fixed


def load_active_employees(wp, name_format):
    """Множество активных ФИО (name_format) из Сотрудники.txt — строки без '!'.

    Зеркалит активную ветку read_employees_file: уволенные/убывшие ('!'/'!-')
    исключаются. Нужно лишь для воспроизведения выборки сотрудников легаси
    start(); веб-версия берёт активность из БД (employees.is_active)."""
    active = set()
    path = os.path.join(wp, "ЛЭЗ", EMPLOYEES_FILENAME)
    try:
        with open(path, encoding="utf_8_sig") as fh:
            for raw in fh.readlines():
                line = raw.replace("\n", "")
                if not line.strip() or "!" in line:
                    continue
                name_clean = line.split("=", 1)[0].strip() if "=" in line else line.strip()
                if name_clean:
                    active.add(name_format(name_clean))
    except Exception as e:
        print("load_active_employees:", e)
    return active
