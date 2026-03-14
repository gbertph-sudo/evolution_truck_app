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



def _clip(text: object, max_len: int) -> str:
    s = str(text or "").strip()
    if len(s) <= max_len:
        return s
    return s[: max_len - 3].rstrip() + "..."



def _clean_line(*parts: object) -> str:
    vals = [str(p).strip() for p in parts if str(p or "").strip()]
    return ", ".join(vals)


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

    wo = None
    wo_number = "-"
    if getattr(inv, "work_order_id", None):
        wo = db.get(WorkOrder, inv.work_order_id)
        if wo:
            wo_number = getattr(wo, "work_order_number", None) or f"WO-{wo.id}"

    vehicle = getattr(wo, "vehicle", None) if wo else None

    vin_full = (
        getattr(vehicle, "vin", None)
        or getattr(wo, "vin", None)
        or getattr(inv, "vin", None)
        or ""
    )
    vin_last8 = vin_full[-8:] if vin_full else "-"

    unit_value = (
        getattr(vehicle, "unit", None)
        or getattr(vehicle, "unit_number", None)
        or getattr(wo, "unit", None)
        or getattr(wo, "unit_number", None)
        or "-"
    )

    year_value = getattr(vehicle, "year", None) or getattr(wo, "year", None) or ""
    make_value = getattr(vehicle, "make", None) or getattr(wo, "make", None) or ""
    model_value = getattr(vehicle, "model", None) or getattr(wo, "model", None) or ""
    vehicle_line = " ".join([str(x).strip() for x in (year_value, make_value, model_value) if str(x).strip()]) or "-"

    cust = getattr(inv, "customer", None)
    cust_name = getattr(cust, "name", None) or "Walk-in Customer"
    cust_phone = getattr(cust, "phone", None) or ""
    cust_email = getattr(cust, "email", None) or ""
    cust_address_1 = (
        getattr(cust, "address", None)
        or getattr(cust, "address1", None)
        or getattr(cust, "street", None)
        or ""
    )
    cust_address_2 = _clean_line(
        getattr(cust, "city", None),
        getattr(cust, "state", None),
        getattr(cust, "zip_code", None) or getattr(cust, "zip", None),
    )

    company_name = "EVOLUTION TRUCK CORP"
    company_addr1 = "17210 NW 24TH AVE"
    company_addr2 = "MIAMI GARDENS, FL 33056-4611"
    company_phone = "Phone: 786-899-6360"

    inv_no = inv.invoice_number or f"INV-{inv.id:06d}"
    inv_date = inv.created_at.strftime("%m/%d/%Y") if getattr(inv, "created_at", None) else datetime.utcnow().strftime("%m/%d/%Y")
    payment_method = (getattr(inv, "payment_method", None) or "-").upper()
    status_value = getattr(inv, "status", None) or "-"

    items = list(inv.items or [])
    if not items:
        items = [None]

    def item_part_no(it: Optional[InvoiceItem]) -> str:
        if not it:
            return "-"
        for attr in ("part_number", "part_no", "sku", "item_code", "code", "ref_number"):
            val = getattr(it, attr, None)
            if val:
                return str(val)
        inv_item_id = getattr(it, "inventory_item_id", None)
        if inv_item_id:
            return str(inv_item_id)
        return str(getattr(it, "id", "-"))

    def item_desc(it: Optional[InvoiceItem]) -> str:
        if not it:
            return "No items"
        return getattr(it, "description", None) or getattr(it, "item_type", None) or "Part"

    row_h = 18
    first_table_top = 590
    first_bottom_nonlast = 60
    first_bottom_last = 175
    next_table_top = 710
    next_bottom_nonlast = 55
    next_bottom_last = 145
    header_h = 22

    first_cap_nonlast = max(1, int((first_table_top - first_bottom_nonlast - header_h) // row_h))
    first_cap_last = max(1, int((first_table_top - first_bottom_last - header_h) // row_h))
    next_cap_nonlast = max(1, int((next_table_top - next_bottom_nonlast - header_h) // row_h))
    next_cap_last = max(1, int((next_table_top - next_bottom_last - header_h) // row_h))

    page_chunks = []
    total_items = len(items)

    if total_items <= first_cap_last:
        page_chunks.append(("first_last", items))
    else:
        idx = first_cap_nonlast
        page_chunks.append(("first_nonlast", items[:idx]))
        remaining = items[idx:]
        while len(remaining) > next_cap_last:
            page_chunks.append(("next_nonlast", remaining[:next_cap_nonlast]))
            remaining = remaining[next_cap_nonlast:]
        page_chunks.append(("next_last", remaining))

    total_pages = len(page_chunks)

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    width, height = letter

    left = 18
    right = width - 18

    def draw_logo(x: float, y: float, w: float = 78, h: float = 40) -> None:
        if os.path.exists(LOGO_PATH_DEFAULT):
            try:
                c.drawImage(LOGO_PATH_DEFAULT, x, y, width=w, height=h, mask="auto")
            except Exception:
                pass

    def draw_rect(x: float, y: float, w: float, h: float, lw: float = 0.8) -> None:
        c.setLineWidth(lw)
        c.setStrokeColor(colors.black)
        c.rect(x, y, w, h, stroke=1, fill=0)

    def draw_box_title(x: float, y: float, title: str, h: float) -> None:
        c.setFont("Helvetica-Bold", 9)
        c.drawString(x + 6, y + h - 12, title)
        c.setLineWidth(0.6)
        c.line(x, y + h - 18, x + 1, y + h - 18)

    def draw_lines_in_box(x: float, y: float, w: float, h: float, lines: List[str], font_size: int = 8) -> None:
        text_y = y + h - 30
        c.setFont("Helvetica", font_size)
        for line in lines:
            if text_y < y + 8:
                break
            c.drawString(x + 6, text_y, _clip(line, 55))
            text_y -= 11

    def draw_first_page_header(page_no: int, page_total: int) -> None:
        header_y = height - 62
        draw_rect(left, header_y, right - left, 144)
        left_w = 250
        right_w = 170
        draw_rect(left, header_y, left_w, 144)
        draw_rect(right - right_w, header_y, right_w, 144)

        draw_logo(left + 8, header_y + 92, 64, 34)
        c.setFont("Helvetica-Bold", 18)
        c.drawCentredString((left + right) / 2, header_y + 102, company_name)
        c.setFont("Helvetica", 9)
        c.drawCentredString((left + right) / 2, header_y + 86, company_addr1)
        c.drawCentredString((left + right) / 2, header_y + 72, company_addr2)
        c.drawCentredString((left + right) / 2, header_y + 58, company_phone)

        c.setFont("Helvetica-Bold", 9)
        c.drawString(right - right_w + 8, header_y + 124, "INVOICE")
        c.setFont("Helvetica", 8.5)
        info_x = right - right_w + 8
        info_y = header_y + 108
        right_value_x = right - 8
        info_rows = [
            ("Invoice #", inv_no),
            ("Date", inv_date),
            ("Customer", cust_name),
            ("Work Order", wo_number),
            ("Unit", str(unit_value or "-")),
            ("VIN", vin_last8),
            ("Status", status_value),
        ]
        for label, value in info_rows:
            c.drawString(info_x, info_y, f"{label}:")
            c.drawRightString(right_value_x, info_y, _clip(value, 26))
            info_y -= 14

        box_y = 616
        box_h = 72
        gap = 12
        box_w = (right - left - gap) / 2
        bill_x = left
        ship_x = left + box_w + gap
        draw_rect(bill_x, box_y, box_w, box_h)
        draw_rect(ship_x, box_y, box_w, box_h)
        draw_box_title(bill_x, box_y, "BILL TO", box_h)
        draw_box_title(ship_x, box_y, "SHIP TO / UNIT", box_h)

        bill_lines = [
            cust_name,
            cust_address_1,
            cust_address_2,
            cust_phone,
            cust_email,
        ]
        ship_lines = [
            f"Unit: {unit_value}",
            f"VIN: {vin_last8}",
            vehicle_line,
            company_addr1,
            company_addr2,
        ]
        draw_lines_in_box(bill_x, box_y, box_w, box_h, [ln for ln in bill_lines if ln])
        draw_lines_in_box(ship_x, box_y, box_w, box_h, [ln for ln in ship_lines if ln])

        c.setFont("Helvetica", 8)
        c.drawRightString(right, 18, f"Page {page_no} of {page_total}")

    def draw_continuation_header(page_no: int, page_total: int) -> None:
        header_y = height - 46
        draw_rect(left, header_y, right - left, 34)
        c.setFont("Helvetica-Bold", 13)
        c.drawString(left + 10, header_y + 21, company_name)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(left + 10, header_y + 8, f"INVOICE {inv_no} - CONTINUATION")
        c.setFont("Helvetica", 8.5)
        c.drawRightString(right - 8, header_y + 20, f"Customer: {_clip(cust_name, 28)}")
        c.drawRightString(right - 8, header_y + 8, f"VIN: {vin_last8}   Unit: {unit_value}")
        c.setFont("Helvetica", 8)
        c.drawRightString(right, 18, f"Page {page_no} of {page_total}")

    def draw_items_table(chunk: List[Optional[InvoiceItem]], start_y: float, bottom_y: float) -> None:
        table_x = left
        table_w = right - left
        col_part = 82
        col_desc = 280
        col_qty = 55
        col_unit = 90
        col_ext = table_w - col_part - col_desc - col_qty - col_unit

        x_part = table_x
        x_desc = x_part + col_part
        x_qty = x_desc + col_desc
        x_unit = x_qty + col_qty
        x_ext = x_unit + col_unit

        c.setLineWidth(0.8)
        c.rect(table_x, bottom_y, table_w, start_y - bottom_y, stroke=1, fill=0)

        c.setFont("Helvetica-Bold", 8.5)
        c.drawString(x_part + 6, start_y - 14, "Part #")
        c.drawString(x_desc + 6, start_y - 14, "Description / Ref Number")
        c.drawCentredString(x_qty + col_qty / 2, start_y - 14, "Qty")
        c.drawRightString(x_unit + col_unit - 6, start_y - 14, "Unit Price")
        c.drawRightString(x_ext + col_ext - 6, start_y - 14, "Ext Price")
        c.line(table_x, start_y - 20, table_x + table_w, start_y - 20)

        for x in (x_desc, x_qty, x_unit, x_ext):
            c.line(x, bottom_y, x, start_y)

        y = start_y - 20
        c.setFont("Helvetica", 8.5)
        for it in chunk:
            next_y = y - row_h
            c.line(table_x, next_y, table_x + table_w, next_y)
            c.drawString(x_part + 6, y - 12, _clip(item_part_no(it), 14))
            c.drawString(x_desc + 6, y - 12, _clip(item_desc(it), 56))
            qty = getattr(it, "qty", 0) if it else 0
            unit_price = getattr(it, "unit_price", Decimal("0.00")) if it else Decimal("0.00")
            line_total = getattr(it, "line_total", Decimal("0.00")) if it else Decimal("0.00")
            c.drawCentredString(x_qty + col_qty / 2, y - 12, f"{float(qty):g}")
            c.drawRightString(x_unit + col_unit - 6, y - 12, _safe_money(unit_price))
            c.drawRightString(x_ext + col_ext - 6, y - 12, _safe_money(line_total))
            y = next_y

    def draw_last_page_footer(is_first_page: bool) -> None:
        notes_x = left
        notes_y = 38
        notes_w = 360
        notes_h = 92
        totals_gap = 12
        totals_w = (right - left) - notes_w - totals_gap
        totals_x = notes_x + notes_w + totals_gap
        totals_y = notes_y
        totals_h = notes_h

        draw_rect(notes_x, notes_y, notes_w, notes_h)
        draw_rect(totals_x, totals_y, totals_w, totals_h)

        c.setFont("Helvetica", 7.5)
        notes_text = [
            f"Payment Method: {payment_method}",
            f"Work Order Reference: {wo_number}",
            _clip(getattr(inv, 'notes', None) or "Parts sales invoice. All claims must be reported immediately upon delivery.", 110),
            "Electrical parts, special-order parts, and used parts are not returnable.",
            "Warranty applies only to manufacturer defects and does not include labor.",
        ]
        ty = notes_y + notes_h - 14
        for line in notes_text:
            c.drawString(notes_x + 8, ty, _clip(line, 88))
            ty -= 12

        c.setFont("Helvetica", 10)
        label_x = totals_x + 10
        value_x = totals_x + totals_w - 10
        line_y = totals_y + totals_h - 18
        c.drawString(label_x, line_y, "Subtotal:")
        c.drawRightString(value_x, line_y, _safe_money(inv.subtotal))
        line_y -= 16
        c.drawString(label_x, line_y, "Tax:")
        c.drawRightString(value_x, line_y, _safe_money(inv.tax))
        line_y -= 16
        c.drawString(label_x, line_y, "Processing Fee:")
        c.drawRightString(value_x, line_y, _safe_money(inv.processing_fee))
        line_y -= 20
        c.setFont("Helvetica-Bold", 12)
        c.drawString(label_x, line_y, "Total:")
        c.drawRightString(value_x, line_y, _safe_money(inv.total))

        c.setFont("Helvetica-Oblique", 7.5)
        c.drawString(left, 22, f"{company_name}  |  {company_phone}")

    for idx, (page_kind, chunk) in enumerate(page_chunks, start=1):
        is_first_page = page_kind.startswith("first")
        is_last_page = page_kind.endswith("last")

        if is_first_page:
            draw_first_page_header(idx, total_pages)
            table_top = first_table_top
            table_bottom = first_bottom_last if is_last_page else first_bottom_nonlast
        else:
            draw_continuation_header(idx, total_pages)
            table_top = next_table_top
            table_bottom = next_bottom_last if is_last_page else next_bottom_nonlast

        draw_items_table(chunk, table_top, table_bottom)

        if is_last_page:
            draw_last_page_footer(is_first_page=is_first_page)

        c.showPage()

    c.save()
    buf.seek(0)
    filename = f"{inv.invoice_number or f'INV-{inv.id}'}.pdf"

    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
