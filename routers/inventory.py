from __future__ import annotations

# routers/inventory.py

from datetime import datetime, date
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, List, Any

from pathlib import Path
from uuid import uuid4
import shutil

from fastapi import APIRouter, Depends, HTTPException, Query, status, Body, UploadFile, File, Form
from sqlalchemy import select, or_
from sqlalchemy.orm import Session

from database import get_db
from models import InventoryItem, InventoryMovement, Supplier, InventoryItemImage, User  # ✅ User para username
from schemas import (
    InventoryItemCreate, InventoryItemUpdate, InventoryItemOut, InventoryItemOutFull,
    SupplierCreate, SupplierUpdate, SupplierOut,
    InventoryItemImageCreate, InventoryItemImageOut,
    InventoryMovementCreate, InventoryMovementOut,
)

from security import require_roles


router = APIRouter(prefix="/inventory", tags=["Inventory"])

ADMIN_ROLES = ["ADMIN", "SUPERADMIN", "ACCOUNTANT"]
# ✅ roles que normalmente pueden usar Inventory (ajusta si tu app usa otros nombres)
INVENTORY_ROLES = ["SUPERADMIN", "ADMIN", "ACCOUNTANT", "VENDEDOR", "MECANICO"]

# ✅ SOLO estos pueden ver MOVEMENTS + activar/desactivar items
MOVEMENTS_ADMIN_ROLES = ["ADMIN", "SUPERADMIN"]

# ✅ DB guarda movement_type en minúsculas (por tu CheckConstraint en models.py)
ALLOWED_MOVEMENT_TYPES = {"in", "out", "adjustment"}

UPLOAD_DIR = Path("static/uploads/inventory")
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
ALLOWED_IMAGE_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


def _ensure_inventory_upload_dir() -> Path:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    return UPLOAD_DIR


def _delete_local_image_file(image_url: Optional[str]) -> None:
    if not image_url:
        return
    prefix = "/static/uploads/inventory/"
    if not str(image_url).startswith(prefix):
        return
    filename = str(image_url).split(prefix, 1)[-1].strip()
    if not filename:
        return
    file_path = UPLOAD_DIR / filename
    try:
        if file_path.exists() and file_path.is_file():
            file_path.unlink()
    except Exception:
        pass


# ======================================================
# HELPERS
# ======================================================

def _to_decimal(value) -> Optional[Decimal]:
    """
    Convierte float/string/Decimal en Decimal seguro.
    Acepta: 12.50 , "12.50" , Decimal("12.50")
    """
    if value is None:
        return None

    try:
        if isinstance(value, Decimal):
            return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except Exception:
        return None


def _weighted_average_cost(old_qty: int, old_cost: Decimal, in_qty: int, in_unit_cost: Decimal) -> Decimal:
    """
    Costo promedio ponderado:
    new_cost = (old_qty*old_cost + in_qty*in_unit_cost) / (old_qty + in_qty)
    """
    denom = old_qty + in_qty

    if denom <= 0:
        return old_cost.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    total = (old_cost * Decimal(old_qty)) + (in_unit_cost * Decimal(in_qty))
    new_cost = total / Decimal(denom)

    return new_cost.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _normalize_movement_type(v: Optional[str]) -> str:
    """
    Normaliza a lo que guarda DB:
      - 'in', 'out', 'adjustment'
    Acepta variantes:
      - IN/OUT/ADJUST
      - adjustment/adjust/adj
    """
    vv = (v or "").strip().lower()

    if vv in {"in"}:
        return "in"
    if vv in {"out"}:
        return "out"
    if vv in {"adjustment", "adjust", "adj", "adjusted", "adjustment "}:
        return "adjustment"
    if vv in {"adjust"}:
        return "adjustment"

    # Si viene "ADJUST" en mayúsculas
    if vv.upper() == "ADJUST":
        return "adjustment"
    if vv.upper() == "IN":
        return "in"
    if vv.upper() == "OUT":
        return "out"

    return vv


