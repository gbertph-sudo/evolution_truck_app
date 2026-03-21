from __future__ import annotations

# routers/companies.py
# Comentarios en español. Strings en inglés.

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database import get_db
from models import Company, User
from schemas import CompanyCreate, CompanyOut
from security import require_roles

router = APIRouter(prefix="/companies", tags=["Companies"])

COMPANY_ADMIN_ROLES = ["SUPERADMIN", "ADMIN"]
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

    exists = db.execute(
        select(Company.id).where(func.lower(Company.name) == func.lower(name))
    ).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=409, detail="Company already exists")

    company = Company(name=name)
    db.add(company)
    db.commit()
    db.refresh(company)
    return company


@router.get("", response_model=list[CompanyOut])
def list_companies(
    q: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*COMPANY_VIEW_ROLES)),
):
    stmt = select(Company).order_by(Company.id.asc())
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
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


@router.patch("/{company_id}", response_model=CompanyOut)
def update_company(
    company_id: int,
    payload: CompanyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*COMPANY_VIEW_ROLES)),
):
    company = db.get(Company, company_id)
    if not company:
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

    company.name = name
    if hasattr(company, "updated_at"):
        company.updated_at = datetime.utcnow()

    db.add(company)
    db.commit()
    db.refresh(company)
    return company


@router.delete("/{company_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_company(
    company_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*COMPANY_ADMIN_ROLES)),
):
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    db.delete(company)
    db.commit()
    return
