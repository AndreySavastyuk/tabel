# -*- coding: utf-8 -*-
"""Разбор ФИО / алиасов (только Кадры/Админ): очередь нераспознанных имён с
подсказкой кандидатов, подтверждение как нового сотрудника и слияние дубля."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..constants import Role
from ..db import get_db
from ..deps import require_role
from ..models import EmployeeAlias
from ..schemas import MergeIn, UnresolvedAlias
from ..services import aliases as svc

router = APIRouter(prefix="/aliases", tags=["aliases"],
                   dependencies=[Depends(require_role(Role.admin_hr))])


@router.get("/count")
def count(db: Session = Depends(get_db)):
    """Дешёвый счётчик очереди разбора (для бейджа в навигации)."""
    n = db.query(EmployeeAlias).filter(EmployeeAlias.confirmed.is_(False)).count()
    return {"unresolved": n}


@router.get("/unresolved", response_model=list[UnresolvedAlias])
def unresolved(db: Session = Depends(get_db), limit: int = Query(500, le=2000)):
    return svc.list_unresolved(db, limit=limit)


@router.post("/{alias_id}/confirm", status_code=status.HTTP_200_OK)
def confirm(alias_id: int, db: Session = Depends(get_db)):
    try:
        svc.confirm_alias(db, alias_id)
    except LookupError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e))
    return {"ok": True}


@router.post("/{alias_id}/merge", status_code=status.HTTP_200_OK)
def merge(alias_id: int, body: MergeIn, db: Session = Depends(get_db)):
    alias = db.get(EmployeeAlias, alias_id)
    if alias is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Алиас не найден")
    try:
        return svc.merge_employee(db, alias.employee_id, body.target_employee_id)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    except LookupError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e))
