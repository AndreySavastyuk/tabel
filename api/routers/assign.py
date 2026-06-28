# -*- coding: utf-8 -*-
"""Массовое назначение из файла (только Кадры/Админ): предпросмотр сопоставления
ФИО→сотрудник и применение подтверждённых назначений отдела/графика/кабинета."""
import os
import shutil
import tempfile

from fastapi import (APIRouter, Depends, File, HTTPException, UploadFile,
                     status)
from sqlalchemy.orm import Session

from ..constants import Role
from ..db import get_db
from ..deps import require_role
from ..schemas import AssignApplyIn, AssignApplyResult, AssignPreviewRow
from ..services import assign as svc

router = APIRouter(prefix="/assign", tags=["assign"],
                   dependencies=[Depends(require_role(Role.admin_hr))])


@router.post("/preview", response_model=list[AssignPreviewRow])
def preview(file: UploadFile = File(...), db: Session = Depends(get_db)):
    tmp = tempfile.mkdtemp(prefix="assign_")
    try:
        src = os.path.join(tmp, os.path.basename(file.filename or "assign.xlsx"))
        with open(src, "wb") as out:
            shutil.copyfileobj(file.file, out)
        try:
            parsed = svc.parse_sheet(src)
        except Exception as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Не удалось прочитать файл: {e}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return svc.preview(db, parsed)


@router.post("/apply", response_model=AssignApplyResult)
def apply(body: AssignApplyIn, db: Session = Depends(get_db)):
    return svc.apply(db, body.items)
