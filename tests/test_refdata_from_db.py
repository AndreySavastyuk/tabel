# -*- coding: utf-8 -*-
"""Гейт Фазы 2b: RefData, собранный из БД, ИДЕНТИЧЕН RefData из ЛЭЗ/*.xlsx.
Это гарантирует, что движок на DB-данных считает так же, как на Excel.

Запуск:  python -m pytest tests/test_refdata_from_db.py -q
"""
import os
import sys
import tempfile

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.names import name_format
from engine.refdata import load_reference_data

from api.db import Base
from api.services.refdata_from_db import build_fixed_times, build_refdata
from scripts.seed_from_excel import import_reference


def test_refdata_db_matches_excel():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    try:
        import_reference(db, ROOT)
        db.commit()
        ref_db = build_refdata(db)
        fixed_db = build_fixed_times(db)
    finally:
        db.close()
        engine.dispose()
        os.unlink(path)

    ref_xl = load_reference_data(ROOT, name_normalizer=name_format)

    assert ref_db.dept_by_name == ref_xl.dept_by_name
    assert ref_db.cabinet_by_name == ref_xl.cabinet_by_name
    assert ref_db.schedule_by_name == ref_xl.schedule_by_name
    assert ref_db.fixed_times == ref_xl.fixed_times
    assert ref_db.lez_controlled == ref_xl.lez_controlled
    assert ref_db.norms == ref_xl.norms
    assert ref_db.shift_start == ref_xl.shift_start
    assert ref_db.shift_len == ref_xl.shift_len
    assert ref_db.lunch == ref_xl.lunch
    assert ref_db.absences == ref_xl.absences
    assert fixed_db == ref_xl.fixed_times