def _apply_movement_to_item(
    *,
    item: InventoryItem,
    movement_type: str,
    qty: int,
    unit_cost_raw,
) -> dict:
    """
    Aplica la lógica de stock/costo al item y devuelve:
    {
      "new_qty": int,
      "unit_cost": Optional[Decimal],
      "movement_type": str,   # DB: in/out/adjustment
      "qty": int
    }
    """
    movement_type = _normalize_movement_type(movement_type)

    if movement_type not in ALLOWED_MOVEMENT_TYPES:
        raise HTTPException(status_code=422, detail="movement_type must be: in, out, adjustment")

    if qty is None or int(qty) < 1:
        raise HTTPException(status_code=422, detail="qty must be >= 1")

    # ✅ Bloqueo si item inactivo
    if hasattr(item, "is_active") and item.is_active is False:
        raise HTTPException(status_code=400, detail="Item is inactive")

    qty = int(qty)
    old_qty = int(item.quantity_in_stock or 0)

    unit_cost: Optional[Decimal] = None

    if movement_type == "in":
        unit_cost = _to_decimal(unit_cost_raw)
        if unit_cost is None:
            raise HTTPException(
                status_code=422,
                detail="unit_cost is required and must be numeric for movement_type='in'"
            )
        if unit_cost < 0:
            raise HTTPException(status_code=422, detail="unit_cost cannot be negative")

        old_cost = item.cost_price or Decimal("0.00")
        new_cost = _weighted_average_cost(
            old_qty=old_qty,
            old_cost=old_cost,
            in_qty=qty,
            in_unit_cost=unit_cost
        )

        item.cost_price = new_cost
        item.last_purchase_price = unit_cost
        item.last_purchase_date = date.today()

        new_qty = old_qty + qty

    elif movement_type == "out":
        if old_qty - qty < 0:
            raise HTTPException(status_code=400, detail="Insufficient stock")

        new_qty = old_qty - qty

        item.times_sold = int(item.times_sold or 0) + qty
        item.last_used_date = date.today()

    else:  # adjustment => stock FINAL (conteo físico)
        new_qty = qty

    item.quantity_in_stock = new_qty

    return {
        "new_qty": new_qty,
        "unit_cost": unit_cost,
        "movement_type": movement_type,  # in/out/adjustment
        "qty": qty,
    }


def _parse_iso_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except Exception:
        return None


def _get_role_name(current_user: User) -> str:
    role_name = ""
    if getattr(current_user, "role_name", None):
        role_name = str(current_user.role_name).upper()
    elif getattr(current_user, "role", None) and getattr(current_user.role, "name", None):
        role_name = str(current_user.role.name).upper()
    return role_name


def _is_movements_admin(current_user: User) -> bool:
    return _get_role_name(current_user) in MOVEMENTS_ADMIN_ROLES


# ======================================================
# SUPPLIERS
# ======================================================

@router.post("/suppliers", response_model=SupplierOut, status_code=status.HTTP_201_CREATED)
def create_supplier(payload: SupplierCreate, db: Session = Depends(get_db)):
    name = (payload.name or "").strip()

    if not name:
        raise HTTPException(status_code=422, detail="Supplier name is required")

    exists_stmt = select(Supplier.id).where(
        Supplier.name == name,
        Supplier.deleted_at.is_(None)
    )

    if db.execute(exists_stmt).scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Supplier already exists")

    supplier = Supplier(**payload.model_dump())
    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    return supplier


@router.get("/suppliers", response_model=list[SupplierOut])
def list_suppliers(db: Session = Depends(get_db)):
    stmt = select(Supplier).where(
        Supplier.deleted_at.is_(None)
    ).order_by(Supplier.name.asc())

    return list(db.execute(stmt).scalars().all())


# ======================================================
# ✅ MOVEMENTS (KARDEX GLOBAL)  <<<<< IMPORTANTE: VA ANTES DE /{item_id}
# ======================================================

