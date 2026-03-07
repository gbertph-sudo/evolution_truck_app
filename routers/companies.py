from __future__ import annotations

# routers/companies.py
# Comentarios en español. Strings en inglés.

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from database import get_db
from models import Company, User
from schemas import CompanyCreate, CompanyOut
from security import require_roles

router = APIRouter(prefix="/companies", tags=["Companies"])

# Ajusta si quieres: quién puede crear/editar/borrar companies
COMPANY_ADMIN_ROLES = ["SUPERADMIN", "ADMIN"]

# Roles que pueden ver companies
COMPANY_VIEW_ROLES = ["SUPERADMIN", "ADMIN", "ACCOUNTANT", "VENDEDOR", "MECANICO"]


@router.post("", response_model=CompanyOut, status_code=status.HTTP_201_CREATED)
def create_company(
    payload: CompanyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*COMPANY_ADMIN_ROLES)),
):
    name = (payload.name or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="Company name is required")

    # ✅ evita duplicados por mayúsculas/minúsculas
    exists = db.execute(
        select(Company.id).where(func.lower(Company.name) == func.lower(name))
    ).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=409, detail="Company already exists")

    c = Company(name=name)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


@router.get("", response_model=list[CompanyOut])
def list_companies(
    q: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*COMPANY_VIEW_ROLES)),
):
    stmt = select(Company).order_by(Company.name.asc())
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(Company.name.ilike(like))

    return list(db.execute(stmt).scalars().all())


@router.get("/{company_id}", response_model=CompanyOut)
def get_company(
    company_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*COMPANY_VIEW_ROLES)),
):
    c = db.get(Company, company_id)
    if not c:
        raise HTTPException(status_code=404, detail="Company not found")
    return c


@router.patch("/{company_id}", response_model=CompanyOut)
def update_company(
    company_id: int,
    payload: CompanyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*COMPANY_ADMIN_ROLES)),
):
    c = db.get(Company, company_id)
    if not c:
        raise HTTPException(status_code=404, detail="Company not found")

    name = (payload.name or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="Company name is required")

    exists = db.execute(
        select(Company.id).where(
            func.lower(Company.name) == func.lower(name),
            Company.id != company_id,
        )
    ).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=409, detail="Company already exists")

    c.name = name
    if hasattr(c, "updated_at"):
        c.updated_at = datetime.utcnow()

    db.add(c)
    db.commit()
    db.refresh(c)
    return c


@router.delete("/{company_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_company(
    company_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*COMPANY_ADMIN_ROLES)),
):
    c = db.get(Company, company_id)
    if not c:
        raise HTTPException(status_code=404, detail="Company not found")

    db.delete(c)
    db.commit()
    return