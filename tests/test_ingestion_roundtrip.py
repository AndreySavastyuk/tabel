# -*- coding: utf-8 -*-
"""Гейт Фазы 2 (round-trip): аналитический xlsx, собранный ИЗ БД после ингеста,
ИДЕНТИЧЕН xlsx, собранному напрямую из тех же in-memory DayRecord/EmployeePeriod.
Это доказывает, что сериализация day_records/period_summaries без потерь.

Запуск:  python -m pytest tests/test_ingestion_roundtrip.py -q
"""
import os
import shutil
import sys
import tempfile

import openpyxl
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from api.db import Base
from api.models import PipelineRun, Upload
from api.services import export, ingestion
from scripts.seed_from_excel import import_reference


def _cells(bio):
    wb = openpyxl.load_workbook(bio, data_only=False)
    out = {}
    for ws in wb.worksheets:
        d = {}
        for row in ws.iter_rows():
            for c in row:
                if c.value is not None:
                    d[c.coordinate] = c.value
        out[ws.title] = d
    wb.close()
    return out


def test_db_roundtrip_identical_to_direct():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    TS = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = TS()
    wp = None
    try:
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

        # --- прямой путь (in-memory) ---
        wp = ingestion._assemble_workdir(uploads)
        records, periods, base, lezbase, points, weekend_fn = ingestion.compute_analytics(db, wp)
        direct = export.write_workbook_from(records, periods, weekend_fn)

        # --- через БД ---
        emap = ingestion._resolve_employees(db, set(base) | set(lezbase))
        ingestion._persist(db, run.id, records, periods, base, lezbase, points, emap)
        db.commit()
        from_db = export.write_workbook(db, run.id)

        a, b = _cells(direct), _cells(from_db)
        assert set(a) == set(b), f"листы расходятся: {set(a) ^ set(b)}"
        diffs = []
        for sheet in a:
            da, dbb = a[sheet], b[sheet]
            for k in set(da) | set(dbb):
                if da.get(k) != dbb.get(k):
                    diffs.append((sheet, k, da.get(k), dbb.get(k)))
        assert not diffs, f"расхождений ячеек: {len(diffs)}; первые: {diffs[:5]}"

        n_days = db.query(__import__('api.models', fromlist=['DayRecordRow']).DayRecordRow).filter_by(run_id=run.id).count()
        print(f"OK: round-trip identical; day_records persisted={n_days}, employees={len(periods)}")
    finally:
        db.close()
        if wp:
            shutil.rmtree(wp, ignore_errors=True)
        engine.dispose()
        os.unlink(path)