@router.get("/movements")
def list_all_movements(
    q: Optional[str] = Query(default=None),
    movement_type: Optional[str] = Query(default=None, description="in | out | adjustment"),
    date_from: Optional[str] = Query(default=None, description="YYYY-MM-DD"),
    date_to: Optional[str] = Query(default=None, description="YYYY-MM-DD"),
    limit: int = Query(default=500, ge=1, le=2000),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MOVEMENTS_ADMIN_ROLES)),  # ✅ SOLO ADMIN/SUPERADMIN
):
    """
    ✅ Endpoint GLOBAL para la pantalla Movements:
    GET /api/inventory/movements
    Devuelve movimientos + info del item + username.
    """

    mt = _normalize_movement_type(movement_type) if movement_type else None
    if mt and mt not in ALLOWED_MOVEMENT_TYPES:
        raise HTTPException(status_code=422, detail="movement_type must be: in, out, adjustment")

    df = _parse_iso_date(date_from)
    dt = _parse_iso_date(date_to)

    # ✅ join item + user (username)
    stmt = (
        select(InventoryMovement, InventoryItem, User)
        .join(InventoryItem, InventoryItem.id == InventoryMovement.item_id)
        .outerjoin(User, User.id == InventoryMovement.user_id)
        .where(InventoryItem.deleted_at.is_(None))
    )

    if mt:
        stmt = stmt.where(InventoryMovement.movement_type == mt)

    if df:
        if hasattr(InventoryMovement, "movement_date"):
            stmt = stmt.where(InventoryMovement.movement_date >= datetime.combine(df, datetime.min.time()))
        else:
            stmt = stmt.where(InventoryMovement.created_at >= datetime.combine(df, datetime.min.time()))

    if dt:
        if hasattr(InventoryMovement, "movement_date"):
            stmt = stmt.where(InventoryMovement.movement_date <= datetime.combine(dt, datetime.max.time()))
        else:
            stmt = stmt.where(InventoryMovement.created_at <= datetime.combine(dt, datetime.max.time()))

    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                InventoryItem.part_code.ilike(like),
                InventoryItem.part_name.ilike(like),
                InventoryMovement.movement_notes.ilike(like),
                User.username.ilike(like),
            )
        )

    stmt = stmt.order_by(InventoryMovement.created_at.desc()).limit(limit)

    rows = db.execute(stmt).all()

    out = []
    for mv, it, u in rows:
        out.append({
            "id": mv.id,
            "item_id": mv.item_id,
            "movement_type": mv.movement_type,  # DB: in/out/adjustment
            "quantity_moved": mv.quantity_moved,
            "unit_cost": getattr(mv, "unit_cost", None),
            "movement_date": getattr(mv, "movement_date", None),
            "created_at": getattr(mv, "created_at", None),
            "movement_notes": getattr(mv, "movement_notes", None),

            "user_id": getattr(mv, "user_id", None),
            "username": (u.username if u else None),

            "part_code": it.part_code,
            "part_name": it.part_name,
        })

    return out


# ======================================================
# ITEMS
# ======================================================

@router.post("", response_model=InventoryItemOut, status_code=status.HTTP_201_CREATED)
def create_item(
    payload: InventoryItemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*INVENTORY_ROLES)),
):
    exists_stmt = select(InventoryItem.id).where(
        InventoryItem.part_code == payload.part_code,
        InventoryItem.deleted_at.is_(None),
    )

    if db.execute(exists_stmt).scalar_one_or_none():
        raise HTTPException(status_code=409, detail="part_code already exists")

    data = payload.model_dump()
    cost = _to_decimal(data.get("cost_price")) or Decimal("0.00")
    markup = _to_decimal(data.get("markup_percent")) or Decimal("0.00")
    data["sale_price_base"] = (
        cost * (Decimal("1") + (markup / Decimal("100")))
    ).quantize(Decimal("0.01"))
    item = InventoryItem(**data)

    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.patch("/{item_id}", response_model=InventoryItemOut)
