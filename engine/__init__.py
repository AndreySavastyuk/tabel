# -*- coding: utf-8 -*-
"""Чистый расчётный движок табеля СКУД (извлечён из SCUD(fixed_time)_v0.3.py).

Без tkinter, без глобалей, импортируемый. Слои:
  model     — dataclass DayRecord/EmployeePeriod, пороги, коды отклонений
  compute   — чистые вычисления (обед, опоздания, переработки, свод за период)
  shifts    — разбиение событий на смены + build_day_records (ночные смены)
  refdata   — RefData + загрузчики Excel-справочников (для разовой миграции)
  report    — писатели аналитических листов xlsx
  parsers   — парсеры сырых выгрузок СКУД (StorK/SIGUR/Hikvision/ЛЭЗ)
  bases     — оркестратор парсинга (аналог bases_creator, без состояния)
  timeutil  — date_format/date_former/base_sort
  calendar  — выходные/праздники (замена DateWorker)
  names     — name_format + нечёткое сопоставление ФИО
"""
