from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import select, desc
from sqlalchemy.orm import Session, joinedload

from database import get_db
from models import Invoice, InvoiceItem, User
from security import get_current_user, require_roles

router = APIRouter(prefix="/api/quotes", tags=["Estimates / Quotes"])

ALLOWED_ROLES = ["SUPERADMIN", "ADMIN", "ACCOUNTANT", "VENDEDOR", "MECANICO"]


def _q2(value) -> Decimal:
    return Decimal(str(value or "0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _payment_label(value: Optional[str]) -> str:
    v = str(value or "").strip().upper()
    return {"CARD": "Card", "CASH": "Cash", "ZELLE": "Zelle", "CHECK": "Check", "ACCOUNT": "Charge to Account"}.get(v, v or "-")


def _doc_label(value: Optional[str]) -> str:
    return "Quote" if str(value or "").strip().upper() == "QUOTE" else "Sale"


def _expire_old_quotes(db: Session) -> int:
    now = datetime.utcnow()
    rows = list(
        db.execute(
            select(Invoice).where(
                Invoice.document_type == "QUOTE",
                Invoice.status == "QUOTE",
                Invoice.expires_at.is_not(None),
                Invoice.expires_at < now,
            )
        ).scalars().all()
    )
    changed = 0
    for inv in rows:
        inv.status = "EXPIRED"
        changed += 1
    if changed:
        db.commit()
    return changed


def _load_quote(db: Session, quote_id: int) -> Invoice:
    inv = db.execute(
        select(Invoice)
        .where(Invoice.id == quote_id)
        .options(
            joinedload(Invoice.customer),
            joinedload(Invoice.work_order),
            joinedload(Invoice.items).joinedload(InvoiceItem.inventory_item),
        )
    ).unique().scalars().first()
    if not inv:
        raise HTTPException(status_code=404, detail="Quote not found")
    if (inv.document_type or "").upper() != "QUOTE":
        raise HTTPException(status_code=422, detail="This record is not a quote")
    return inv


def _append_note(inv: Invoice, extra: Optional[str]) -> None:
    extra = str(extra or "").strip()
    if not extra:
        return
    if inv.notes:
        inv.notes = f"{inv.notes} | {extra}"
    else:
        inv.notes = extra


def _invoice_out(inv: Invoice) -> dict:
    customer = None
    if getattr(inv, "customer", None):
        customer = {
            "id": inv.customer.id,
            "name": inv.customer.name,
            "phone": getattr(inv.customer, "phone", None),
            "email": getattr(inv.customer, "email", None),
        }
    work_order = None
    if getattr(inv, "work_order", None):
        work_order = {
            "id": inv.work_order.id,
            "work_order_number": getattr(inv.work_order, "work_order_number", None),
            "status": getattr(inv.work_order, "status", None),
        }
    items = []
    for it in list(inv.items or []):
        items.append({
            "id": it.id,
            "item_type": it.item_type,
            "description": it.description,
            "qty": str(it.qty),
            "unit_price": str(it.unit_price),
            "line_total": str(it.line_total),
            "inventory_item_id": it.inventory_item_id,
            "work_order_item_id": it.work_order_item_id,
        })
    return {
        "id": inv.id,
        "invoice_number": inv.invoice_number,
        "work_order_id": inv.work_order_id,
        "customer_id": inv.customer_id,
        "status": inv.status,
        "document_type": inv.document_type or "QUOTE",
        "settlement_type": getattr(inv, "settlement_type", None),
        "expires_at": inv.expires_at.isoformat() if getattr(inv, "expires_at", None) else None,
        "converted_at": inv.converted_at.isoformat() if getattr(inv, "converted_at", None) else None,
        "inventory_applied": bool(getattr(inv, "inventory_applied", False)),
        "quote_origin": getattr(inv, "quote_origin", None),
        "subtotal": float(_q2(inv.subtotal)),
        "tax": float(_q2(inv.tax)),
        "total": float(_q2(inv.total)),
        "processing_fee": float(_q2(getattr(inv, "processing_fee", 0))),
        "payment_method": inv.payment_method,
        "paid_at": inv.paid_at.isoformat() if getattr(inv, "paid_at", None) else None,
        "notes": inv.notes,
        "created_at": inv.created_at.isoformat() if getattr(inv, "created_at", None) else None,
        "customer": customer,
        "work_order": work_order,
        "items": items,
        "payment_label": _payment_label(inv.payment_method),
        "document_label": _doc_label(inv.document_type),
    }


@router.get("/meta")
def get_quotes_meta(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(*ALLOWED_ROLES)),
):
    expired = _expire_old_quotes(db)
    return {
        "ok": True,
        "module": "estimates_quotes",
        "title": "Estimates / Quotes",
        "expired_now": expired,
        "statuses": ["QUOTE", "EXPIRED", "UNPAID", "PAID", "VOID"],
        "document_types": ["QUOTE"],
        "settlement_types": ["PAY_NOW", "CHARGE_ACCOUNT"],
    }


@router.get("/kpis")
def get_quotes_kpis(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(*ALLOWED_ROLES)),
):
    _expire_old_quotes(db)
    quotes = list(db.execute(select(Invoice).where(Invoice.document_type == "QUOTE")).scalars().all())
    now = datetime.utcnow()

    active = expired = unpaid = paid = expiring_soon = 0
    total_open_amount = Decimal("0.00")

    for inv in quotes:
        st = (inv.status or "").upper()
        if st == "QUOTE":
            active += 1
            total_open_amount += _q2(inv.total)
            if getattr(inv, "expires_at", None) and inv.expires_at > now:
                seconds = (inv.expires_at - now).total_seconds()
                if seconds <= 6 * 3600:
                    expiring_soon += 1
        elif st == "EXPIRED":
            expired += 1
        elif st == "UNPAID":
            unpaid += 1
            total_open_amount += _q2(inv.total)
        elif st == "PAID":
            paid += 1

    return {
        "active_quotes": active,
        "expired_quotes": expired,
        "unpaid_quotes": unpaid,
        "paid_quotes": paid,
        "expiring_soon": expiring_soon,
        "open_amount": float(_q2(total_open_amount)),
    }


