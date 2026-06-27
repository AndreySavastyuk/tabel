# -*- coding: utf-8 -*-
"""Гейт Фазы 2 (легаси-паритет): xlsx, выгруженный ИЗ БД после полного веб-ингеста
(upload → process_run → export), совпадает по значениям с листами, которые пишет
настоящий legacy start(). Сравнение по той же выборке сотрудников, что у легаси.

Запуск (БЕЗ PYTHONUTF8):  python -m pytest tests/test_export_vs_legacy.py -q
"""
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEGACY = os.path.join(ROOT, "legacy")
sys.path.insert(0, ROOT)
# legacy/ на путь — для bare-импортов легаси внутри SCUD*.py после переноса.
sys.path.insert(0, LEGACY)

from api.db import Base
from api.models import PipelineRun, Upload
from api.services import export, ingestion
from scripts.seed_from_excel import import_reference


def _load_legacy(wp):
    spec = importlib.util.spec_from_file_location(
        "scud_legacy", os.path.join(LEGACY, "SCUD(fixed_time)_v0.3.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m.start(wp, True)
    return m


def test_db_export_matches_legacy():
    # Требует реальных выгрузок СКУД в корне репозитория (ПДн, не в git).
    # На чистом клоне/CI их нет — пропускаем, а не падаем.
    required = [os.path.join(ROOT, "StorK.csv"),
                os.path.join(ROOT, "SIGUR.xlsx"),
                os.path.join(ROOT, "ЛЭЗ", "lez.xlsx")]
    missing = [os.path.basename(p) for p in required if not os.path.exists(p)]
    if missing:
        pytest.skip("нет реальных выгрузок (" + ", ".join(missing) + ") — легаси-паритет пропущен")

    tmp = tempfile.mkdtemp(prefix="scud_legacy_")
    fd, dbpath = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{dbpath}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    TS = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    try:
        # данные для легаси: копия входов в temp
        for f in ["StorK.csv", "SIGUR.xlsx"]:
            if os.path.exists(os.path.join(ROOT, f)):
                shutil.copy(os.path.join(ROOT, f), os.path.join(tmp, f))
        shutil.copytree(os.path.join(ROOT, "ЛЭЗ"), os.path.join(tmp, "ЛЭЗ"))

        scud = _load_legacy(tmp)
        legacy_xlsx = os.path.join(tmp, "Общая выгрузка.xlsx")
        assert os.path.exists(legacy_xlsx)
        roster = set(scud.last_day_records)        # выборка сотрудников легаси

        # веб-ингест: БД из тех же справочников + загрузки реальных файлов
        db = TS()
        import_reference(db, ROOT)
        db.commit()
        uploads = [
            Upload(filename="StorK.csv", source="stork", stored_path=os.path.join(ROOT, "StorK.csv")),
            Upload(filename="SIGUR.xlsx", source="sigur", stored_path=os.path.join(ROOT, "SIGUR.xlsx")),
            Upload(filename="lez.xlsx", source="lez", stored_path=os.path.join(ROOT, "ЛЭЗ", "lez.xlsx")),
        ]
        db.add_all(uploads)
        db.flush()
        run = PipelineRun(upload_ids=[u.id for u in uploads], status="queued")
        db.add(run)
        db.commit()
        run_id = run.id
        db.close()

        ingestion.process_run(run_id, TS, names=roster)

        db = TS()
        run = db.get(PipelineRun, run_id)
        assert run.status == "done", f"run failed: {run.error_text}"
        out = os.path.join(tmp, "engine_db_export.xlsx")
        with open(out, "wb") as fh:
            fh.write(export.write_workbook(db, run_id).getbuffer())
        db.close()

        r = subprocess.run(
            [sys.executable, os.path.join(LEGACY, "_cmp.py"), out, legacy_xlsx],
            capture_output=True, text=True, encoding="utf-8",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        print(r.stdout.strip())
        assert r.returncode == 0, "DB-экспорт расходится с легаси"
    finally:
        engine.dispose()
        shutil.rmtree(tmp, ignore_errors=True)
        os.unlink(dbpath)
