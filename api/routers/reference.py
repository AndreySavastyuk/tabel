# -*- coding: utf-8 -*-
"""Импорт справочников из Excel в БД через UI (только Кадры/Админ).

Один файл за запрос: kind задаёт тип (employees/norms/absences/trips), файл
сохраняется во временную папку и прогоняется через тот же импорт, что и сидер."""
import os
import shutil
import tempfile

from fastapi import (APIRouter, Depends, File, Form, HTTPException, UploadFile,
                     status)
from sqlalchemy.orm import Session

from ..constants import ReferenceKind, Role
from ..db import get_db
from ..deps import require_role
from ..schemas import ReferenceImportResult
from ..services.reference_import import import_reference_upload

router = APIRouter(prefix="/reference", tags=["reference"])


@router.post("/import", response_model=ReferenceImportResult,
             status_code=status.HTTP_201_CREATED)
def import_reference_file(kind: ReferenceKind = Form(...),
                         file: UploadFile = File(...),
                         db: Session = Depends(get_db),
                         _=Depends(require_role(Role.admin_hr))):
    tmp = tempfile.mkdtemp(prefix="ref_upload_")
    try:
        src = os.path.join(tmp, os.path.basename(file.filename or "reference.xlsx"))
        with open(src, "wb") as out:
            shutil.copyfileobj(file.file, out)
        try:
            res = import_reference_upload(db, kind, src)
        except Exception as e:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Не удалось импортировать справочник: {e}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return ReferenceImportResult(
        kind=kind.value, filename=file.filename or "",
        before=res["before"], after=res["after"])