def update_item(
    item_id: int,
    payload: InventoryItemUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*INVENTORY_ROLES)),
):
    item = db.get(InventoryItem, item_id)
    if not item or item.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Item not found")

    # ✅ no-admin no puede editar item inactivo
    if hasattr(item, "is_active") and item.is_active is False and not _is_movements_admin(current_user):
        raise HTTPException(status_code=404, detail="Item not found")

    data = payload.model_dump(exclude_unset=True)

    # Seguridad: no permitimos cambiar part_code desde update (tu front ya lo bloquea)
    if "part_code" in data:
        data.pop("part_code", None)

    for k, v in data.items():
        setattr(item, k, v)

    cost = _to_decimal(getattr(item, "cost_price", 0)) or Decimal("0.00")
    markup = _to_decimal(getattr(item, "markup_percent", 0)) or Decimal("0.00")
    item.sale_price_base = (
        cost * (Decimal("1") + (markup / Decimal("100")))
    ).quantize(Decimal("0.01"))

    if hasattr(item, "updated_at"):
        setattr(item, "updated_at", datetime.utcnow())

    db.add(item)
    db.commit()
    db.refresh(item)
    return item


# ✅ ACTIVAR / DESACTIVAR (SOLO ADMIN/SUPERADMIN)
@router.patch("/{item_id}/active")
def toggle_item_active(
    item_id: int,
    body: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MOVEMENTS_ADMIN_ROLES)),
):
    item = db.get(InventoryItem, item_id)
    if not item or item.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Item not found")

    if "is_active" not in body:
        raise HTTPException(status_code=422, detail="is_active required")

    item.is_active = bool(body["is_active"])

    if hasattr(item, "updated_at"):
        setattr(item, "updated_at", datetime.utcnow())

    db.add(item)
    db.commit()
    db.refresh(item)

    return {"id": item.id, "is_active": item.is_active}


@router.get("", response_model=list[InventoryItemOut])
def list_items(
    q: Optional[str] = Query(default=None),
    category: Optional[str] = None,
    brand: Optional[str] = None,
    low_stock: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*INVENTORY_ROLES)),
):
    # ✅ NO admin: solo activos
    # ✅ admin: activos + inactivos (para poder reactivar)
    stmt = select(InventoryItem).where(InventoryItem.deleted_at.is_(None))

    if not _is_movements_admin(current_user):
        stmt = stmt.where(InventoryItem.is_active.is_(True))

    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            (InventoryItem.part_code.ilike(like)) |
            (InventoryItem.part_name.ilike(like)) |
            (InventoryItem.brand.ilike(like)) |
            (InventoryItem.category.ilike(like)) |
            (InventoryItem.sub_category.ilike(like)) |
            (InventoryItem.oem_reference.ilike(like))
        )

    if category:
        stmt = stmt.where(InventoryItem.category == category)

    if brand:
        stmt = stmt.where(InventoryItem.brand == brand)

    if low_stock:
        stmt = stmt.where(
            InventoryItem.quantity_in_stock <= InventoryItem.minimum_stock
        )

    stmt = stmt.order_by(InventoryItem.part_name.asc())
    return list(db.execute(stmt).scalars().all())


# ======================================================
# ✅ ATENCION: /{item_id} DEBE IR DESPUÉS DE /movements
# ======================================================

@router.get("/{item_id}", response_model=InventoryItemOutFull)
def get_item_full(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*INVENTORY_ROLES)),
):
    item = db.get(InventoryItem, item_id)
    if not item or item.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Item not found")

    # ✅ NO admin: si está inactivo -> 404
    if hasattr(item, "is_active") and item.is_active is False and not _is_movements_admin(current_user):
        raise HTTPException(status_code=404, detail="Item not found")

    # ✅ imágenes siempre
    img_stmt = select(InventoryItemImage).where(
        InventoryItemImage.item_id == item_id
    ).order_by(InventoryItemImage.position.asc(), InventoryItemImage.id.asc())
    images = list(db.execute(img_stmt).scalars().all())

    # ✅ movimientos solo ADMIN/SUPERADMIN
    movements = []
    if _is_movements_admin(current_user):
        mov_stmt = select(InventoryMovement).where(
            InventoryMovement.item_id == item_id
        ).order_by(InventoryMovement.created_at.desc())
        movements = list(db.execute(mov_stmt).scalars().all())

    item.movements = movements  # type: ignore[attr-defined]
    item.images = images        # type: ignore[attr-defined]
    return item


