# -*- coding: utf-8 -*-
"""Золотой регресс Фазы 0: движок engine/ воспроизводит ЛЕГАСИ побитно на
РЕАЛЬНЫХ данных репозитория.

Сравнивается:
  1. Парсинг: engine.bases.build_bases(wp) == legacy bases_creator (base/lezbase/points)
  2. build_day_records: engine.shifts == legacy SCUD на одинаковых входах
     (asdict каждого DayRecord совпадает)

Чтение файлов — НЕдеструктивно (start()/sync не вызываются). Запуск:
  python tests/test_golden_vs_legacy.py
"""
import dataclasses
import importlib.util
import io
import os
import sys

# Печать в utf-8, НЕ трогая кодировку open() по умолчанию (StorK.csv читается
# по локали = cp1251; форсировать PYTHONUTF8 нельзя — сломает чтение StorK).
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from engine import bases as engine_bases
from engine import calendar as engine_cal
from engine import names as engine_names
from engine import refdata as engine_refdata
from engine import shifts as engine_shifts

WP = ROOT


def load_legacy():
    spec = importlib.util.spec_from_file_location(
        "scud_legacy", os.path.join(ROOT, "SCUD(fixed_time)_v0.3.py")
    )
    scud = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scud)
    return scud


def legacy_bases(scud, wp):
    # Инициализируем глобали, которые ожидает bases_creator().
    for g in ["base", "lezbase", "allbase", "base_classes",
              "lezbase_classes", "allbase_classes", "base_to_out", "points"]:
        setattr(scud, g, {})
    scud.wp = wp
    scud.bases_creator()
    return scud.base, scud.lezbase, scud.points


def main():
    scud = load_legacy()

    # --- 1. Парсинг ---
    lbase, llez, lpoints = legacy_bases(scud, WP)
    ebase, elez, epoints = engine_bases.build_bases(WP)

    assert ebase == lbase, "base расходится (engine vs legacy)"
    assert elez == llez, "lezbase расходится"
    assert epoints == lpoints, "points расходится"
    print(f"парсинг: PASS  (base={len(ebase)} чел, lezbase={len(elez)} чел, "
          f"points={len(epoints)})")

    # --- 2. build_day_records на одинаковых входах ---
    ref = engine_refdata.load_reference_data(WP, name_normalizer=engine_names.name_format)
    fixed = scud.load_fixed_start_employees(WP)
    rebuild = {n: [] for n in (set(ebase) | set(elez))}

    legacy_recs = scud.build_day_records(
        rebuild, ebase, elez, ref=ref, fixed_employees=fixed, apply_fixed=True)
    engine_recs = engine_shifts.build_day_records(
        rebuild, ebase, elez, ref=ref, fixed_employees=fixed, apply_fixed=True,
        weekend_fn=engine_cal.legacy_weekend)

    assert set(legacy_recs) == set(engine_recs), "набор сотрудников расходится"
    mismatches = []
    total = 0
    for name in legacy_recs:
        a = [dataclasses.asdict(dr) for dr in legacy_recs[name]]
        b = [dataclasses.asdict(dr) for dr in engine_recs[name]]
        total += len(a)
        if a != b:
            first = next((x for x, y in zip(a, b) if x != y), "(длина: %d vs %d)" % (len(a), len(b)))
            mismatches.append((name, first))

    if mismatches:
        print(f"build_day_records: РАСХОЖДЕНИЙ {len(mismatches)} из {len(legacy_recs)} чел")
        for name, first in mismatches[:5]:
            print("   ", name, "->", first)
        raise AssertionError("build_day_records расходится с легаси")
    print(f"build_day_records: PASS  ({len(engine_recs)} чел, {total} записей-дней)")
    print("ALL GOLDEN TESTS PASS")


if __name__ == "__main__":
    main()
