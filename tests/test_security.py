# -*- coding: utf-8 -*-
"""JWT-claims и bcrypt: токен без обязательных claim'ов отвергается; новые хэши
используют настроенную стоимость bcrypt. Запуск:
python -m pytest tests/test_security.py -q
"""
import os
import sys

import jwt
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from api import security
from api.config import settings


def test_valid_token_roundtrip():
    p = security.decode_token(security.create_access_token(7, "admin_hr"))
    assert p["sub"] == "7" and p["role"] == "admin_hr"


def test_decode_rejects_token_without_required_claims():
    # токен без exp/iat — никогда не истекает; должен отвергаться
    bad = jwt.encode({"sub": "1", "role": "admin_hr"},
                     settings.secret_key, algorithm=settings.algorithm)
    with pytest.raises(jwt.exceptions.MissingRequiredClaimError):
        security.decode_token(bad)


def test_bcrypt_uses_configured_rounds():
    h = security.hash_password("correct horse battery staple")
    assert h.startswith(f"$2b${max(12, settings.bcrypt_rounds):02d}$")
    assert security.verify_password("correct horse battery staple", h)
    assert not security.verify_password("wrong", h)
