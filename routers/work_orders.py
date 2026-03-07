from __future__ import annotations

# routers/work_orders.py
# Comentarios en español. Nombres/strings en inglés.

import os
from io import BytesIO
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import select, desc

from database import get_db
from models import (
    WorkOrder, Customer, Company, Vehicle, User,
    Invoice, InvoiceItem,
    WorkOrderItem, InventoryItem, InventoryMovement
)

from schemas import (
    WorkOrderCreate,
    WorkOrderUpdate,
    WorkOrderOut,
    WorkOrderStatusUpdate,
    WorkOrderItemAdd,
    WorkOrderItemUpdate,
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
        )
    )
    wo = db.execute(stmt).scalars().first()
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
@router.get("/work-orders", response_model=List[WorkOrderOut])
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
    return rows


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
    unit_price = inv.sale_price_base or Decimal("0.00")
    line_total = _q2(unit_price * Decimal(qty_int))

    # crear línea
    wo_item = WorkOrderItem(
        work_order_id=wo.id,
        inventory_item_id=inv.id,
        description_snapshot=desc_snapshot,
        qty=Decimal(qty_int),
        unit_price_snapshot=_q2(unit_price),
        line_total=line_total,
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


# -------------------------------
# Create Invoice from Work Order
# -------------------------------
@router.post("/work-orders/{work_order_id}/create-invoice", response_model=WorkOrderOut)
def create_invoice_from_work_order(
    work_order_id: int,
    db: Session = Depends(get_db),
):
    wo = _load_work_order(db, work_order_id)

    if wo.invoice is not None:
        # ya existe, no duplicar
        return wo

    # Crear invoice
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
    db.flush()  # obtener inv.id

    inv.invoice_number = _format_invoice_number(inv.id)

    subtotal = Decimal("0.00")

    # copiar líneas desde work_order_items
    for wo_it in (wo.items or []):
        # item_type PART
        ii = InvoiceItem(
            invoice_id=inv.id,
            item_type="PART",
            description=wo_it.description_snapshot,
            qty=_q2(wo_it.qty),
            unit_price=_q2(wo_it.unit_price_snapshot),
            line_total=_q2(wo_it.line_total),

            inventory_item_id=wo_it.inventory_item_id,
            work_order_item_id=wo_it.id,
        )
        subtotal += _q2(ii.line_total)
        db.add(ii)

    inv.subtotal = _q2(subtotal)
    inv.tax = Decimal("0.00")
    inv.total = _q2(inv.subtotal + inv.tax)

    # opcional: marcar estado de WO si quieres
    # wo.status = "DONE"

    db.commit()

    wo = _load_work_order(db, work_order_id)
    return wo


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

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    width, height = letter

    left = 0.75 * inch
    right = width - 0.75 * inch
    top = height - 0.75 * inch

    logo_path_final = (logo_path or LOGO_PATH_DEFAULT).strip()
    if logo_path_final and os.path.exists(logo_path_final):
        try:
            c.drawImage(logo_path_final, left, top - 0.9 * inch, width=1.6 * inch, height=0.8 * inch, mask="auto")
        except Exception:
            pass

    c.setFont("Helvetica-Bold", 16)
    c.drawString(left + 1.8 * inch, top - 0.25 * inch, "Evolution Truck - Work Order")

    c.setFont("Helvetica", 10)
    wo_no = wo.work_order_number or f"WO-{wo.id}"
    c.drawRightString(right, top - 0.20 * inch, f"Work Order: {wo_no}")
    c.drawRightString(right, top - 0.40 * inch, f"Date: {wo.created_at.strftime('%Y-%m-%d %H:%M')}")
    c.drawRightString(right, top - 0.60 * inch, f"Status: {wo.status}")

    c.setStrokeColor(colors.black)
    c.setLineWidth(1)
    c.line(left, top - 1.05 * inch, right, top - 1.05 * inch)

    y = top - 1.35 * inch

    def section_title(title: str):
        nonlocal y
        c.setFont("Helvetica-Bold", 11)
        c.drawString(left, y, title)
        y -= 0.18 * inch
        c.setLineWidth(0.5)
        c.setStrokeColor(colors.grey)
        c.line(left, y, right, y)
        y -= 0.20 * inch
        c.setStrokeColor(colors.black)

    def row(label: str, value: str):
        nonlocal y
        c.setFont("Helvetica-Bold", 9)
        c.drawString(left, y, f"{label}:")
        c.setFont("Helvetica", 9)
        c.drawString(left + 1.2 * inch, y, value or "-")
        y -= 0.18 * inch

    section_title("Customer / Company")
    cust_name = wo.customer.name if wo.customer else "-"
    row("Customer", cust_name)
    if wo.customer:
        row("Phone", wo.customer.phone or "-")
        row("Email", wo.customer.email or "-")
    comp_name = wo.company.name if wo.company else "-"
    row("Company", comp_name)

    y -= 0.10 * inch

    section_title("Vehicle")
    if wo.vehicle:
        row("Unit #", wo.vehicle.unit_number or "-")
        row("VIN", wo.vehicle.vin or "-")
        row("Make/Model", f"{wo.vehicle.make or ''} {wo.vehicle.model or ''}".strip() or "-")
        row("Year", str(wo.vehicle.year) if wo.vehicle.year else "-")
    else:
        row("Vehicle", "-")

    y -= 0.10 * inch

    section_title("Work Description")
    c.setFont("Helvetica", 10)
    desc = (wo.description or "").strip() or "-"
    max_width = right - left
    words = desc.split()
    lines = []
    current = ""
    for w in words:
        test = (current + " " + w).strip()
        if c.stringWidth(test, "Helvetica", 10) <= max_width:
            current = test
        else:
            lines.append(current)
            current = w
    if current:
        lines.append(current)

    for ln in lines[:12]:
        c.drawString(left, y, ln)
        y -= 0.18 * inch

    y -= 0.15 * inch

    section_title("Assigned Technician")
    mech = "-"
    if wo.mechanic:
        mech = wo.mechanic.full_name or wo.mechanic.username
    row("Mechanic", mech)

    y -= 0.15 * inch

    if wo.invoice:
        section_title("Invoice Summary")
        inv = wo.invoice

        row("Invoice #", inv.invoice_number or "-")
        row("Invoice Status", inv.status)
        row("Subtotal", f"${float(inv.subtotal):,.2f}")
        row("Tax", f"${float(inv.tax):,.2f}")
        row("Total", f"${float(inv.total):,.2f}")

        y -= 0.10 * inch

        c.setFont("Helvetica-Bold", 9)
        c.drawString(left, y, "Items")
        y -= 0.20 * inch

        c.setFont("Helvetica-Bold", 8)
        c.drawString(left, y, "Type")
        c.drawString(left + 0.8 * inch, y, "Description")
        c.drawRightString(right - 1.4 * inch, y, "Qty")
        c.drawRightString(right - 0.7 * inch, y, "Unit")
        c.drawRightString(right, y, "Total")
        y -= 0.14 * inch
        c.setLineWidth(0.5)
        c.setStrokeColor(colors.grey)
        c.line(left, y, right, y)
        y -= 0.14 * inch
        c.setStrokeColor(colors.black)

        c.setFont("Helvetica", 8)
        for it in inv.items[:12]:
            c.drawString(left, y, (it.item_type or "")[:10])
            c.drawString(left + 0.8 * inch, y, (it.description or "")[:45])
            c.drawRightString(right - 1.4 * inch, y, f"{float(it.qty):g}")
            c.drawRightString(right - 0.7 * inch, y, f"{float(it.unit_price):,.2f}")
            c.drawRightString(right, y, f"{float(it.line_total):,.2f}")
            y -= 0.14 * inch
            if y < 1.2 * inch:
                break

    c.setFont("Helvetica", 9)
    c.setStrokeColor(colors.black)
    c.setLineWidth(0.8)

    c.line(left, 1.1 * inch, left + 2.6 * inch, 1.1 * inch)
    c.drawString(left, 0.9 * inch, "Customer Signature")

    c.line(left + 3.2 * inch, 1.1 * inch, left + 5.8 * inch, 1.1 * inch)
    c.drawString(left + 3.2 * inch, 0.9 * inch, "Technician")

    c.setFont("Helvetica-Oblique", 8)
    c.drawRightString(right, 0.7 * inch, "Generated by Evolution Truck System")

    c.showPage()
    c.save()

    buf.seek(0)
    filename = f"{wo.work_order_number or f'WO-{wo.id}'}.pdf"

    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )