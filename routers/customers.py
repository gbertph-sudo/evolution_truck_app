from __future__ import annotations

# routers/customers.py
# Comentarios en español. Strings en inglés.

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status, Body
from sqlalchemy import select, or_
from sqlalchemy.orm import Session

from database import get_db
from models import Customer, Company, User
from schemas import CustomerCreate, CustomerUpdate, CustomerOut
from security import require_roles

router = APIRouter(prefix="/customers", tags=["Customers"])

CUSTOMER_ROLES = ["SUPERADMIN", "ADMIN", "ACCOUNTANT", "VENDEDOR", "MECANICO"]
CUSTOMER_ADMIN_ROLES = ["SUPERADMIN", "ADMIN"]  # solo estos pueden activar/desactivar (si quieres)


def _fill_customer_company_ids(c: Customer) -> Customer:
    # ✅ Para que el schema CustomerOut reciba company_ids listo
    try:
        c.company_ids = [x.id for x in (c.companies or [])]  # type: ignore[attr-defined]
    except Exception:
        pass
    return c


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

    c = Customer(
        name=name,
        phone=payload.phone,
        email=str(payload.email) if payload.email else None,
    )

    # ✅ Si existe is_active en el modelo, por defecto activo
    if hasattr(Customer, "is_active"):
        c.is_active = True  # type: ignore[attr-defined]

    # ✅ set companies (many-to-many)
    companies = _load_companies_by_ids(db, payload.company_ids or [])
    c.companies = companies

    db.add(c)
    db.commit()
    db.refresh(c)
    return _fill_customer_company_ids(c)


@router.get("", response_model=list[CustomerOut])
def list_customers(
    q: Optional[str] = Query(default=None),
    include_inactive: bool = Query(default=False, description="If true, includes inactive customers"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*CUSTOMER_ROLES)),
):
    stmt = select(Customer).order_by(Customer.name.asc())

    # ✅ Por defecto: solo activos (si existe is_active)
    if hasattr(Customer, "is_active") and not include_inactive:
        stmt = stmt.where(Customer.is_active.is_(True))  # type: ignore[attr-defined]

    if q:
        like = f"%{q.strip()}%"
        # evita ilike sobre None
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
    c = db.get(Customer, customer_id)
    if not c:
        raise HTTPException(status_code=404, detail="Customer not found")

    # si existe is_active y está inactivo, igual lo devolvemos (para editar / ver historial)
    return _fill_customer_company_ids(c)


@router.patch("/{customer_id}", response_model=CustomerOut)
def update_customer(
    customer_id: int,
    payload: CustomerUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*CUSTOMER_ROLES)),
):
    c = db.get(Customer, customer_id)
    if not c:
        raise HTTPException(status_code=404, detail="Customer not found")

    data = payload.model_dump(exclude_unset=True)

    if "name" in data and data["name"] is not None:
        name = str(data["name"]).strip()
        if not name:
            raise HTTPException(status_code=422, detail="Customer name is required")
        c.name = name

    if "phone" in data:
        c.phone = data["phone"]

    if "email" in data:
        c.email = str(data["email"]) if data["email"] else None

    # ✅ si viene company_ids, reemplaza lista completa
    if "company_ids" in data and data["company_ids"] is not None:
        companies = _load_companies_by_ids(db, data["company_ids"])
        c.companies = companies

    if hasattr(c, "updated_at"):
        c.updated_at = datetime.utcnow()

    db.add(c)
    db.commit()
    db.refresh(c)
    return _fill_customer_company_ids(c)


# ✅ ACTIVAR / DESACTIVAR (NO BORRAR)
@router.patch("/{customer_id}/active")
def toggle_customer_active(
    customer_id: int,
    body: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*CUSTOMER_ADMIN_ROLES)),
):
    c = db.get(Customer, customer_id)
    if not c:
        raise HTTPException(status_code=404, detail="Customer not found")

    if not hasattr(c, "is_active"):
        raise HTTPException(status_code=400, detail="Customer.is_active not available (missing DB column)")

    if "is_active" not in body:
        raise HTTPException(status_code=422, detail="is_active required")

    c.is_active = bool(body["is_active"])  # type: ignore[attr-defined]

    if hasattr(c, "updated_at"):
        c.updated_at = datetime.utcnow()

    db.add(c)
    db.commit()
    db.refresh(c)

    return {"id": c.id, "is_active": bool(getattr(c, "is_active", True))}

@router.get("", response_model=list[CustomerOut])
def list_customers(
    q: Optional[str] = Query(default=None),
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*CUSTOMER_ROLES)),
):
    stmt = select(Customer).order_by(Customer.name.asc())

    if not include_inactive and hasattr(Customer, "is_active"):
        stmt = stmt.where(Customer.is_active.is_(True))

    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            (Customer.name.ilike(like)) |
            (Customer.phone.ilike(like)) |
            (Customer.email.ilike(like))
        )

    rows = list(db.execute(stmt).scalars().all())
    return [_fill_customer_company_ids(x) for x in rows]


@router.patch("/{customer_id}/active")
def toggle_customer_active(
    customer_id: int,
    body: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("SUPERADMIN", "ADMIN")),
):
    c = db.get(Customer, customer_id)
    if not c:
        raise HTTPException(status_code=404, detail="Customer not found")

    if "is_active" not in body:
        raise HTTPException(status_code=422, detail="is_active required")

    c.is_active = bool(body["is_active"])
    if hasattr(c, "updated_at"):
        c.updated_at = datetime.utcnow()

    db.add(c)
    db.commit()
    db.refresh(c)
    return {"id": c.id, "is_active": c.is_active}