# -*- coding: utf-8 -*-
"""Перечисления домена (строковые, для переносимости SQLite↔PostgreSQL)."""
from enum import Enum


class Role(str, Enum):
    admin_hr = "admin_hr"        # Кадры/Админ — полный доступ
    accountant = "accountant"    # Бухгалтер — деньги/нормы/аванс
    dept_head = "dept_head"      # Руководитель отдела — свой отдел, без зарплат


class AbsenceType(str, Enum):
    vacation = "отпуск"
    sick = "больничный"
    trip = "командировка"
    timeoff = "отгул"            # НОВОЕ — с подтверждением


class AbsenceStatus(str, Enum):
    draft = "draft"
    submitted = "submitted"
    approved = "approved"
    rejected = "rejected"


class AliasSource(str, Enum):
    stork = "stork"
    sigur = "sigur"
    hikvision = "hikvision"
    lez = "lez"
    manual = "manual"


class UploadSource(str, Enum):
    stork = "stork"          # StorK.csv
    sigur = "sigur"          # SIGUR.xlsx
    hikvision = "hikvision"  # report.xls
    lez = "lez"              # ЛЭЗ/lez.xlsx (проходная)


class HolidayKind(str, Enum):
    weekend = "weekend"
    holiday = "holiday"                      # праздничный день (сокращает предыдущий день −1 ч)
    dayoff = "dayoff"                        # перенесённый выходной (нерабочий, но НЕ сокращает)
    workday_override = "workday_override"    # рабочий день, выпавший на сб/вс (перенос)


# Роли, которым видны денежные поля (ставка, оплата переработки).
MONEY_ROLES = {Role.admin_hr, Role.accountant}
