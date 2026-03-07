from __future__ import annotations

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
from models import Invoice, InvoiceItem, InventoryItem, WorkOrder, User
from schemas import (
    InvoiceOut,
    InvoiceStatusUpdate,
    InvoicePay,
    InvoiceItemPriceUpdate,
)

from security import get_current_user, require_roles

# PDF (ReportLab)
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.lib import colors


router = APIRouter(tags=["Invoices"])

ALLOWED_STATUS = {"DRAFT", "SENT", "PAID", "VOID"}

TAX_RATE = Decimal("0.07")
CARD_FEE_RATE = Decimal("0.04")

LOGO_PATH_DEFAULT = "static/img/logo.png"


# -------------------------------
# Helpers
# -------------------------------
def _q2(x: Decimal) -> Decimal:
    return (x or Decimal("0.00")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _normalize_status(s: str) -> str:
    v = (s or "").strip().upper()
    if v not in ALLOWED_STATUS:
        raise HTTPException(status_code=422, detail=f"Invalid status. Use: {', '.join(sorted(ALLOWED_STATUS))}")
    return v


def _load_invoice(db: Session, invoice_id: int) -> Invoice:
    stmt = (
        select(Invoice)
        .where(Invoice.id == invoice_id)
        .options(
            joinedload(Invoice.customer),
            joinedload(Invoice.items),
        )
    )
    inv = db.execute(stmt).scalars().first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return inv


def _ensure_editable(inv: Invoice) -> None:
    st = (inv.status or "").upper().strip()
    if st in ("PAID", "VOID"):
        raise HTTPException(status_code=422, detail="Invoice is closed. Cannot edit.")


def _recalc_invoice(inv: Invoice) -> None:
    subtotal = Decimal("0.00")
    for it in (inv.items or []):
        subtotal += _q2(it.line_total or Decimal("0.00"))
    inv.subtotal = _q2(subtotal)

    pm = (inv.payment_method or "").upper().strip()

    if pm == "CASH":
        inv.tax = Decimal("0.00")
        inv.processing_fee = Decimal("0.00")
    elif pm == "ZELLE":
        inv.tax = _q2(inv.subtotal * TAX_RATE)
        inv.processing_fee = Decimal("0.00")
    elif pm == "CARD":
        inv.tax = _q2(inv.subtotal * TAX_RATE)
        inv.processing_fee = _q2((inv.subtotal + inv.tax) * CARD_FEE_RATE)
    else:
        # si no hay método todavía, normaliza pero no inventa
        inv.tax = _q2(inv.tax or Decimal("0.00"))
        inv.processing_fee = _q2(inv.processing_fee or Decimal("0.00"))

    inv.total = _q2(inv.subtotal + inv.tax + inv.processing_fee)


def _safe_money(d: Decimal) -> str:
    try:
        return f"${float(d):,.2f}"
    except Exception:
        return "$0.00"


# -------------------------------
# Endpoints
# -------------------------------
@router.get("/invoices", response_model=List[InvoiceOut])
def list_invoices(
    q: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=80, ge=1, le=300),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stmt = select(Invoice).options(
        joinedload(Invoice.customer),
        joinedload(Invoice.items),
    )

    if q:
        txt = f"%{q.strip()}%"
        stmt = stmt.where(
            (Invoice.invoice_number.ilike(txt)) |
            (Invoice.notes.ilike(txt))
        )

    if status:
        stmt = stmt.where(Invoice.status == _normalize_status(status))

    stmt = stmt.order_by(desc(Invoice.created_at)).limit(limit)
    return db.execute(stmt).scalars().all()


@router.get("/invoices/{invoice_id}", response_model=InvoiceOut)
def get_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _load_invoice(db, invoice_id)


@router.put("/invoices/{invoice_id}/status", response_model=InvoiceOut)
def update_invoice_status(
    invoice_id: int,
    payload: InvoiceStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    inv = db.get(Invoice, invoice_id)
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")

    inv.status = _normalize_status(payload.status)

    if inv.status == "PAID" and inv.paid_at is None:
        inv.paid_at = datetime.utcnow()

    db.commit()
    return _load_invoice(db, invoice_id)


@router.put("/invoices/{invoice_id}/pay", response_model=InvoiceOut)
def pay_invoice(
    invoice_id: int,
    payload: InvoicePay,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    inv = _load_invoice(db, invoice_id)
    _ensure_editable(inv)

    method = (payload.method or "").upper().strip()
    if method not in {"CASH", "CARD", "ZELLE"}:
        raise HTTPException(status_code=422, detail="Invalid method. Use CASH, CARD, or ZELLE")

    inv.payment_method = method
    _recalc_invoice(inv)

    inv.status = "PAID"
    inv.paid_at = datetime.utcnow()

    db.commit()
    return _load_invoice(db, invoice_id)


# ✅ SOLO ADMIN/SUPERADMIN
@router.patch("/invoices/{invoice_id}/items/{item_id}", response_model=InvoiceOut)
def update_invoice_item_price(
    invoice_id: int,
    item_id: int,
    payload: InvoiceItemPriceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("ADMIN", "SUPERADMIN")),
):
    inv = _load_invoice(db, invoice_id)
    _ensure_editable(inv)

    it = db.get(InvoiceItem, item_id)
    if not it or it.invoice_id != invoice_id:
        raise HTTPException(status_code=404, detail="Invoice item not found")

    if payload.unit_price is None:
        raise HTTPException(status_code=422, detail="unit_price is required")

    new_unit = _q2(payload.unit_price)
    if new_unit < 0:
        raise HTTPException(status_code=422, detail="unit_price must be >= 0")

    # ✅ markup 0..200% basado en cost_snapshot si hay cost
    cost = _q2(it.cost_snapshot or Decimal("0.00"))
    if cost > 0:
        markup = ((new_unit / cost) - Decimal("1.0")) * Decimal("100.0")
        if markup < 0 or markup > 200:
            raise HTTPException(status_code=422, detail="Markup must be between 0% and 200% (based on cost).")

    it.unit_price = new_unit
    it.line_total = _q2(new_unit * _q2(it.qty))

    _recalc_invoice(inv)

    db.commit()
    return _load_invoice(db, invoice_id)


@router.get("/invoices/{invoice_id}/pdf")
def invoice_pdf(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    inv = _load_invoice(db, invoice_id)

    # Si quieres mostrar el WO number, lo buscamos por work_order_id
    wo_number = "-"
    if getattr(inv, "work_order_id", None):
        wo = db.get(WorkOrder, inv.work_order_id)
        if wo:
            wo_number = wo.work_order_number or f"WO-{wo.id}"

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    width, height = letter

    left = 0.75 * inch
    right = width - 0.75 * inch
    top = height - 0.75 * inch

    # logo (si existe)
    if os.path.exists(LOGO_PATH_DEFAULT):
        try:
            c.drawImage(LOGO_PATH_DEFAULT, left, top - 0.85 * inch, width=1.6 * inch, height=0.75 * inch, mask="auto")
        except Exception:
            pass

    c.setFont("Helvetica-Bold", 16)
    c.drawString(left + 1.8 * inch, top - 0.15 * inch, "Evolution Truck - Invoice")

    c.setFont("Helvetica", 10)
    inv_no = inv.invoice_number or f"INV-{inv.id}"
    c.drawRightString(right, top - 0.10 * inch, f"Invoice: {inv_no}")
    c.drawRightString(right, top - 0.28 * inch, f"Date: {inv.created_at.strftime('%Y-%m-%d %H:%M')}")
    c.drawRightString(right, top - 0.46 * inch, f"Status: {inv.status}")
    c.drawRightString(right, top - 0.64 * inch, f"Payment: {inv.payment_method or '-'}")

    c.setStrokeColor(colors.black)
    c.setLineWidth(1)
    c.line(left, top - 0.95 * inch, right, top - 0.95 * inch)

    y = top - 1.25 * inch

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

    section_title("Bill To")
    cust_name = inv.customer.name if inv.customer else "-"
    row("Customer", cust_name)
    if inv.customer:
        row("Phone", inv.customer.phone or "-")
        row("Email", inv.customer.email or "-")
    row("Work Order", wo_number)

    y -= 0.10 * inch

    section_title("Items")
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
    for it in (inv.items or [])[:18]:
        c.drawString(left, y, (it.item_type or "")[:10])
        c.drawString(left + 0.8 * inch, y, (it.description or "")[:50])
        c.drawRightString(right - 1.4 * inch, y, f"{float(it.qty):g}")
        c.drawRightString(right - 0.7 * inch, y, f"{float(it.unit_price):,.2f}")
        c.drawRightString(right, y, f"{float(it.line_total):,.2f}")
        y -= 0.14 * inch
        if y < 2.2 * inch:
            break

    # Totals
    y = max(y - 0.10 * inch, 2.0 * inch)
    section_title("Totals")
    row("Subtotal", _safe_money(inv.subtotal))
    row("Tax", _safe_money(inv.tax))
    row("Fee", _safe_money(inv.processing_fee))
    c.setFont("Helvetica-Bold", 11)
    c.drawString(left, y, f"TOTAL: {_safe_money(inv.total)}")
    y -= 0.22 * inch

    c.setFont("Helvetica-Oblique", 8)
    c.drawRightString(right, 0.7 * inch, "Generated by Evolution Truck System")

    c.showPage()
    c.save()

    buf.seek(0)
    filename = f"{inv.invoice_number or f'INV-{inv.id}'}.pdf"

    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )