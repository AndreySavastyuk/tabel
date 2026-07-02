# -*- coding: utf-8 -*-
"""Поквартальный свод переработок за год. Руководитель отдела видит только свой
отдел; кадры/бухгалтер — всех."""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..constants import Role
from ..db import get_db
from ..deps import get_current_user, scoped_department_id
from ..services import overtime as ot_service

router = APIRouter(prefix="/overtime", tags=["overtime"])


@router.get("")
def overtime_report(year: Optional[int] = Query(None),
                    db: Session = Depends(get_db), user=Depends(get_current_user)):
    years = ot_service.available_years(db)
    if year is None:
        year = years[0] if years else datetime.now(timezone.utc).year
    dept = scoped_department_id(user) if user.role == Role.dept_head.value else None
    if user.role == Role.dept_head.value and dept is None:
        return {"year": year, "years": years, "rows": []}
    return {"year": year, "years": years,
            "rows": ot_service.overtime_report(db, year, department_id=dept)}
