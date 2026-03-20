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

from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, KeepTogether


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
            joinedload(Invoice.items).joinedload(InvoiceItem.inventory_item),
        )
    )
    inv = db.execute(stmt).unique().scalars().first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return inv



def _ensure_editable(inv: Invoice) -> None:
    st = (inv.status or "").upper().strip()
    if st in ("PAID", "VOID"):
        raise HTTPException(status_code=422, detail="Invoice is closed. Cannot edit.")



def _recalc_invoice(inv: Invoice) -> None:
    # POS checkout can send discount_percent / price_mode / manual_price per line.
    # This router already recalculates totals from each saved unit_price and line_total.
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
    stmt = (
        select(Invoice)
        .where((Invoice.document_type.is_(None)) | (Invoice.document_type != "QUOTE"))
        .options(
            joinedload(Invoice.customer),
            joinedload(Invoice.items).joinedload(InvoiceItem.inventory_item),
        )
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
    return db.execute(stmt).unique().scalars().all()


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
            wo_number = getattr(wo, "work_order_number", None) or f"WO-{wo.id:06d}"

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

    cust = getattr(inv, "customer", None)
    cust_name = getattr(cust, "name", None) or "WALK-IN CUSTOMER"
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
    company_phone = "786-899-6360"

    inv_no = inv.invoice_number or f"INV-{inv.id:06d}"
    inv_date = inv.created_at.strftime("%m/%d/%Y") if getattr(inv, "created_at", None) else datetime.utcnow().strftime("%m/%d/%Y")
    inv_time = inv.created_at.strftime("%I:%M:%S %p") if getattr(inv, "created_at", None) else datetime.utcnow().strftime("%I:%M:%S %p")
    payment_method = (getattr(inv, "payment_method", None) or "-").upper()
    status_value = getattr(inv, "status", None) or "-"

    def item_part_no(it: Optional[InvoiceItem]) -> str:
        if not it:
            return "-"
        inv_item = getattr(it, "inventory_item", None)
        for val in (
            getattr(it, "part_code", None),
            getattr(inv_item, "part_code", None) if inv_item else None,
            getattr(inv_item, "oem_reference", None) if inv_item else None,
        ):
            if val:
                return str(val)
        for attr in ("part_number", "part_no", "sku", "item_code", "code", "ref_number"):
            val = getattr(it, attr, None)
            if val:
                return str(val)
        if getattr(it, "item_type", "").upper() == "LABOR":
            return "LABOR"
        inv_item_id = getattr(it, "inventory_item_id", None)
        if inv_item_id:
            return f"#{inv_item_id}"
        return str(getattr(it, "id", "-"))

    def item_desc(it: Optional[InvoiceItem]) -> str:
        if not it:
            return "No items"
        return getattr(it, "description", None) or getattr(it, "item_type", None) or "Item"

    def item_uom(it: Optional[InvoiceItem]) -> str:
        if not it:
            return "EA"
        for attr in ("uom", "unit_of_measure", "measure"):
            val = getattr(it, attr, None)
            if val:
                return str(val)
        return "EA"

    def item_list_price(it: Optional[InvoiceItem]) -> Decimal:
        if not it:
            return Decimal("0.00")
        for attr in ("list_price", "msrp", "sale_price_base", "base_price"):
            val = getattr(it, attr, None)
            if val is not None:
                try:
                    return _q2(Decimal(val))
                except Exception:
                    pass
        return _q2(getattr(it, "unit_price", Decimal("0.00")))

    def payment_label(value: str) -> str:
        v = (value or "").strip().upper()
        return {"CARD": "Credit Card", "CASH": "Cash", "ZELLE": "Zelle", "CHECK": "Check"}.get(v, v or "-")

    styles = getSampleStyleSheet()
    normal = ParagraphStyle("et_normal", parent=styles["Normal"], fontName="Helvetica", fontSize=9, leading=11)
    normal_small = ParagraphStyle("et_small", parent=normal, fontSize=8, leading=9.5)
    bold = ParagraphStyle("et_bold", parent=normal, fontName="Helvetica-Bold")
    title = ParagraphStyle("et_title", parent=normal, fontName="Helvetica-Bold", fontSize=18, leading=22)
    subtitle = ParagraphStyle("et_subtitle", parent=normal, fontName="Helvetica-Oblique", fontSize=10.5, leading=13)
    right_style = ParagraphStyle("et_right", parent=normal, alignment=TA_RIGHT)
    right_bold = ParagraphStyle("et_right_bold", parent=bold, alignment=TA_RIGHT)

    def P(text, style=normal):
        return Paragraph(str(text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"), style)

    def draw_page_number(canv, doc):
        canv.setFont("Helvetica", 8)
        canv.drawRightString(letter[0] - 28, 16, f"Page {doc.page}")

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        leftMargin=22,
        rightMargin=22,
        topMargin=16,
        bottomMargin=22,
    )

    story = []

    # Top header area
    left_header = [
        P("Evolution Truck", title),
        P("Truck Parts - Service - Accessories", subtitle),
        Spacer(1, 2),
        P(company_addr1, normal),
        P(company_addr2, normal),
        P(f"Phone: {company_phone}", normal),
    ]

    summary_rows = [
        [P("Invoice:", bold), P(inv_no, right_style)],
        [P("Date / Time:", bold), P(f"{inv_date} {inv_time}", right_style)],
        [P("Customer:", bold), P(cust_name, right_style)],
        [P("Work Order:", bold), P(wo_number, right_style)],
        [P("Status:", bold), P(status_value, right_style)],
        [P("Invoice Total:", bold), P(_safe_money(inv.total), right_bold)],
        [P("Payment:", bold), P(payment_label(payment_method), right_style)],
    ]
    summary_box = Table(summary_rows, colWidths=[88, 168])
    summary_box.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))

    header_tbl = Table([[left_header, summary_box]], colWidths=[326, 234])
    header_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(header_tbl)
    story.append(Spacer(1, 14))

    # Bill To / Ship To closer to reference sample
    bill_lines = [cust_name]
    if cust_address_1:
        bill_lines.append(cust_address_1)
    if cust_address_2:
        bill_lines.append(cust_address_2)
    if cust_phone:
        bill_lines.append(f"Phone: {cust_phone}")
    if cust_email:
        bill_lines.append(cust_email)

    ship_lines = [company_name, company_addr1, company_addr2, f"Office Phone: {company_phone}"]

    bill_block = [P("Bill To:", bold)] + [P(x, normal) for x in bill_lines]
    ship_block = [P("Ship To:", bold)] + [P(x, normal) for x in ship_lines]

    addr_tbl = Table([[bill_block, ship_block]], colWidths=[280, 280])
    addr_tbl.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(addr_tbl)
    story.append(Spacer(1, 8))

    meta_tbl = Table([[
        P("Customer P/O:", normal_small),
        P("Invoiced By: cashier", normal_small),
        P(f"Unit: {unit_value}", normal_small),
        P(f"VIN: {vin_last8}", normal_small),
    ]], colWidths=[150, 165, 105, 140])
    meta_tbl.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.black),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(meta_tbl)
    story.append(Spacer(1, 6))

    # Items area: header only + zebra rows, no full grid
    rows = list(inv.items or [])
    if not rows:
        rows = [None]

    data = [[
        P("Part / Misc", bold),
        P("Description / Ref Number", bold),
        P("U/M", bold),
        P("Quantity", right_bold),
        P("List", right_bold),
        P("Price", right_bold),
        P("Ext Price", right_bold),
    ]]

    for it in rows:
        qty = getattr(it, "qty", Decimal("0.00")) if it is not None else Decimal("0.00")
        unit_price = getattr(it, "unit_price", Decimal("0.00")) if it is not None else Decimal("0.00")
        ext_price = getattr(it, "line_total", Decimal("0.00")) if it is not None else Decimal("0.00")
        list_price = item_list_price(it) if it is not None else Decimal("0.00")

        data.append([
            P(_clip(item_part_no(it), 20), normal_small),
            P(_clip(item_desc(it), 56), normal_small),
            P(item_uom(it), normal_small),
            P(f"{float(qty):g}", right_style),
            P(_safe_money(list_price), right_style),
            P(_safe_money(unit_price), right_style),
            P(_safe_money(ext_price), right_style),
        ])

    items_tbl = Table(data, colWidths=[100, 205, 34, 48, 56, 56, 61], repeatRows=1)
    style_cmds = [
        ("LINEABOVE", (0, 0), (-1, 0), 0.8, colors.black),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    for row_idx in range(1, len(data)):
        if row_idx % 2 == 0:
            style_cmds.append(("BACKGROUND", (0, row_idx), (-1, row_idx), colors.HexColor("#efefef")))
    items_tbl.setStyle(TableStyle(style_cmds))
    story.append(items_tbl)
    story.append(Spacer(1, 10))

    notes_lines = []
    if getattr(inv, "notes", None):
        raw_notes = str(inv.notes or "").strip()
        if raw_notes:
            notes_lines = [x.strip() for x in raw_notes.split("|") if x.strip()]

    notes_block = [P("Notes:", bold)] + [P(x, normal_small) for x in notes_lines] if notes_lines else [P("Notes:", bold), P("-", normal_small)]
    notes_tbl = Table([[notes_block]], colWidths=[320])
    notes_tbl.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1, colors.black),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))

    totals_rows = [
        [P("Total Parts:", normal), P(_safe_money(inv.subtotal), right_style)],
        [P("Total Core Charges:", normal), P("$0.00", right_style)],
        [P("Total Core Returns:", normal), P("$0.00", right_style)],
        [P("Invoice Subtotal:", normal), P(_safe_money(inv.subtotal), right_style)],
        [P("Total Tax:", normal), P(_safe_money(inv.tax), right_style)],
        [P("Processing Fee:", normal), P(_safe_money(getattr(inv, "processing_fee", Decimal("0.00"))), right_style)],
        [P("Invoice Total:", bold), P(_safe_money(inv.total), right_bold)],
        [P("Payment:", bold), P(payment_label(payment_method), right_style)],
    ]
    totals_tbl = Table(totals_rows, colWidths=[154, 86])
    totals_tbl.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1, colors.black),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))

    bottom_tbl = Table([[notes_tbl, totals_tbl]], colWidths=[320, 240])
    bottom_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(KeepTogether([bottom_tbl]))

    is_quote = (getattr(inv, "document_type", None) or "").upper() == "QUOTE"

    def draw_page(canv, doc):
        if is_quote:
            canv.saveState()
            try:
                canv.setFillAlpha(0.10)
            except Exception:
                pass
            canv.setFillColor(colors.Color(0.75, 0.75, 0.75))
            canv.setFont("Helvetica-Bold", 64)
            canv.translate(letter[0] / 2, letter[1] / 2)
            canv.rotate(45)
            canv.drawCentredString(0, 0, "QUOTATION")
            canv.restoreState()
        draw_page_number(canv, doc)

    doc.build(story, onFirstPage=draw_page, onLaterPages=draw_page)

    buf.seek(0)
    filename = f"{inv.invoice_number or f'INV-{inv.id:06d}'}.pdf"
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
