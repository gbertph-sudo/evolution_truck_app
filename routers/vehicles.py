from __future__ import annotations

# routers/vehicles.py
# Comentarios en español. Strings en inglés.

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from database import get_db
from models import Customer, User, Vehicle
from schemas import VehicleCreate, VehicleOut
from security import require_roles

router = APIRouter(prefix="/vehicles", tags=["Vehicles"])

VEHICLE_ROLES = ["SUPERADMIN", "ADMIN", "ACCOUNTANT", "VENDEDOR", "MECANICO"]
VEHICLE_ADMIN_ROLES = ["SUPERADMIN", "ADMIN"]


def _norm_str(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    vv = str(v).strip()
    return vv if vv != "" else None


def _norm_vin(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    vv = str(v).strip().upper()
    return vv if vv != "" else None


def _vin_exists(db: Session, vin: str, exclude_vehicle_id: Optional[int] = None) -> bool:
    if not vin:
        return False
    stmt = select(Vehicle.id).where(Vehicle.vin == vin)
    if exclude_vehicle_id:
        stmt = stmt.where(Vehicle.id != exclude_vehicle_id)
    return db.execute(stmt).scalar_one_or_none() is not None


@router.post("", response_model=VehicleOut, status_code=status.HTTP_201_CREATED)
def create_vehicle(
    payload: VehicleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*VEHICLE_ROLES)),
):
    vin = _norm_vin(payload.vin)
    unit_number = _norm_str(payload.unit_number)
    make = _norm_str(payload.make)
    model = _norm_str(payload.model)
    year = payload.year
    customer_id = payload.customer_id

    if customer_id:
        customer = db.get(Customer, customer_id)
        if not customer:
            raise HTTPException(status_code=422, detail="Invalid customer_id")

    if vin and _vin_exists(db, vin):
        raise HTTPException(status_code=409, detail="VIN already exists")

    vehicle = Vehicle(
        vin=vin,
        unit_number=unit_number,
        make=make,
        model=model,
        year=year,
        customer_id=customer_id,
    )

    db.add(vehicle)
    db.commit()
    db.refresh(vehicle)
    return vehicle


@router.get("", response_model=list[VehicleOut])
def list_vehicles(
    q: Optional[str] = Query(default=None),
    customer_id: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*VEHICLE_ROLES)),
):
    stmt = select(Vehicle).order_by(Vehicle.id.asc())

    if customer_id:
        stmt = stmt.where(Vehicle.customer_id == customer_id)

    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Vehicle.vin.ilike(like),
                Vehicle.unit_number.ilike(like),
                Vehicle.make.ilike(like),
                Vehicle.model.ilike(like),
            )
        )

    return list(db.execute(stmt).scalars().all())


@router.get("/{vehicle_id}", response_model=VehicleOut)
def get_vehicle(
    vehicle_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*VEHICLE_ROLES)),
):
    vehicle = db.get(Vehicle, vehicle_id)
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    return vehicle


@router.patch("/{vehicle_id}", response_model=VehicleOut)
def update_vehicle(
    vehicle_id: int,
    payload: VehicleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*VEHICLE_ROLES)),
):
    vehicle = db.get(Vehicle, vehicle_id)
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")

    data = payload.model_dump(exclude_unset=True)

    if "customer_id" in data:
        cid = data.get("customer_id")
        if cid:
            customer = db.get(Customer, cid)
            if not customer:
                raise HTTPException(status_code=422, detail="Invalid customer_id")
        vehicle.customer_id = cid

    if "vin" in data:
        vin = _norm_vin(data.get("vin"))
        if vin and _vin_exists(db, vin, exclude_vehicle_id=vehicle_id):
            raise HTTPException(status_code=409, detail="VIN already exists")
        vehicle.vin = vin

    if "unit_number" in data:
        vehicle.unit_number = _norm_str(data.get("unit_number"))
    if "make" in data:
        vehicle.make = _norm_str(data.get("make"))
    if "model" in data:
        vehicle.model = _norm_str(data.get("model"))
    if "year" in data:
        vehicle.year = data.get("year")

    if hasattr(vehicle, "updated_at"):
        vehicle.updated_at = datetime.utcnow()

    db.add(vehicle)
    db.commit()
    db.refresh(vehicle)
    return vehicle


@router.delete("/{vehicle_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_vehicle(
    vehicle_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*VEHICLE_ADMIN_ROLES)),
):
    vehicle = db.get(Vehicle, vehicle_id)
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")

    db.delete(vehicle)
    db.commit()
    return