# ======================================================
# MOVEMENTS (POR ITEM)
# ======================================================

@router.post("/{item_id}/movements", response_model=InventoryMovementOut, status_code=status.HTTP_201_CREATED)
def create_movement(
    item_id: int,
    payload: InventoryMovementCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*INVENTORY_ROLES)),  # ✅ para saber quién lo hizo
):
    item = db.get(InventoryItem, item_id)
    if not item or item.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Item not found")

    # ✅ Bloqueo si item inactivo
    if hasattr(item, "is_active") and item.is_active is False:
        raise HTTPException(status_code=400, detail="Item is inactive")

    if payload.item_id != item_id:
        raise HTTPException(status_code=422, detail="item_id mismatch (path vs body)")

    applied = _apply_movement_to_item(
        item=item,
        movement_type=payload.movement_type,
        qty=payload.quantity_moved,
        unit_cost_raw=payload.unit_cost,
    )

    # ✅ Si no mandan user_id, usar el usuario logueado
    uid = payload.user_id if payload.user_id is not None else current_user.id

    movement = InventoryMovement(
        item_id=item.id,
        movement_type=applied["movement_type"],       # ✅ DB: in/out/adjustment
        quantity_moved=applied["qty"],                # SIEMPRE positivo
        unit_cost=applied["unit_cost"] if applied["movement_type"] == "in" else None,
        movement_date=payload.movement_date or datetime.utcnow(),
        user_id=uid,                                  # ✅
        related_job_id=payload.related_job_id,
        movement_notes=payload.movement_notes,
    )

    db.add(movement)
    db.add(item)
    db.commit()
    db.refresh(movement)

    return movement


@router.get("/{item_id}/movements", response_model=List[InventoryMovementOut])
def list_item_movements(
    item_id: int,
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MOVEMENTS_ADMIN_ROLES)),  # ✅ SOLO ADMIN/SUPERADMIN
):
    item = db.get(InventoryItem, item_id)
    if not item or item.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Item not found")

    stmt = select(InventoryMovement).where(
        InventoryMovement.item_id == item_id
    ).order_by(InventoryMovement.created_at.desc()).limit(limit)

    return list(db.execute(stmt).scalars().all())


# ======================================================
# STOCK ADJUST (LEGACY ENDPOINT COMPAT)
# Mantengo tu endpoint /{item_id}/adjust (tu inventory.js lo usa)
# ======================================================

@router.post("/{item_id}/adjust", response_model=InventoryItemOut)
def adjust_stock(
    item_id: int,
    body: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*INVENTORY_ROLES)),  # ✅ para saber quién lo hizo
):
    """
    Endpoint compatible con tu front:
    body:
      movement_type: "in" | "out" | "adjustment"
      qty: int
      unit_cost: decimal (solo si in)
      notes: str
    """
    item = db.get(InventoryItem, item_id)

    if not item or item.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Item not found")

    # ✅ Bloqueo si item inactivo
    if hasattr(item, "is_active") and item.is_active is False:
        raise HTTPException(status_code=400, detail="Item is inactive")

    movement_type_raw = body.get("movement_type")
    qty = body.get("qty")
    notes = body.get("notes")
    unit_cost_raw = body.get("unit_cost")

    mt = _normalize_movement_type(movement_type_raw)

    if mt not in ALLOWED_MOVEMENT_TYPES:
        raise HTTPException(status_code=422, detail="movement_type must be: in, out, adjustment")

    applied = _apply_movement_to_item(
        item=item,
        movement_type=mt,
        qty=qty,
        unit_cost_raw=unit_cost_raw,
    )

    movement = InventoryMovement(
        item_id=item.id,
        movement_type=applied["movement_type"],  # ✅ DB: in/out/adjustment
        quantity_moved=applied["qty"],           # SIEMPRE positivo
        unit_cost=applied["unit_cost"] if applied["movement_type"] == "in" else None,
        movement_date=datetime.utcnow(),
        movement_notes=notes,
        user_id=current_user.id,                 # ✅ QUIÉN LO HIZO
    )

    db.add(movement)
    db.add(item)
    db.commit()
    db.refresh(item)

    return item


# ======================================================
# IMAGES (para tu modal Photos en inventory.js)
# ======================================================

@router.get("/{item_id}/images", response_model=List[InventoryItemImageOut])
def list_images(item_id: int, db: Session = Depends(get_db)):
    item = db.get(InventoryItem, item_id)
    if not item or item.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Item not found")

    stmt = select(InventoryItemImage).where(
        InventoryItemImage.item_id == item_id
    ).order_by(InventoryItemImage.position.asc(), InventoryItemImage.id.asc())

    return list(db.execute(stmt).scalars().all())


@router.post("/{item_id}/images/upload", response_model=InventoryItemImageOut, status_code=status.HTTP_201_CREATED)
def upload_image(
    item_id: int,
    file: UploadFile = File(...),
    is_primary: bool = Form(False),
    alt_text: Optional[str] = Form(None),
    position: int = Form(0),
    db: Session = Depends(get_db),
):
    item = db.get(InventoryItem, item_id)
    if not item or item.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Item not found")

    if not file or not file.filename:
        raise HTTPException(status_code=422, detail="Image file is required")

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise HTTPException(status_code=422, detail="Allowed image types: jpg, jpeg, png, webp, gif")

    content_type = (file.content_type or "").lower()
    if content_type and content_type not in ALLOWED_IMAGE_CONTENT_TYPES:
        raise HTTPException(status_code=422, detail="Invalid image content type")

    upload_dir = _ensure_inventory_upload_dir()
    safe_name = f"item_{item_id}_{uuid4().hex}{ext}"
    saved_path = upload_dir / safe_name

    try:
        with saved_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception:
        raise HTTPException(status_code=500, detail="Could not save image file")
    finally:
        file.file.close()

    image_url = f"/static/uploads/inventory/{safe_name}"

    if is_primary:
        stmt = select(InventoryItemImage).where(InventoryItemImage.item_id == item_id)
        imgs = list(db.execute(stmt).scalars().all())
        for im in imgs:
            im.is_primary = False
            db.add(im)

    img = InventoryItemImage(
        item_id=item_id,
        image_url=image_url,
        position=position or 0,
        is_primary=bool(is_primary),
        alt_text=(alt_text or None),
        created_at=datetime.utcnow() if hasattr(InventoryItemImage, "created_at") else None,
    )

    db.add(img)
    db.commit()
    db.refresh(img)
    return img


@router.post("/{item_id}/images", response_model=InventoryItemImageOut, status_code=status.HTTP_201_CREATED)
def add_image(item_id: int, payload: InventoryItemImageCreate, db: Session = Depends(get_db)):
    item = db.get(InventoryItem, item_id)
    if not item or item.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Item not found")

    # Si es primary, desmarcar otras
    if payload.is_primary:
        stmt = select(InventoryItemImage).where(InventoryItemImage.item_id == item_id)
        imgs = list(db.execute(stmt).scalars().all())
        for im in imgs:
            im.is_primary = False
            db.add(im)

    img = InventoryItemImage(
        item_id=item_id,
        image_url=payload.image_url,
        position=payload.position or 0,
        is_primary=bool(payload.is_primary),
        alt_text=payload.alt_text,
        created_at=datetime.utcnow() if hasattr(InventoryItemImage, "created_at") else None,
    )

    db.add(img)
    db.commit()
    db.refresh(img)
    return img


@router.delete("/images/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_image(image_id: int, db: Session = Depends(get_db)):
    img = db.get(InventoryItemImage, image_id)
    if not img:
        raise HTTPException(status_code=404, detail="Image not found")

    image_url = img.image_url
    db.delete(img)
    db.commit()
    _delete_local_image_file(image_url)
    return