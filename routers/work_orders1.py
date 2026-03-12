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
from reportlab.lib.pagesizes import letter
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
    subtotal = _q2(invoice.subtotal if invoice else sum((_q2(i.line_total) for i in (wo.items or [])), Decimal("0.00")) + sum((_q2(l.line_total) for l in (wo.labors or [])), Decimal("0.00")))
    tax = _q2(invoice.tax if invoice else subtotal * Decimal("0.07"))
    total = _q2(invoice.total if invoice else subtotal + tax)

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    width, height = letter

    left = 0.45 * inch
    right = width - 0.45 * inch
    top = height - 0.45 * inch
    y = top

    def money(v):
        return f"${float(_q2(v or Decimal('0.00'))):,.2f}"

    def draw_box(x, y_top, w, h, stroke=colors.black, fill=None, lw=1):
        c.setLineWidth(lw)
        c.setStrokeColor(stroke)
        if fill is not None:
            c.setFillColor(fill)
            c.rect(x, y_top - h, w, h, stroke=1, fill=1)
            c.setFillColor(colors.black)
        else:
            c.rect(x, y_top - h, w, h, stroke=1, fill=0)

    def draw_wrapped(x, y_top, text_value, width_chars=34, leading=10, font="Helvetica", size=8):
        c.setFont(font, size)
        yy = y_top
        for line in textwrap.wrap(str(text_value or "-"), width=width_chars):
            c.drawString(x, yy, line)
            yy -= leading
        return yy

    def ensure_space(required=1.35 * inch):
        nonlocal y
        if y < required:
            c.showPage()
            y = top

    # Header
    header_h = 1.55 * inch
    draw_box(left, y, right - left, header_h, lw=1.2)

    logo_path_final = (logo_path or LOGO_PATH_DEFAULT).strip()
    logo_x = left + 0.14 * inch
    logo_y = y - 0.16 * inch
    if logo_path_final and os.path.exists(logo_path_final):
        try:
            c.drawImage(logo_path_final, logo_x, y - 1.02 * inch, width=1.15 * inch, height=0.9 * inch, mask="auto")
        except Exception:
            pass

    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString((left + right) / 2, y - 0.38 * inch, company_name)
    c.setFont("Helvetica", 9)
    c.drawCentredString((left + right) / 2, y - 0.58 * inch, company_addr_1)
    c.drawCentredString((left + right) / 2, y - 0.73 * inch, company_addr_2)
    c.drawCentredString((left + right) / 2, y - 0.88 * inch, company_phone)

    info_w = 2.15 * inch
    info_x = right - info_w - 0.12 * inch
    draw_box(info_x, y - 0.10 * inch, info_w, 1.15 * inch, lw=1)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(info_x + 0.10 * inch, y - 0.28 * inch, "WORK ORDER / INVOICE")
    c.setFont("Helvetica", 8.5)
    c.drawString(info_x + 0.10 * inch, y - 0.48 * inch, f"WO: {wo.work_order_number or f'WO-{wo.id:06d}'}")
    c.drawString(info_x + 0.10 * inch, y - 0.63 * inch, f"Invoice: {invoice.invoice_number if invoice else '-'}")
    c.drawString(info_x + 0.10 * inch, y - 0.78 * inch, f"Date: {wo.created_at.strftime('%m/%d/%Y %I:%M %p') if wo.created_at else '-'}")
    c.drawString(info_x + 0.10 * inch, y - 0.93 * inch, f"Status: {wo.status or '-'}")

    y -= header_h + 0.12 * inch

    # Bill To / Ship To
    bill_h = 0.95 * inch
    mid = left + (right - left) / 2
    draw_box(left, y, mid - left - 0.05 * inch, bill_h)
    draw_box(mid + 0.05 * inch, y, right - (mid + 0.05 * inch), bill_h)

    c.setFont("Helvetica-Bold", 10)
    c.drawString(left + 0.10 * inch, y - 0.18 * inch, "Bill To:")
    c.drawString(mid + 0.15 * inch, y - 0.18 * inch, "Vehicle / Service:")
    c.setFont("Helvetica", 8.5)

    cust_name = wo.customer.name if wo.customer else "-"
    cust_phone = wo.customer.phone if wo.customer and wo.customer.phone else ""
    cust_email = wo.customer.email if wo.customer and wo.customer.email else ""
    ship_lines = [
        cust_name,
        company_name if wo.company else "",
        cust_phone,
        cust_email,
    ]
    yy = y - 0.35 * inch
    for line in [cust_name, cust_phone, cust_email]:
        if line:
            c.drawString(left + 0.10 * inch, yy, str(line))
            yy -= 0.15 * inch

    vehicle_txt = f"{(wo.vehicle.year or '') if wo.vehicle else ''} {(wo.vehicle.make or '') if wo.vehicle else ''} {(wo.vehicle.model or '') if wo.vehicle else ''}".strip() or "-"
    c.drawString(mid + 0.15 * inch, y - 0.35 * inch, f"Vehicle: {vehicle_txt}")
    c.drawString(mid + 0.15 * inch, y - 0.50 * inch, f"Unit: {wo.vehicle.unit_number if wo.vehicle and wo.vehicle.unit_number else '-'}")
    c.drawString(mid + 0.15 * inch, y - 0.65 * inch, f"VIN: {wo.vehicle.vin if wo.vehicle and wo.vehicle.vin else '-'}")
    mech_name = (wo.mechanic.full_name or wo.mechanic.username) if wo.mechanic else "-"
    c.drawString(mid + 0.15 * inch, y - 0.80 * inch, f"Mechanic: {mech_name}")

    y -= bill_h + 0.12 * inch

    # Description / notes box
    desc_h = 0.95 * inch
    draw_box(left, y, right - left, desc_h)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(left + 0.10 * inch, y - 0.18 * inch, "Job Description / Notes")
    c.setFont("Helvetica", 8.5)
    desc = (wo.description or "").strip() or "-"
    yy = y - 0.36 * inch
    for line in textwrap.wrap(desc, width=110)[:4]:
        c.drawString(left + 0.10 * inch, yy, line)
        yy -= 0.14 * inch

    y -= desc_h + 0.15 * inch

    # Parts table
    c.setFont("Helvetica-Bold", 10)
    c.drawString(left, y, "PARTS DETAIL")
    y -= 0.10 * inch

    cols = {
        "desc": left + 0.10 * inch,
        "qty": right - 2.35 * inch,
        "unit": right - 1.50 * inch,
        "total": right - 0.12 * inch,
    }
    row_h = 0.23 * inch
    table_w = right - left
    draw_box(left, y, table_w, row_h, fill=colors.lightgrey)
    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(cols["desc"], y - 0.16 * inch, "Description / Ref Number")
    c.drawRightString(cols["qty"], y - 0.16 * inch, "Qty")
    c.drawRightString(cols["unit"], y - 0.16 * inch, "Price")
    c.drawRightString(cols["total"], y - 0.16 * inch, "Ext Price")
    y -= row_h

    parts_total = Decimal("0.00")
    parts = list(wo.items or [])
    if not parts:
        draw_box(left, y, table_w, row_h)
        c.setFont("Helvetica", 8.5)
        c.drawString(left + 0.10 * inch, y - 0.16 * inch, "No parts added")
        y -= row_h
    else:
        for it in parts[:10]:
            ensure_space(2.25 * inch)
            draw_box(left, y, table_w, row_h)
            c.setFont("Helvetica", 8)
            desc_line = (it.description_snapshot or "-")[:55]
            c.drawString(cols["desc"], y - 0.16 * inch, desc_line)
            c.drawRightString(cols["qty"], y - 0.16 * inch, f"{float(it.qty or 0):g}")
            c.drawRightString(cols["unit"], y - 0.16 * inch, money(it.unit_price_snapshot))
            c.drawRightString(cols["total"], y - 0.16 * inch, money(it.line_total))
            parts_total += _q2(it.line_total)
            y -= row_h

    y -= 0.12 * inch

    # Labor table
    c.setFont("Helvetica-Bold", 10)
    c.drawString(left, y, "LABOR DETAIL")
    y -= 0.10 * inch
    draw_box(left, y, table_w, row_h, fill=colors.lightgrey)
    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(cols["desc"], y - 0.16 * inch, "Description")
    c.drawRightString(right - 2.35 * inch, y - 0.16 * inch, "Hours")
    c.drawRightString(right - 1.50 * inch, y - 0.16 * inch, "Rate")
    c.drawRightString(cols["total"], y - 0.16 * inch, "Price")
    y -= row_h

    labor_total = Decimal("0.00")
    labors = list(wo.labors or [])
    if not labors:
        draw_box(left, y, table_w, row_h)
        c.setFont("Helvetica", 8.5)
        c.drawString(left + 0.10 * inch, y - 0.16 * inch, "No labor added")
        y -= row_h
    else:
        for lb in labors[:10]:
            ensure_space(1.8 * inch)
            draw_box(left, y, table_w, row_h)
            c.setFont("Helvetica", 8)
            c.drawString(cols["desc"], y - 0.16 * inch, (lb.description or "-")[:55])
            c.drawRightString(right - 2.35 * inch, y - 0.16 * inch, f"{float(lb.hours or 0):g}")
            c.drawRightString(right - 1.50 * inch, y - 0.16 * inch, money(lb.rate))
            c.drawRightString(cols["total"], y - 0.16 * inch, money(lb.line_total))
            labor_total += _q2(lb.line_total)
            y -= row_h

    y -= 0.14 * inch

    # Bottom notes + totals
    notes_w = 4.75 * inch
    notes_h = 1.45 * inch
    totals_w = (right - left) - notes_w - 0.10 * inch
    draw_box(left, y, notes_w, notes_h)
    draw_box(left + notes_w + 0.10 * inch, y, totals_w, notes_h)

    c.setFont("Helvetica-Bold", 9)
    c.drawString(left + 0.10 * inch, y - 0.18 * inch, "Terms / Notes")
    c.setFont("Helvetica", 7.6)
    notes_text = [
        "NO RETURNS OR CHANGES ON WARRANTIES, ELECTRIC PARTS, OIL, FLUIDS AND VALVES.",
        "NO RETURNS OF ANY PART AFTER 3 DAYS OF THE PURCHASE DATE.",
        "NO RETURNS, EXCHANGES, OR WARRANTIES WITHOUT THE INVOICE.",
        "NO RETURNS OR EXCHANGES ON SPECIAL ORDERS.",
        "20 % RESTOCKING FEE WILL BE CHARGED ON ALL RETURNED PARTS.",
        "THE CORES MUST BE RETURNED BEFORE 6 MONTHS.",
        "I ACCEPT THE RETURN POLICY. SIGNATURE: __________________________",
    ]
    yy = y - 0.36 * inch
    for line in notes_text:
        c.drawString(left + 0.10 * inch, yy, line)
        yy -= 0.14 * inch

    tx = left + notes_w + 0.20 * inch
    c.setFont("Helvetica-Bold", 9)
    c.drawString(tx, y - 0.22 * inch, "Parts:")
    c.drawRightString(right - 0.12 * inch, y - 0.22 * inch, money(parts_total))
    c.drawString(tx, y - 0.42 * inch, "Labor:")
    c.drawRightString(right - 0.12 * inch, y - 0.42 * inch, money(labor_total))
    c.drawString(tx, y - 0.62 * inch, "Sub Total:")
    c.drawRightString(right - 0.12 * inch, y - 0.62 * inch, money(subtotal))
    c.drawString(tx, y - 0.82 * inch, "Tax 7%:")
    c.drawRightString(right - 0.12 * inch, y - 0.82 * inch, money(tax))
    c.setFont("Helvetica-Bold", 11)
    c.drawString(tx, y - 1.10 * inch, "Total:")
    c.drawRightString(right - 0.12 * inch, y - 1.10 * inch, money(total))

    # Footer/signatures
    c.setFont("Helvetica", 8)
    c.line(left, 0.90 * inch, left + 2.6 * inch, 0.90 * inch)
    c.drawString(left, 0.74 * inch, "Customer Signature")
    c.line(right - 2.6 * inch, 0.90 * inch, right, 0.90 * inch)
    c.drawString(right - 2.6 * inch, 0.74 * inch, "Authorized Signature")
    c.setFont("Helvetica-Oblique", 7.5)
    c.drawCentredString(width / 2, 0.48 * inch, "Generated by Evolution Truck System")

    c.showPage()
    c.save()
    buf.seek(0)
    filename = f"{wo.work_order_number or f'WO-{wo.id}'}.pdf"
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )
