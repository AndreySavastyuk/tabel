# -*- coding: utf-8 -*-
"""Прод-гейт Settings: в проде небезопасные dev-дефолты отвергаются (fail fast),
а dev/полная прод-конфигурация поднимаются. Запуск:
python -m pytest tests/test_config_prod.py -q
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from api.config import INSECURE_SECRET, Settings

GOOD = dict(env="prod", secret_key="x" * 40, cors_origins="https://tabel.example",
            database_url="postgresql+psycopg://u:p@h/db",
            upload_dir="/var/lib/tabel/uploads")


def test_dev_defaults_boot():
    s = Settings(env="dev")
    assert s.is_prod is False
    assert s.uploads_path.endswith("_uploads")


def test_prod_full_config_boots():
    s = Settings(**GOOD)
    assert s.is_prod is True


@pytest.mark.parametrize("override", [
    {"secret_key": INSECURE_SECRET},                 # дефолтный секрет
    {"secret_key": "short"},                          # слишком короткий
    {"algorithm": "none"},                            # запрещённый алгоритм
    {"cors_origins": "*"},                            # wildcard CORS
    {"cors_origins": "https://a.example,*"},          # '*' как элемент списка
    {"cors_origins": ""},                             # пустой CORS
    {"database_url": "sqlite:///./t.db"},             # SQLite в проде
    {"database_url": "SQLITE:///./t.db"},             # регистр схемы
    {"upload_dir": None},                             # не задан upload_dir
    {"upload_dir": "relative/uploads"},               # не абсолютный
])
def test_prod_rejects_insecure(override):
    with pytest.raises(Exception):
        Settings(**{**GOOD, **override})
