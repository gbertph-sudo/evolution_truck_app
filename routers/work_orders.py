from __future__ import annotations

# routers/work_orders.py
# Comentarios en español. Nombres/strings en inglés.

import os
from io import BytesIO
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional
import textwrap

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import select, desc

from database import get_db
from models import (
    WorkOrder, Customer, Company, Vehicle, User,
    Invoice, InvoiceItem,
    WorkOrderItem, WorkOrderLabor, InventoryItem, InventoryMovement
)

from schemas import (
    WorkOrderCreate,
    WorkOrderUpdate,
    WorkOrderOut,
    WorkOrderStatusUpdate,
    WorkOrderItemAdd,
    WorkOrderItemUpdate,
    WorkOrderItemPriceUpdate,
    WorkOrderLaborCreate,
    WorkOrderLaborUpdate,
)

# PDF (ReportLab)
from reportlab.lib.pagesizes import letter, landscape
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.lib import colors


router = APIRouter(tags=["Work Orders"])

LOGO_PATH_DEFAULT = "static/img/logo.png"

ALLOWED_STATUS = {"OPEN", "IN_PROGRESS", "DONE", "CANCELLED"}
ALLOWED_INVOICE_STATUS = {"DRAFT", "SENT", "PAID", "VOID"}


# -------------------------------
# Helpers
# -------------------------------
def _normalize_status(status: str) -> str:
    vv = (status or "").strip().upper()
    if vv not in ALLOWED_STATUS:
        raise HTTPException(status_code=422, detail=f"Invalid status. Use: {', '.join(sorted(ALLOWED_STATUS))}")
    return vv


def _load_work_order(db: Session, work_order_id: int) -> WorkOrder:
    stmt = (
        select(WorkOrder)
        .where(WorkOrder.id == work_order_id)
        .options(
            joinedload(WorkOrder.customer),
            joinedload(WorkOrder.company),
            joinedload(WorkOrder.vehicle),
            joinedload(WorkOrder.mechanic),

            # ✅ invoice
            joinedload(WorkOrder.invoice).joinedload(Invoice.items),

            # ✅ carrito de piezas
            joinedload(WorkOrder.items),
            joinedload(WorkOrder.labors),
        )
    )
    wo = db.execute(stmt).unique().scalars().first()
    if not wo:
        raise HTTPException(status_code=404, detail="Work order not found")
    return wo


def _ensure_company_belongs_to_customer(db: Session, customer_id: int, company_id: int) -> None:
    cust = db.get(Customer, customer_id)
    if not cust:
        raise HTTPException(status_code=404, detail="Customer not found")

    ok = any(c.id == company_id for c in (cust.companies or []))
    if not ok:
        raise HTTPException(
            status_code=422,
            detail="company_id is not linked to the selected customer. Link it first or select a valid company."
        )


def _ensure_vehicle_belongs_to_customer(db: Session, customer_id: int, vehicle_id: int) -> None:
    veh = db.get(Vehicle, vehicle_id)
    if not veh:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    if veh.customer_id is not None and veh.customer_id != customer_id:
        raise HTTPException(status_code=422, detail="vehicle_id does not belong to the selected customer")


def _format_wo_number(wo_id: int) -> str:
    return f"WO-{wo_id:06d}"


def _format_invoice_number(inv_id: int) -> str:
    return f"INV-{inv_id:06d}"


def _q2(val: Decimal) -> Decimal:
    return (val or Decimal("0.00")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

def _calc_markup_unit(cost: Decimal, markup_percent: Optional[Decimal]) -> Decimal:
    cost = _q2(cost or Decimal("0.00"))
    if markup_percent is None:
        return cost
    pct = Decimal(str(markup_percent))
    return _q2(cost + (cost * pct / Decimal("100")))


def _to_int_qty(qty: Decimal) -> int:
    """
    Tu inventario quantity_in_stock es INT.
    Para no romper, aquí forzamos cantidades enteras (1,2,3...).
    """
    if qty is None:
        raise HTTPException(status_code=422, detail="qty is required")
    if qty <= 0:
        raise HTTPException(status_code=422, detail="qty must be > 0")

    # si te mandan 1.00 ok; si te mandan 1.5 lo bloqueamos
    if qty != qty.to_integral_value(rounding=ROUND_HALF_UP):
        raise HTTPException(status_code=422, detail="qty must be a whole number (1,2,3...)")
    qty_int = int(qty)
    if qty_int <= 0:
        raise HTTPException(status_code=422, detail="qty must be >= 1")
    return qty_int


def _ensure_wo_open(wo: WorkOrder) -> None:
    if wo.status in ("DONE", "CANCELLED"):
        raise HTTPException(status_code=422, detail="This work order is closed/cancelled. Cannot modify items.")


# -------------------------------
# Endpoints (Work Orders)
# -------------------------------
@router.get("/work-orders")
def list_work_orders(
    q: Optional[str] = Query(default=None, description="Search in description"),
    status: Optional[str] = Query(default=None, description="OPEN, IN_PROGRESS, DONE, CANCELLED"),
    customer_id: Optional[int] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    stmt = select(WorkOrder).options(
        joinedload(WorkOrder.customer),
        joinedload(WorkOrder.company),
        joinedload(WorkOrder.vehicle),
        joinedload(WorkOrder.mechanic),
    )

    if q:
        stmt = stmt.where(WorkOrder.description.ilike(f"%{q.strip()}%"))

    if status:
        stmt = stmt.where(WorkOrder.status == _normalize_status(status))

    if customer_id:
        stmt = stmt.where(WorkOrder.customer_id == customer_id)

    stmt = stmt.order_by(desc(WorkOrder.created_at)).limit(limit)

    rows = db.execute(stmt).scalars().all()

    out = []
    for wo in rows:
        out.append({
            "id": wo.id,
            "work_order_number": wo.work_order_number,
            "description": wo.description,
            "status": wo.status,
            "created_at": wo.created_at.isoformat() if wo.created_at else None,
            "customer_id": wo.customer_id,
            "company_id": wo.company_id,
            "vehicle_id": wo.vehicle_id,
            "mechanic_id": wo.mechanic_id,
            "customer": (
                {
                    "id": wo.customer.id,
                    "name": wo.customer.name,
                    "phone": wo.customer.phone,
                    "email": wo.customer.email,
                    "is_active": getattr(wo.customer, "is_active", True),
                } if wo.customer else None
            ),
            "company": (
                {
                    "id": wo.company.id,
                    "name": wo.company.name,
                    "is_active": getattr(wo.company, "is_active", True),
                } if wo.company else None
            ),
            "vehicle": (
                {
                    "id": wo.vehicle.id,
                    "vin": wo.vehicle.vin,
                    "unit_number": wo.vehicle.unit_number,
                    "make": wo.vehicle.make,
                    "model": wo.vehicle.model,
                    "year": wo.vehicle.year,
                    "customer_id": wo.vehicle.customer_id,
                    "is_active": getattr(wo.vehicle, "is_active", True),
                } if wo.vehicle else None
            ),
            "mechanic": (
                {
                    "id": wo.mechanic.id,
                    "username": wo.mechanic.username,
                    "full_name": wo.mechanic.full_name,
                    "email": wo.mechanic.email,
                    "is_active": getattr(wo.mechanic, "is_active", True),
                } if wo.mechanic else None
            ),
        })
    return out


@router.get("/work-orders/{work_order_id}", response_model=WorkOrderOut)
def get_work_order(
    work_order_id: int,
    db: Session = Depends(get_db),
):
    wo = _load_work_order(db, work_order_id)
    return wo


@router.post("/work-orders", response_model=WorkOrderOut, status_code=201)
def create_work_order(
    payload: WorkOrderCreate,
    db: Session = Depends(get_db),
):
    status = _normalize_status(payload.status or "OPEN")

    if payload.customer_id and payload.company_id:
        _ensure_company_belongs_to_customer(db, payload.customer_id, payload.company_id)

    if payload.customer_id and payload.vehicle_id:
        _ensure_vehicle_belongs_to_customer(db, payload.customer_id, payload.vehicle_id)

    wo = WorkOrder(
        description=payload.description.strip(),
        status=status,
        customer_id=payload.customer_id,
        company_id=payload.company_id,
        vehicle_id=payload.vehicle_id,
        mechanic_id=payload.mechanic_id,
    )

    db.add(wo)
    db.flush()  # obtiene wo.id sin commit

    wo.work_order_number = _format_wo_number(wo.id)

    db.commit()
    wo = _load_work_order(db, wo.id)
    return wo


@router.patch("/work-orders/{work_order_id}", response_model=WorkOrderOut)
def update_work_order(
    work_order_id: int,
    payload: WorkOrderUpdate,
    db: Session = Depends(get_db),
):
    wo = db.get(WorkOrder, work_order_id)
    if not wo:
        raise HTTPException(status_code=404, detail="Work order not found")

    if payload.status is not None:
        wo.status = _normalize_status(payload.status)

    if payload.description is not None:
        desc_txt = payload.description.strip()
        if desc_txt == "":
            raise HTTPException(status_code=422, detail="description cannot be empty")
        wo.description = desc_txt

    if payload.customer_id is not None:
        wo.customer_id = payload.customer_id

    if payload.company_id is not None:
        wo.company_id = payload.company_id

    if payload.vehicle_id is not None:
        wo.vehicle_id = payload.vehicle_id

    if payload.mechanic_id is not None:
        wo.mechanic_id = payload.mechanic_id

    if wo.customer_id and wo.company_id:
        _ensure_company_belongs_to_customer(db, wo.customer_id, wo.company_id)

    if wo.customer_id and wo.vehicle_id:
        _ensure_vehicle_belongs_to_customer(db, wo.customer_id, wo.vehicle_id)

    db.commit()

    wo = _load_work_order(db, work_order_id)
    return wo


@router.put("/work-orders/{work_order_id}/status", response_model=WorkOrderOut)
def update_work_order_status(
    work_order_id: int,
    payload: WorkOrderStatusUpdate,
    db: Session = Depends(get_db),
):
    wo = db.get(WorkOrder, work_order_id)
    if not wo:
        raise HTTPException(status_code=404, detail="Work order not found")

    wo.status = _normalize_status(payload.status)
    db.commit()

    wo = _load_work_order(db, work_order_id)
    return wo


# -------------------------------
# Endpoints (Work Order Items = Parts Cart)
# -------------------------------
@router.post("/work-orders/{work_order_id}/items", response_model=WorkOrderOut, status_code=201)
def add_work_order_item(
    work_order_id: int,
    payload: WorkOrderItemAdd,
    db: Session = Depends(get_db),
):
    wo = db.get(WorkOrder, work_order_id)
    if not wo:
        raise HTTPException(status_code=404, detail="Work order not found")
    _ensure_wo_open(wo)

    inv = db.get(InventoryItem, payload.inventory_item_id)
    if not inv or not inv.is_active:
        raise HTTPException(status_code=404, detail="Inventory item not found")

    qty_int = _to_int_qty(payload.qty)

    if inv.quantity_in_stock < qty_int:
        raise HTTPException(status_code=422, detail=f"Insufficient stock. On hand: {inv.quantity_in_stock}")

    desc_snapshot = (inv.part_name or "").strip() or f"Item #{inv.id}"
    cost_snapshot = _q2(inv.cost_price or Decimal("0.00"))
    if payload.unit_price is not None:
        unit_price = _q2(payload.unit_price)
    elif payload.markup_percent is not None:
        unit_price = _calc_markup_unit(cost_snapshot, payload.markup_percent)
    else:
        unit_price = _q2(inv.sale_price_base or Decimal("0.00"))
    line_total = _q2(unit_price * Decimal(qty_int))

    # crear línea
    wo_item = WorkOrderItem(
        work_order_id=wo.id,
        inventory_item_id=inv.id,
        description_snapshot=desc_snapshot,
        qty=Decimal(qty_int),
        unit_price_snapshot=_q2(unit_price),
        line_total=line_total,
        cost_snapshot=cost_snapshot,
        added_by_user_id=None,
    )
    db.add(wo_item)

    # descuento stock + movimiento OUT
    inv.quantity_in_stock = inv.quantity_in_stock - qty_int
    mv = InventoryMovement(
        item_id=inv.id,
        movement_type="out",
        quantity_moved=qty_int,
        unit_cost=None,
        user_id=None,
        related_job_id=wo.id,
        movement_notes=f"Used on {wo.work_order_number or wo.id}",
    )
    db.add(mv)

    db.commit()

    wo = _load_work_order(db, work_order_id)
    return wo


@router.patch("/work-orders/{work_order_id}/items/{wo_item_id}", response_model=WorkOrderOut)
def update_work_order_item_qty(
    work_order_id: int,
    wo_item_id: int,
    payload: WorkOrderItemUpdate,
    db: Session = Depends(get_db),
):
    wo = db.get(WorkOrder, work_order_id)
    if not wo:
        raise HTTPException(status_code=404, detail="Work order not found")
    _ensure_wo_open(wo)

    wo_item = db.get(WorkOrderItem, wo_item_id)
    if not wo_item or wo_item.work_order_id != work_order_id:
        raise HTTPException(status_code=404, detail="Work order item not found")

    inv = db.get(InventoryItem, wo_item.inventory_item_id)
    if not inv:
        raise HTTPException(status_code=404, detail="Inventory item not found")

    new_qty_int = _to_int_qty(payload.qty)
    old_qty_int = int(wo_item.qty)

    if new_qty_int == old_qty_int:
        wo = _load_work_order(db, work_order_id)
        return wo

    diff = new_qty_int - old_qty_int  # + = necesita más stock, - = devuelve stock

    if diff > 0:
        if inv.quantity_in_stock < diff:
            raise HTTPException(status_code=422, detail=f"Insufficient stock for increase. On hand: {inv.quantity_in_stock}")
        inv.quantity_in_stock -= diff
        mv = InventoryMovement(
            item_id=inv.id,
            movement_type="out",
            quantity_moved=diff,
            unit_cost=None,
            user_id=None,
            related_job_id=wo.id,
            movement_notes=f"WO qty increase on {wo.work_order_number or wo.id}",
        )
        db.add(mv)
    else:
        give_back = abs(diff)
        inv.quantity_in_stock += give_back
        mv = InventoryMovement(
            item_id=inv.id,
            movement_type="in",
            quantity_moved=give_back,
            unit_cost=None,
            user_id=None,
            related_job_id=wo.id,
            movement_notes=f"WO qty decrease/return on {wo.work_order_number or wo.id}",
        )
        db.add(mv)

    # recalcular línea
    wo_item.qty = Decimal(new_qty_int)
    wo_item.unit_price_snapshot = _q2(wo_item.unit_price_snapshot)
    wo_item.line_total = _q2(wo_item.unit_price_snapshot * Decimal(new_qty_int))

    db.commit()

    wo = _load_work_order(db, work_order_id)
    return wo


@router.patch("/work-orders/{work_order_id}/items/{wo_item_id}/pricing", response_model=WorkOrderOut)
def update_work_order_item_pricing(
    work_order_id: int,
    wo_item_id: int,
    payload: WorkOrderItemPriceUpdate,
    db: Session = Depends(get_db),
):
    wo = db.get(WorkOrder, work_order_id)
    if not wo:
        raise HTTPException(status_code=404, detail="Work order not found")
    _ensure_wo_open(wo)

    wo_item = db.get(WorkOrderItem, wo_item_id)
    if not wo_item or wo_item.work_order_id != work_order_id:
        raise HTTPException(status_code=404, detail="Work order item not found")

    if payload.unit_price is not None:
        unit_price = _q2(payload.unit_price)
    elif payload.markup_percent is not None:
        unit_price = _calc_markup_unit(wo_item.cost_snapshot or Decimal("0.00"), payload.markup_percent)
    else:
        raise HTTPException(status_code=422, detail="unit_price or markup_percent is required")

    wo_item.unit_price_snapshot = unit_price
    wo_item.line_total = _q2(unit_price * wo_item.qty)
    db.commit()
    return _load_work_order(db, work_order_id)


# -------------------------------
# Labor lines
# -------------------------------
@router.post("/work-orders/{work_order_id}/labors", response_model=WorkOrderOut, status_code=201)
def add_work_order_labor(
    work_order_id: int,
    payload: WorkOrderLaborCreate,
    db: Session = Depends(get_db),
):
    wo = db.get(WorkOrder, work_order_id)
    if not wo:
        raise HTTPException(status_code=404, detail="Work order not found")
    _ensure_wo_open(wo)

    desc = (payload.description or "").strip()
    if not desc:
        raise HTTPException(status_code=422, detail="description is required")

    labor = WorkOrderLabor(
        work_order_id=wo.id,
        description=desc,
        hours=_q2(payload.hours),
        rate=_q2(payload.rate),
        line_total=_q2((payload.hours or Decimal("0")) * (payload.rate or Decimal("0"))),
    )
    db.add(labor)
    db.commit()
    return _load_work_order(db, work_order_id)


@router.patch("/work-orders/{work_order_id}/labors/{labor_id}", response_model=WorkOrderOut)
def update_work_order_labor(
    work_order_id: int,
    labor_id: int,
    payload: WorkOrderLaborUpdate,
    db: Session = Depends(get_db),
):
    wo = db.get(WorkOrder, work_order_id)
    if not wo:
        raise HTTPException(status_code=404, detail="Work order not found")
    _ensure_wo_open(wo)

    labor = db.get(WorkOrderLabor, labor_id)
    if not labor or labor.work_order_id != work_order_id:
        raise HTTPException(status_code=404, detail="Labor line not found")

    if payload.description is not None:
        desc = payload.description.strip()
        if not desc:
            raise HTTPException(status_code=422, detail="description cannot be empty")
        labor.description = desc
    if payload.hours is not None:
        labor.hours = _q2(payload.hours)
    if payload.rate is not None:
        labor.rate = _q2(payload.rate)
    labor.line_total = _q2(labor.hours * labor.rate)
    db.commit()
    return _load_work_order(db, work_order_id)


@router.delete("/work-orders/{work_order_id}/labors/{labor_id}", response_model=WorkOrderOut)
def delete_work_order_labor(
    work_order_id: int,
    labor_id: int,
    db: Session = Depends(get_db),
):
    wo = db.get(WorkOrder, work_order_id)
    if not wo:
        raise HTTPException(status_code=404, detail="Work order not found")
    _ensure_wo_open(wo)

    labor = db.get(WorkOrderLabor, labor_id)
    if not labor or labor.work_order_id != work_order_id:
        raise HTTPException(status_code=404, detail="Labor line not found")

    db.delete(labor)
    db.commit()
    return _load_work_order(db, work_order_id)


@router.delete("/work-orders/{work_order_id}/items/{wo_item_id}", response_model=WorkOrderOut)
def delete_work_order_item(
    work_order_id: int,
    wo_item_id: int,
    db: Session = Depends(get_db),
):
    wo = db.get(WorkOrder, work_order_id)
    if not wo:
        raise HTTPException(status_code=404, detail="Work order not found")
    _ensure_wo_open(wo)

    wo_item = db.get(WorkOrderItem, wo_item_id)
    if not wo_item or wo_item.work_order_id != work_order_id:
        raise HTTPException(status_code=404, detail="Work order item not found")

    inv = db.get(InventoryItem, wo_item.inventory_item_id)
    if not inv:
        raise HTTPException(status_code=404, detail="Inventory item not found")

    qty_int = int(wo_item.qty)

    # devolver stock + movimiento IN
    inv.quantity_in_stock += qty_int
    mv = InventoryMovement(
        item_id=inv.id,
        movement_type="in",
        quantity_moved=qty_int,
        unit_cost=None,
        user_id=None,
        related_job_id=wo.id,
        movement_notes=f"Removed from {wo.work_order_number or wo.id}",
    )
    db.add(mv)

    db.delete(wo_item)
    db.commit()

    wo = _load_work_order(db, work_order_id)
    return wo




@router.delete("/work-orders/{work_order_id}")
def delete_work_order(
    work_order_id: int,
    db: Session = Depends(get_db),
):
    wo = db.get(WorkOrder, work_order_id)
    if not wo:
        raise HTTPException(status_code=404, detail="Work order not found")

    if wo.status in ("DONE", "CANCELLED"):
        raise HTTPException(status_code=422, detail="Closed/cancelled work orders cannot be deleted")

    stmt_items = select(WorkOrderItem).where(WorkOrderItem.work_order_id == work_order_id)
    items = db.execute(stmt_items).scalars().all()

    for wo_item in items:
        inv = db.get(InventoryItem, wo_item.inventory_item_id)
        if inv:
            qty_int = int(wo_item.qty or 0)
            if qty_int > 0:
                inv.quantity_in_stock += qty_int
                mv = InventoryMovement(
                    item_id=inv.id,
                    movement_type="in",
                    quantity_moved=qty_int,
                    unit_cost=None,
                    user_id=None,
                    related_job_id=wo.id,
                    movement_notes=f"Work order deleted: return from {wo.work_order_number or wo.id}",
                )
                db.add(mv)

    db.delete(wo)
    db.commit()
    return {"ok": True, "deleted_id": work_order_id}


# -------------------------------
# Create Invoice from Work Order
# -------------------------------
@router.post("/work-orders/{work_order_id}/create-invoice", response_model=WorkOrderOut)
def create_invoice_from_work_order(
    work_order_id: int,
    db: Session = Depends(get_db),
):
    wo = _load_work_order(db, work_order_id)

    inv = wo.invoice
    if inv is None:
        inv = Invoice(
            work_order_id=wo.id,
            customer_id=wo.customer_id,
            status="DRAFT",
            subtotal=Decimal("0.00"),
            tax=Decimal("0.00"),
            total=Decimal("0.00"),
            notes=None,
        )
        db.add(inv)
        db.flush()
        inv.invoice_number = _format_invoice_number(inv.id)
    else:
        for old in list(inv.items or []):
            db.delete(old)
        db.flush()

    subtotal = Decimal("0.00")

    for wo_it in (wo.items or []):
        ii = InvoiceItem(
            invoice_id=inv.id,
            item_type="PART",
            description=wo_it.description_snapshot,
            qty=_q2(wo_it.qty),
            unit_price=_q2(wo_it.unit_price_snapshot),
            line_total=_q2(wo_it.line_total),
            inventory_item_id=wo_it.inventory_item_id,
            work_order_item_id=wo_it.id,
            cost_snapshot=_q2(getattr(wo_it, "cost_snapshot", Decimal("0.00"))),
        )
        subtotal += _q2(ii.line_total)
        db.add(ii)

    for lb in (wo.labors or []):
        ii = InvoiceItem(
            invoice_id=inv.id,
            item_type="LABOR",
            description=lb.description,
            qty=_q2(lb.hours),
            unit_price=_q2(lb.rate),
            line_total=_q2(lb.line_total),
            inventory_item_id=None,
            work_order_item_id=None,
            cost_snapshot=Decimal("0.00"),
        )
        subtotal += _q2(ii.line_total)
        db.add(ii)

    inv.customer_id = wo.customer_id
    inv.subtotal = _q2(subtotal)
    inv.tax = _q2(inv.subtotal * Decimal("0.07"))
    inv.total = _q2(inv.subtotal + inv.tax)

    # close work order automatically when invoice is created
    wo.status = "DONE"

    db.commit()
    return _load_work_order(db, work_order_id)


# -------------------------------
# PDF (se mantiene tu PDF)
# -------------------------------
@router.get("/work-orders/{work_order_id}/pdf")
def work_order_pdf(
    work_order_id: int,
    logo_path: Optional[str] = Query(default=None, description="Optional override logo path"),
    db: Session = Depends(get_db),
):
    wo = _load_work_order(db, work_order_id)

    company_name = "EVOLUTION TRUCK CORP"
    company_addr_1 = "17210 NW 24TH AVE"
    company_addr_2 = "MIAMI GARDENS, FL 33056-4611"
    company_phone = "Phone: 786-899-6360"

    invoice = wo.invoice
    parts_total = sum((_q2(i.line_total) for i in (wo.items or [])), Decimal("0.00"))
    labor_total = sum((_q2(l.line_total) for l in (wo.labors or [])), Decimal("0.00"))
    subtotal = _q2(invoice.subtotal if invoice else (parts_total + labor_total))
    tax = _q2(invoice.tax if invoice else subtotal * Decimal("0.07"))
    total = _q2(invoice.total if invoice else subtotal + tax)

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=landscape(letter))
    width, height = landscape(letter)

    left = 16
    right = width - 16
    top = height - 16

    HEADER_H_FIRST = 198
    HEADER_H_CONT = 34
    HEADER_GAP = 10
    CONT_TABLE_TOP_GAP = 42
    FOOTER_TOP_Y = 132
    FOOTER_SAFE_TOP_Y = 146
    NONLAST_BOTTOM_Y_FIRST = 30
    NONLAST_BOTTOM_Y_CONT = 24
    ROW_H = 17
    TABLE_HEADER_H = 18

    def money(v):
        return f"${float(_q2(v or Decimal('0.00'))):,.2f}"

    def box(x, y_top, w, h, fill=None, lw=1):
        c.setLineWidth(lw)
        c.setStrokeColor(colors.black)
        if fill is not None:
            c.setFillColor(fill)
            c.rect(x, y_top - h, w, h, fill=1, stroke=1)
            c.setFillColor(colors.black)
        else:
            c.rect(x, y_top - h, w, h, fill=0, stroke=1)

    def txt(x, y, s, font="Helvetica", size=8):
        c.setFont(font, size)
        c.drawString(x, y, str(s or ""))

    def txt_right(x, y, s, font="Helvetica", size=8):
        c.setFont(font, size)
        c.drawRightString(x, y, str(s or ""))

    def wrapped(x, y, s, width_chars, leading=10, font="Helvetica", size=8, max_lines=None):
        c.setFont(font, size)
        lines = textwrap.wrap(str(s or ""), width=width_chars) or [""]
        if max_lines is not None:
            lines = lines[:max_lines]
        yy = y
        for line in lines:
            c.drawString(x, yy, line)
            yy -= leading
        return yy

    def draw_top_area():
        y = top
        top_h = HEADER_H_FIRST

        left_w = 250
        center_w = 250
        right_w = (right - left) - left_w - center_w

        # Left info block
        box(left, y, left_w, top_h)
        wrapped(
            left + 6, y - 12,
            "PLEASE READ CAREFULLY. CHECK ONE OF THE STATEMENTS BELOW, AND SIGN:",
            52, leading=9, font="Helvetica-Bold", size=7, max_lines=2
        )
        legal_lines = [
            "I UNDERSTAND THAT, UNDER STATE LAW, AN ESTIMATE TO A WRITTEN",
            "LIMITED TO A WRITTEN ESTIMATE.",
            "MY FINAL BILL EXCEEDS $100:",
            "[] I DO NOT REQUEST A WRITTEN STATEMENT AS",
            "LONG AS THE REPAIR COSTS DO NOT EXCEED THIS LIMIT.",
            "[] I REQUEST AN ORAL APPROVAL.",
            "[] I REQUEST A WRITTEN ESTIMATE.",
        ]
        yy = y - 36
        for line in legal_lines:
            txt(left + 6, yy, line, "Helvetica", 6.8)
            yy -= 10

        label_x = left + 8
        value_x = left + 92
        line_y = y - 106
        row_gap = 12
        data_pairs = [
            ("SIGNED:", ""),
            ("Phone:", wo.customer.phone if wo.customer and wo.customer.phone else ""),
            ("Fax:", ""),
            ("InvDate:", wo.created_at.strftime("%m/%d/%Y") if wo.created_at else ""),
            ("Name:", wo.customer.name if wo.customer else ""),
            ("Address:", company_addr_1),
        ]
        for k, v in data_pairs:
            txt(label_x, line_y, k, "Helvetica-Bold", 7)
            txt(value_x, line_y, v, "Helvetica", 7)
            line_y -= row_gap
        txt(value_x, line_y, company_addr_2, "Helvetica", 7)

        # Center company/vehicle block
        cx = left + left_w
        box(cx, y, center_w, top_h)
        logo_path_final = (logo_path or LOGO_PATH_DEFAULT).strip()
        if logo_path_final and os.path.exists(logo_path_final):
            try:
                c.drawImage(logo_path_final, cx + 72, y - 82, width=96, height=56, mask="auto")
            except Exception:
                pass
        txt(cx + center_w/2 - 70, y - 94, company_name, "Helvetica-Bold", 13)
        txt(cx + center_w/2 - 78, y - 108, company_addr_1, "Helvetica", 7.5)
        txt(cx + center_w/2 - 96, y - 120, company_addr_2, "Helvetica", 7.5)
        txt(cx + center_w/2 - 62, y - 132, company_phone, "Helvetica", 7.5)

        vin_last8 = "-"
        if wo.vehicle and wo.vehicle.vin:
            vin_last8 = str(wo.vehicle.vin)[-8:]

        details = [
            ("Year:", str(wo.vehicle.year) if wo.vehicle and wo.vehicle.year else "-"),
            ("Make:", wo.vehicle.make if wo.vehicle and wo.vehicle.make else "-"),
            ("Model:", wo.vehicle.model if wo.vehicle and wo.vehicle.model else "-"),
            ("VIN#:", vin_last8),
            ("Unit:", wo.vehicle.unit_number if wo.vehicle and wo.vehicle.unit_number else "-"),
            ("Miles out:", ""),
        ]
        lx1 = cx + 8
        lx2 = cx + 132
        dy = y - 146
        for idx, (k, v) in enumerate(details[:3]):
            txt(lx1, dy - idx * 11, k, "Helvetica-Bold", 7)
            txt(lx1 + 36, dy - idx * 11, v, "Helvetica", 7)
        for idx, (k, v) in enumerate(details[3:]):
            txt(lx2, dy - idx * 11, k, "Helvetica-Bold", 7)
            txt(lx2 + 42, dy - idx * 11, v, "Helvetica", 7)

        # Right estimate block
        rx = cx + center_w
        box(rx, y, right_w, top_h)

        label_x = rx + 8
        value_x = rx + 118
        line_h = 10
        yy = y - 16

        simple_rows = [
            ("ESTIMATE/DIAGNOSTIC", ""),
            ("FEE:", ""),
            ("OR/HOURLY on parts and labor", ""),
            ("ESTIMATE", ""),
            ("Proposed Complete Date:", ""),
            ("Warranty:", "No"),
        ]
        for k, v in simple_rows:
            if v:
                txt(label_x, yy, k, "Helvetica-Bold", 6.7)
                txt(value_x, yy, v, "Helvetica", 6.7)
            else:
                txt(label_x, yy, k, "Helvetica", 6.7)
            yy -= line_h

        txt(label_x, yy, "Customer Complaint/Problem:", "Helvetica-Bold", 6.7)
        yy -= 9
        complaint = (wo.description or "").strip()
        complaint_lines = textwrap.wrap(complaint, width=22)[:3] or [""]
        for line in complaint_lines:
            txt(label_x + 6, yy, line, "Helvetica", 6.6)
            yy -= 8

        bottom_rows = [
            ("Labor rate based on:", ""),
            ("DOT rate:", ""),
            ("HOURLY RATE $50.00", ""),
            ("PER DAY MAY BE APPLIED", ""),
            ("NOT CLEAR OF CHARGES", ""),
        ]
        for k, v in bottom_rows:
            if yy < y - top_h + 10:
                break
            if v:
                txt(label_x, yy, k, "Helvetica-Bold", 6.5)
                txt(value_x, yy, v, "Helvetica", 6.5)
            else:
                txt(label_x, yy, k, "Helvetica", 6.5)
            yy -= 9

        return top - top_h - HEADER_GAP

    def draw_continuation_header():
        cont_y = top
        box(left, cont_y, right - left, HEADER_H_CONT)
        txt(left + 8, cont_y - 14, company_name, "Helvetica-Bold", 12)
        txt(left + 8, cont_y - 27, f"WORK ORDER {wo.work_order_number or f'WO-{wo.id:06d}'} - CONTINUATION", "Helvetica-Bold", 9)
        txt_right(right - 8, cont_y - 14, f"Invoice: {invoice.invoice_number if invoice else '-'}", "Helvetica", 8)
        txt_right(right - 8, cont_y - 27, f"Customer: {wo.customer.name if wo.customer else '-'}", "Helvetica", 8)
        return cont_y - CONT_TABLE_TOP_GAP

    def draw_detail_headers(y_top, content_bottom_y):
        bar_w = 18
        detail_h = max(60, y_top - content_bottom_y)

        # Parts
        box(left, y_top, bar_w, detail_h, fill=colors.lightgrey)
        c.saveState()
        c.setFont("Helvetica-Bold", 10)
        c.translate(left + 13, y_top - detail_h + 8)
        c.rotate(90)
        c.drawString(0, 0, "P A R T S   D E T A I L")
        c.restoreState()

        px = left + bar_w
        pw = width - 260 - px
        box(px, y_top, pw, detail_h)
        box(px, y_top, pw, TABLE_HEADER_H, fill=colors.whitesmoke)
        txt(px + 6, y_top - 12, "Part / Misc", "Helvetica-Bold", 7.5)
        txt(px + 110, y_top - 12, "Description / Ref Number", "Helvetica-Bold", 7.5)
        txt_right(px + pw - 135, y_top - 12, "Quantity", "Helvetica-Bold", 7.5)
        txt_right(px + pw - 78, y_top - 12, "Price", "Helvetica-Bold", 7.5)
        txt_right(px + pw - 8, y_top - 12, "Ext Price", "Helvetica-Bold", 7.5)

        # Labor
        lx = px + pw + 8
        lw = right - lx
        box(lx, y_top, bar_w, detail_h, fill=colors.lightgrey)
        c.saveState()
        c.setFont("Helvetica-Bold", 10)
        c.translate(lx + 13, y_top - detail_h + 8)
        c.rotate(90)
        c.drawString(0, 0, "L A B O R   D E T A I L")
        c.restoreState()

        tx = lx + bar_w
        tw = right - tx
        box(tx, y_top, tw, detail_h)
        box(tx, y_top, tw, TABLE_HEADER_H, fill=colors.whitesmoke)
        txt(tx + 8, y_top - 12, "Description", "Helvetica-Bold", 7.5)
        txt_right(tx + tw - 122, y_top - 12, "Hours", "Helvetica-Bold", 7.5)
        txt_right(tx + tw - 64, y_top - 12, "Rate", "Helvetica-Bold", 7.5)
        txt_right(tx + tw - 8, y_top - 12, "Price", "Helvetica-Bold", 7.5)

        usable_h = max(0, detail_h - TABLE_HEADER_H)
        max_rows = max(1, int(usable_h // ROW_H))

        return {
            "parts_x": px,
            "parts_w": pw,
            "labor_x": tx,
            "labor_w": tw,
            "row_h": ROW_H,
            "table_top_y": y_top - TABLE_HEADER_H,
            "max_rows": max_rows,
        }

    def draw_bottom_area():
        y = FOOTER_TOP_Y

        left_note_w = 248
        left_note_h = 88
        box(left, y, left_note_w, left_note_h)
        wrapped(
            left + 6, y - 12,
            "Estimate good for 30 days. Not responsible for damage caused by theft, fire or acts of God. "
            "This charge represents cost and profits to motor vehicles of materials and supplies sold by us and/or furnished by outside suppliers. "
            "Waste disposal sold to customer. Under no circumstances are labor charges returnable.",
            62, leading=8, font="Helvetica", size=6.7, max_lines=9
        )
        txt(left + 6, y - 78, "X _____________________________    Date: ____________", "Helvetica", 7)

        mid_note_x = left + left_note_w + 8
        mid_note_w = 320
        mid_note_h = 88
        box(mid_note_x, y, mid_note_w, mid_note_h)
        wrapped(
            mid_note_x + 6, y - 12,
            "ORIGINAL PARTS HAVE TWELVE (12) MONTHS OF WARRANTY SUBJECT TO INSPECTION FROM MANUFACTURER BEFORE "
            "REPLACEMENT PART IS CREDITED. AFTERMARKET AND REBUILD PARTS HAVE SIX MONTHS (6) OF WARRANTY. "
            "UNDER NO REASON, TURBOS AND CLUTCHES DO NOT HAVE WARRANTY. LABOR CLAIM WILL NOT PROCESSED.",
            82, leading=8, font="Helvetica", size=6.5, max_lines=9
        )

        totals_x = mid_note_x + mid_note_w + 8
        totals_w = right - totals_x
        totals_h = 88
        box(totals_x, y, totals_w, totals_h)
        line_y = y - 16
        for label, value in [
            ("Charges:", money(Decimal("0.00"))),
            ("Sublet:", money(Decimal("0.00"))),
            ("Supplies:", money(Decimal("0.00"))),
            ("Sub Total:", money(subtotal)),
            ("Tax:", money(tax)),
            ("Total:", money(total)),
        ]:
            font = "Helvetica-Bold" if label == "Total:" else "Helvetica"
            size = 9 if label == "Total:" else 8.5
            txt(totals_x + 8, line_y, label, font, size)
            txt_right(totals_x + totals_w - 8, line_y, value, font, size)
            line_y -= 12

    def rows_for(y_top, content_bottom_y):
        detail_h = max(60, y_top - content_bottom_y)
        usable_h = max(0, detail_h - TABLE_HEADER_H)
        return max(1, int(usable_h // ROW_H))

    first_table_top_y = top - HEADER_H_FIRST - HEADER_GAP
    cont_table_top_y = top - CONT_TABLE_TOP_GAP

    first_last_cap = rows_for(first_table_top_y, FOOTER_SAFE_TOP_Y)
    first_nonlast_cap = rows_for(first_table_top_y, NONLAST_BOTTOM_Y_FIRST)
    cont_last_cap = rows_for(cont_table_top_y, FOOTER_SAFE_TOP_Y)
    cont_nonlast_cap = rows_for(cont_table_top_y, NONLAST_BOTTOM_Y_CONT)

    def page_caps(page_count: int):
        if page_count <= 1:
            return [first_last_cap]
        return [first_nonlast_cap] + ([cont_nonlast_cap] * (page_count - 2)) + [cont_last_cap]

    parts = list(wo.items or [])
    labors = list(wo.labors or [])

    total_pages = 1
    while True:
        caps = page_caps(total_pages)
        if len(parts) <= sum(caps) and len(labors) <= sum(caps):
            break
        total_pages += 1

    def distribute(items, caps):
        out = []
        idx = 0
        total_items = len(items)
        for cap in caps:
            next_idx = min(total_items, idx + cap)
            out.append(items[idx:next_idx])
            idx = next_idx
        return out

    parts_pages = distribute(parts, page_caps(total_pages))
    labors_pages = distribute(labors, page_caps(total_pages))

    for page_idx in range(total_pages):
        if page_idx > 0:
            c.showPage()

        is_first = page_idx == 0
        is_last = page_idx == total_pages - 1

        if is_first:
            table_y_top = draw_top_area()
            content_bottom_y = FOOTER_SAFE_TOP_Y if is_last else NONLAST_BOTTOM_Y_FIRST
        else:
            table_y_top = draw_continuation_header()
            content_bottom_y = FOOTER_SAFE_TOP_Y if is_last else NONLAST_BOTTOM_Y_CONT

        layout = draw_detail_headers(table_y_top, content_bottom_y)

        page_parts = parts_pages[page_idx] if page_idx < len(parts_pages) else []
        page_labors = labors_pages[page_idx] if page_idx < len(labors_pages) else []

        row_y_parts = layout["table_top_y"]
        row_y_labors = layout["table_top_y"]

        if not page_parts:
            msg = "No parts added" if len(parts) == 0 and is_first else "No additional parts"
            box(layout["parts_x"], row_y_parts, layout["parts_w"], layout["row_h"])
            txt(layout["parts_x"] + 8, row_y_parts - 11, msg, "Helvetica", 8)
        else:
            for it in page_parts:
                box(layout["parts_x"], row_y_parts, layout["parts_w"], layout["row_h"])
                txt(layout["parts_x"] + 6, row_y_parts - 11, str(it.inventory_item_id or ""), "Helvetica", 7)
                txt(layout["parts_x"] + 110, row_y_parts - 11, (it.description_snapshot or "-")[:42], "Helvetica", 7)
                txt_right(layout["parts_x"] + layout["parts_w"] - 135, row_y_parts - 11, f"{float(it.qty or 0):g}", "Helvetica", 7)
                txt_right(layout["parts_x"] + layout["parts_w"] - 78, row_y_parts - 11, money(it.unit_price_snapshot), "Helvetica", 7)
                txt_right(layout["parts_x"] + layout["parts_w"] - 8, row_y_parts - 11, money(it.line_total), "Helvetica", 7)
                row_y_parts -= layout["row_h"]

        if not page_labors:
            msg = "No labor added" if len(labors) == 0 and is_first else "No additional labor"
            box(layout["labor_x"], row_y_labors, layout["labor_w"], layout["row_h"])
            txt(layout["labor_x"] + 8, row_y_labors - 11, msg, "Helvetica", 8)
        else:
            for lb in page_labors:
                box(layout["labor_x"], row_y_labors, layout["labor_w"], layout["row_h"])
                txt(layout["labor_x"] + 8, row_y_labors - 11, (lb.description or "-")[:28], "Helvetica", 7)
                txt_right(layout["labor_x"] + layout["labor_w"] - 122, row_y_labors - 11, f"{float(lb.hours or 0):g}", "Helvetica", 7)
                txt_right(layout["labor_x"] + layout["labor_w"] - 64, row_y_labors - 11, money(lb.rate), "Helvetica", 7)
                txt_right(layout["labor_x"] + layout["labor_w"] - 8, row_y_labors - 11, money(lb.line_total), "Helvetica", 7)
                row_y_labors -= layout["row_h"]

        if is_last:
            draw_bottom_area()

        c.setFont("Helvetica", 7)
        c.drawRightString(right, 10, f"Page {page_idx + 1} of {total_pages}")

    c.save()
    buf.seek(0)
    filename = f"{wo.work_order_number or f'WO-{wo.id}'}.pdf"
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


