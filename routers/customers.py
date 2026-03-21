from __future__ import annotations

# routers/customers.py
# Comentarios en español. Strings en inglés.

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from database import get_db
from models import Company, Customer, User
from schemas import CustomerCreate, CustomerOut, CustomerUpdate
from security import require_roles

router = APIRouter(prefix="/customers", tags=["Customers"])

CUSTOMER_ROLES = ["SUPERADMIN", "ADMIN", "ACCOUNTANT", "VENDEDOR", "MECANICO"]
CUSTOMER_ADMIN_ROLES = ["SUPERADMIN", "ADMIN"]


def _fill_customer_company_ids(customer: Customer) -> Customer:
    try:
        customer.company_ids = [x.id for x in (customer.companies or [])]  # type: ignore[attr-defined]
    except Exception:
        pass
    return customer


def _load_companies_by_ids(db: Session, ids: list[int]) -> list[Company]:
    if not ids:
        return []
    rows = db.execute(select(Company).where(Company.id.in_(ids))).scalars().all()
    found = {x.id for x in rows}
    missing = [x for x in ids if x not in found]
    if missing:
        raise HTTPException(status_code=422, detail=f"Invalid company_ids: {missing}")
    return list(rows)


@router.post("", response_model=CustomerOut, status_code=status.HTTP_201_CREATED)
def create_customer(
    payload: CustomerCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*CUSTOMER_ROLES)),
):
    name = (payload.name or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="Customer name is required")

    customer = Customer(
        name=name,
        phone=payload.phone,
        email=str(payload.email) if payload.email else None,
    )
    if hasattr(Customer, "is_active"):
        customer.is_active = True  # type: ignore[attr-defined]

    customer.companies = _load_companies_by_ids(db, payload.company_ids or [])

    db.add(customer)
    db.commit()
    db.refresh(customer)
    return _fill_customer_company_ids(customer)


@router.get("", response_model=list[CustomerOut])
def list_customers(
    q: Optional[str] = Query(default=None),
    include_inactive: bool = Query(default=False, description="If true, includes inactive customers"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*CUSTOMER_ROLES)),
):
    stmt = select(Customer).order_by(Customer.id.asc())

    if hasattr(Customer, "is_active") and not include_inactive:
        stmt = stmt.where(Customer.is_active.is_(True))  # type: ignore[attr-defined]

    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Customer.name.ilike(like),
                Customer.phone.ilike(like),
                Customer.email.ilike(like),
            )
        )

    rows = list(db.execute(stmt).scalars().all())
    return [_fill_customer_company_ids(x) for x in rows]


@router.get("/{customer_id}", response_model=CustomerOut)
def get_customer(
    customer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*CUSTOMER_ROLES)),
):
    customer = db.get(Customer, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    return _fill_customer_company_ids(customer)


@router.patch("/{customer_id}", response_model=CustomerOut)
def update_customer(
    customer_id: int,
    payload: CustomerUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*CUSTOMER_ROLES)),
):
    customer = db.get(Customer, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    data = payload.model_dump(exclude_unset=True)

    if "name" in data and data["name"] is not None:
        name = str(data["name"]).strip()
        if not name:
            raise HTTPException(status_code=422, detail="Customer name is required")
        customer.name = name

    if "phone" in data:
        customer.phone = data["phone"]

    if "email" in data:
        customer.email = str(data["email"]) if data["email"] else None

    if "company_ids" in data and data["company_ids"] is not None:
        customer.companies = _load_companies_by_ids(db, data["company_ids"])

    if "is_active" in data and hasattr(customer, "is_active"):
        customer.is_active = bool(data["is_active"])  # type: ignore[attr-defined]

    if hasattr(customer, "updated_at"):
        customer.updated_at = datetime.utcnow()

    db.add(customer)
    db.commit()
    db.refresh(customer)
    return _fill_customer_company_ids(customer)


@router.patch("/{customer_id}/active")
def toggle_customer_active(
    customer_id: int,
    body: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*CUSTOMER_ADMIN_ROLES)),
):
    customer = db.get(Customer, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    if not hasattr(customer, "is_active"):
        raise HTTPException(status_code=400, detail="Customer.is_active not available")
    if "is_active" not in body:
        raise HTTPException(status_code=422, detail="is_active required")

    customer.is_active = bool(body["is_active"])  # type: ignore[attr-defined]
    if hasattr(customer, "updated_at"):
        customer.updated_at = datetime.utcnow()

    db.add(customer)
    db.commit()
    db.refresh(customer)
    return {"id": customer.id, "is_active": bool(getattr(customer, "is_active", True))}


@router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_customer(
    customer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*CUSTOMER_ADMIN_ROLES)),
):
    customer = db.get(Customer, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    db.delete(customer)
    db.commit()
    return