@router.get("")
def list_quotes(
    q: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=300),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(*ALLOWED_ROLES)),
):
    _expire_old_quotes(db)
    rows = list(
        db.execute(
            select(Invoice)
            .where(Invoice.document_type == "QUOTE")
            .options(
                joinedload(Invoice.customer),
                joinedload(Invoice.work_order),
                joinedload(Invoice.items),
            )
            .order_by(desc(Invoice.created_at))
            .limit(limit)
        ).unique().scalars().all()
    )

    qv = str(q or "").strip().lower()
    status_v = str(status or "").strip().upper()
    out = []
    for inv in rows:
        if status_v and (inv.status or "").upper() != status_v:
            continue
        hay = " ".join([
            str(inv.invoice_number or ""),
            str(getattr(inv.customer, "name", "") or ""),
            str(getattr(inv.customer, "phone", "") or ""),
            str(inv.notes or ""),
        ]).lower()
        if qv and qv not in hay:
            continue
        out.append(_invoice_out(inv))
    return out


@router.get("/{quote_id}")
def get_quote(
    quote_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(*ALLOWED_ROLES)),
):
    _expire_old_quotes(db)
    inv = _load_quote(db, quote_id)
    return _invoice_out(inv)


@router.post("/cleanup-expired")
def cleanup_expired_quotes(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(*ALLOWED_ROLES)),
):
    expired_now = _expire_old_quotes(db)
    return {"ok": True, "expired_now": expired_now}


@router.post("/{quote_id}/mark-paid")
def mark_quote_paid(
    quote_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED_ROLES)),
):
    inv = _load_quote(db, quote_id)
    st = (inv.status or "").upper()
    if st not in {"QUOTE", "UNPAID"}:
        raise HTTPException(status_code=422, detail="Only active or receivable quotes can be marked paid")

    payment_method = str(payload.get("payment_method") or "").strip().upper()
    if payment_method not in {"CASH", "CARD", "ZELLE", "CHECK"}:
        raise HTTPException(status_code=422, detail="Invalid payment method")

    inv.document_type = "SALE"
    inv.status = "PAID"
    inv.payment_method = payment_method
    inv.paid_at = datetime.utcnow()
    if hasattr(inv, "converted_at"):
        inv.converted_at = datetime.utcnow()
    _append_note(inv, payload.get("notes"))
    db.commit()
    db.refresh(inv)
    return {
        "ok": True,
        "moved_to_invoices": True,
        "invoice_id": inv.id,
        "invoice_number": inv.invoice_number,
    }


@router.post("/{quote_id}/convert")
def convert_quote(
    quote_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED_ROLES)),
):
    inv = _load_quote(db, quote_id)
    st = (inv.status or "").upper()
    if st != "QUOTE":
        raise HTTPException(status_code=422, detail="Only active QUOTE records can be converted")

    settlement_type = str(payload.get("settlement_type") or "").strip().upper()
    payment_method = str(payload.get("payment_method") or "").strip().upper() or None

    if settlement_type not in {"PAY_NOW", "CHARGE_ACCOUNT"}:
        raise HTTPException(status_code=422, detail="Invalid settlement_type")

    inv.document_type = "SALE"
    if hasattr(inv, "settlement_type"):
        inv.settlement_type = settlement_type
    if hasattr(inv, "converted_at"):
        inv.converted_at = datetime.utcnow()

    if settlement_type == "PAY_NOW":
        if payment_method not in {"CASH", "CARD", "ZELLE", "CHECK"}:
            raise HTTPException(status_code=422, detail="Payment method required for PAY_NOW")
        inv.status = "PAID"
        inv.payment_method = payment_method
        inv.paid_at = datetime.utcnow()
    else:
        inv.status = "UNPAID"
        inv.payment_method = "ACCOUNT"

    _append_note(inv, payload.get("notes"))
    db.commit()
    db.refresh(inv)

    return {
        "ok": True,
        "moved_to_invoices": True,
        "invoice_id": inv.id,
        "invoice_number": inv.invoice_number,
        "status": inv.status,
    }


@router.post("/{quote_id}/void")
def void_quote(
    quote_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(*ALLOWED_ROLES)),
):
    inv = _load_quote(db, quote_id)
    if (inv.status or "").upper() == "VOID":
        return {"ok": True, "quote_id": inv.id, "status": inv.status}
    inv.status = "VOID"
    _append_note(inv, payload.get("notes"))
    db.commit()
    return {"ok": True, "quote_id": inv.id, "status": inv.status}


@router.get("/{quote_id}/pdf")
def quote_pdf_redirect(
    quote_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(*ALLOWED_ROLES)),
):
    inv = _load_quote(db, quote_id)
    return RedirectResponse(url=f"/invoices/{inv.id}/pdf", status_code=307)
