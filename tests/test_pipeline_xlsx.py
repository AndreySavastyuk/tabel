# -*- coding: utf-8 -*-
"""End-to-end Фаза 0: аналитические листы движка ИДЕНТИЧНЫ листам, которые
настоящий легаси SCUD.start() пишет в «Общую выгрузку».

В изолированной temp-папке:
  1. копируем реальные входы (StorK.csv, SIGUR.xlsx, ЛЭЗ/),
  2. запускаем legacy start(temp, automatic=True) -> «Общая выгрузка.xlsx»,
  3. строим engine pipeline.write_analytic_workbook -> engine_out.xlsx,
  4. _cmp.py: общие листы (Отклонения/по отделам/Бухгалтерия/Нормы/Опоздания)
     должны совпасть ячейка-в-ячейку (легаси-листы Выгрузка/Фикс. — аддитивны,
     игнорируются).

Запуск (БЕЗ PYTHONUTF8 — иначе StorK.csv в легаси читается не той кодировкой):
  python tests/test_pipeline_xlsx.py
"""
import importlib.util
import io
import os
import shutil
import subprocess
import sys
import tempfile

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)


def main():
    tmp = tempfile.mkdtemp(prefix="scud_e2e_")
    try:
        # 1) копируем входы
        for f in ["StorK.csv", "SIGUR.xlsx"]:
            src = os.path.join(ROOT, f)
            if os.path.exists(src):
                shutil.copy(src, os.path.join(tmp, f))
        shutil.copytree(os.path.join(ROOT, "ЛЭЗ"), os.path.join(tmp, "ЛЭЗ"))

        # 2) легаси start() в temp
        spec = importlib.util.spec_from_file_location(
            "scud_legacy", os.path.join(ROOT, "SCUD(fixed_time)_v0.3.py"))
        scud = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(scud)
        scud.start(tmp, True)
        legacy_xlsx = os.path.join(tmp, "Общая выгрузка.xlsx")
        assert os.path.exists(legacy_xlsx), "легаси не создал Общую выгрузку"

        # 3) движок. Фильтруем по ТОЧНОМУ набору сотрудников легаси (его оставляет
        #    start() в last_day_records), чтобы изолировать сравнение вычислений и
        #    листов от ЛЕГАСИ-ОТБОРА сотрудников (find_emp/Сотрудники.txt — это
        #    хрупкое сопоставление ФИО, которое заменяется явным списком в БД;
        #    на этих данных оно отбрасывает 10 человек, которых engine сохраняет).
        legacy_universe = set(scud.last_day_records)
        from engine import pipeline
        engine_xlsx = os.path.join(tmp, "engine_out.xlsx")
        pipeline.write_analytic_workbook(tmp, engine_xlsx, names=legacy_universe)

        # 4) сравнение (engine = A: его листы должны все присутствовать и совпасть
        #    в B=легаси; лишние листы легаси — аддитивны и игнорируются)
        r = subprocess.run(
            [sys.executable, os.path.join(ROOT, "_cmp.py"), engine_xlsx, legacy_xlsx],
            capture_output=True, text=True, encoding="utf-8",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        print(r.stdout.strip())
        if r.stderr.strip():
            print("stderr:", r.stderr.strip()[:500])
        if r.returncode != 0:
            raise AssertionError("аналитические листы движка расходятся с легаси")
        print("PIPELINE E2E: PASS (аналитические листы идентичны легаси)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
