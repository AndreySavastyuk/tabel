# -*- coding: utf-8 -*-
"""Нормализованная модель табеля (SCUD v0.3).

DayRecord — одна запись на сотрудника на календарный день. В отличие от
старого слияния всех систем в общий `base`, здесь отметки внутренних СКУД
(StorK/SIGUR/Hikvision) и проходной ЛЭЗ хранятся РАЗДЕЛЬНО — это нужно для
кросс-проверки двух систем и для детекции повторного входа на территорию.

EmployeePeriod — свёртка по сотруднику за период (для листов «Бухгалтерия»,
«Нормы», «Опоздания и переработки»).
"""
from dataclasses import dataclass, field
from typing import Optional, List, Tuple


@dataclass
class DayRecord:
    # --- идентификация ---
    name: str
    date: str                                   # "DD.MM.YYYY"
    is_weekend: bool = False

    # --- внутренние СКУД (StorK + SIGUR + Hikvision) ---
    int_entry: Optional[str] = None             # "HH:MM" или None
    int_exit: Optional[str] = None
    int_pairs: List[Tuple[str, str]] = field(default_factory=list)  # [(вход, выход), ...]

    # --- проходная ЛЭЗ ---
    lez_entry: Optional[str] = None
    lez_exit: Optional[str] = None
    lez_events: List[Tuple[str, str]] = field(default_factory=list)  # [("HH:MM", "Вход"/"Выход"), ...]

    # --- итоговые / вычисленные ---
    entry: Optional[str] = None                 # выбранный вход (для табеля)
    exit: Optional[str] = None
    entry_source: Optional[str] = None          # "internal" / "LEZ" / None
    exit_source: Optional[str] = None
    start_fixed: bool = False                   # время прихода подменено на фикс.
    original_start: Optional[str] = None        # фактический приход до подмены
    raw_hours: float = 0.0                      # (выход - вход) без обеда
    lunch_deducted: float = 0.0                 # вычтено на обед, ч
    worked_hours: float = 0.0                   # raw_hours - lunch_deducted (цифра табеля)

    # --- нормы / отсутствия ---
    schedule: Optional[str] = None
    dept: Optional[str] = None
    cabinet: Optional[str] = None               # кабинет внутри отдела
    lez_controlled: bool = False                # обязан проходить ЛЭЗ
    dual_tracked: bool = False                  # есть отметки И во внутренней, И в ЛЭЗ за период
    day_norm: float = 0.0
    absence: Optional[str] = None               # "отпуск"/"больничный"/"командировка"/None
    lateness_min: int = 0
    overtime_h: float = 0.0

    # --- флаги отклонений (пусто = запись чистая) ---
    deviations: List[str] = field(default_factory=list)


@dataclass
class EmployeePeriod:
    name: str
    schedule: Optional[str] = None
    dept: Optional[str] = None
    worked_total: float = 0.0                   # фактически отработанные часы
    credited_total: float = 0.0                 # отработка + зачёт отсутствий
    period_norm: float = 0.0
    absence_days: dict = field(default_factory=dict)   # {тип: кол-во дней}
    late_count: int = 0
    late_minutes: int = 0
    overtime_total: float = 0.0
    percent: float = 0.0                        # credited_total / period_norm * 100
    bucket: str = ""                            # "<25%" / "25-50%" / "50-75%" / ">75%"


# Пороги по умолчанию (Фаза 5 вынесет в конфиг).
THRESHOLDS = {
    # Расхождение времён между ЛЭЗ (проходная) и внутренней СКУД (кабинет)
    # естественно составляет несколько минут (дойти от проходной). Поэтому
    # порог высокий — флагуем только грубые расхождения, чтобы лист отклонений
    # оставался коротким. Подстраивается заказчиком.
    "time_mismatch_min": 120,       # расхождение времён между системами, мин
    "implausible_hours_max": 16.0,  # верхняя граница правдоподобия, ч
    "implausible_hours_min": 0.0,   # worked <= этого -> подозрительно
    "lateness_grace_min": 0,        # грейс опоздания, мин
    "reentry_gap_min": 30,          # разрыв выход->вход на ЛЭЗ, мин (эпизод)
    # Порог по СУММЕ отлучек за день для отклонения «выход с территории».
    # Читается API-слоем (api.services.ingestion), движок его не использует —
    # ключ живёт здесь, чтобы редактироваться из Настроек как остальные пороги.
    "away_daily_min": 30,           # суммарно вне территории за день, мин
    # Разбиение событий на смены: перерыв больше этого начинает новую смену.
    # Меньше — внутрисменная отлучка/обед (вход-выход внутри смены сливаются).
    # Больше 5 ч естественно отделяет ночные смены (вечер -> утро) друг от друга.
    "shift_gap_min": 300,           # порог разрыва между сменами, мин (5 ч)
    "max_shift_min": 960,           # максимальная длительность смены, мин (16 ч)
}

# Коды отклонений для листа «Отклонения».
DEV_ONLY_INTERNAL = "ONLY_INTERNAL"     # есть во внутренней, нет в ЛЭЗ (за отсутствующего?)
DEV_ONLY_LEZ = "ONLY_LEZ"               # есть в ЛЭЗ, нет во внутренней
DEV_MISSING_ENTRY = "MISSING_ENTRY"
DEV_MISSING_EXIT = "MISSING_EXIT"
DEV_TIME_MISMATCH = "TIME_MISMATCH"
DEV_IMPLAUSIBLE = "IMPLAUSIBLE_HOURS"
DEV_REENTRY = "REENTRY_GAP"

DEV_LABELS = {
    DEV_ONLY_INTERNAL: "Только внутренняя система (нет ЛЭЗ)",
    DEV_ONLY_LEZ: "Только ЛЭЗ (нет внутренней)",
    DEV_MISSING_ENTRY: "Нет входа",
    DEV_MISSING_EXIT: "Нет выхода",
    DEV_TIME_MISMATCH: "Расхождение времени систем",
    DEV_IMPLAUSIBLE: "Нулевые/неправдоподобные часы",
    DEV_REENTRY: "Выход с территории > 30 мин",
}
