from __future__ import annotations

from datetime import datetime, date
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, or_
from sqlalchemy.orm import Session, joinedload

from database import get_db
from models import (
    Customer,
    InventoryItem,
    InventoryItemImage,
    InventoryMovement,
    Invoice,
    InvoiceItem,
    User,
    WorkOrder,
)
from security import get_current_user, require_roles

router = APIRouter(prefix="/parts-store", tags=["Parts Store POS"])

ALLOWED_ROLES = ["SUPERADMIN", "ADMIN", "ACCOUNTANT", "VENDEDOR", "MECANICO"]
TAX_RATE = Decimal("0.07")
CARD_FEE_RATE = Decimal("0.04")
ZELLE_EMAIL = "yaidelp@yahoo.com"


def _q2(value: Decimal | int | float | str | None) -> Decimal:
    return Decimal(str(value or "0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _format_wo_number(wo_id: int) -> str:
    return f"WO-{wo_id:06d}"


def _format_invoice_number(inv_id: int) -> str:
    return f"INV-{inv_id:06d}"


def _primary_image_url(db: Session, item_id: int) -> Optional[str]:
    stmt = (
        select(InventoryItemImage)
        .where(InventoryItemImage.item_id == item_id)
        .order_by(InventoryItemImage.is_primary.desc(), InventoryItemImage.position.asc(), InventoryItemImage.id.asc())
    )
    img = db.execute(stmt).scalars().first()
    return img.image_url if img else None




def _fmt_dt_label(value: Optional[datetime]) -> str:
    if not value:
        return '-'
    return value.strftime('%m/%d/%Y %I:%M %p')


def _payment_label(value: Optional[str]) -> str:
    v = str(value or '').strip().upper()
    return {'CARD': 'Card', 'CASH': 'Cash', 'ZELLE': 'Zelle', 'CHECK': 'Check'}.get(v, v or '-')


def _image_gallery(db: Session, item_id: int) -> list[dict]:
    stmt = (
        select(InventoryItemImage)
        .where(InventoryItemImage.item_id == item_id)
        .order_by(InventoryItemImage.is_primary.desc(), InventoryItemImage.position.asc(), InventoryItemImage.id.asc())
    )
    rows = list(db.execute(stmt).scalars().all())
    return [
        {
            'id': img.id,
            'image_url': img.image_url,
            'alt_text': img.alt_text,
            'is_primary': bool(img.is_primary),
            'position': int(img.position or 0),
        }
        for img in rows
    ]


@router.get('/meta')
def parts_store_meta(current_user: User = Depends(require_roles(*ALLOWED_ROLES))):
    return {
        'ok': True,
        'module': 'parts_store',
        'title': 'Parts Store (POS)',
        'zelle_email': ZELLE_EMAIL,
        'rules': {
            'cash_tax_toggle': True,
            'card_processing_fee_rate': '0.04',
            'tax_rate': '0.07',
        },
    }


@router.get('/search-parts')
def search_parts(
    q: Optional[str] = Query(default=None),
    limit: int = Query(default=60, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED_ROLES)),
):
    stmt = select(InventoryItem).where(InventoryItem.deleted_at.is_(None), InventoryItem.is_active.is_(True))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                InventoryItem.part_code.ilike(like),
                InventoryItem.part_name.ilike(like),
                InventoryItem.oem_reference.ilike(like),
                InventoryItem.brand.ilike(like),
                InventoryItem.category.ilike(like),
                InventoryItem.engine_type.ilike(like),
            )
        )
    stmt = stmt.order_by(InventoryItem.part_name.asc()).limit(limit)
    items = list(db.execute(stmt).scalars().all())

    out = []
    for item in items:
        out.append({
            'id': item.id,
            'part_code': item.part_code,
            'part_name': item.part_name,
            'brand': item.brand,
            'category': item.category,
            'oem_reference': item.oem_reference,
            'engine_type': item.engine_type,
            'quantity_in_stock': int(item.quantity_in_stock or 0),
            'sale_price_base': float(_q2(item.sale_price_base)),
            'taxable': bool(item.taxable),
            'primary_image_url': _primary_image_url(db, item.id),
        })
    return out


@router.get('/part-details/{item_id}')
def part_details(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED_ROLES)),
):
    item = db.get(InventoryItem, item_id)
    if not item or item.deleted_at is not None or not bool(item.is_active):
        raise HTTPException(status_code=404, detail='Inventory item not found or inactive')

    images = _image_gallery(db, item.id)
    return {
        'id': item.id,
        'part_code': item.part_code,
        'part_name': item.part_name,
        'brand': item.brand,
        'category': item.category,
        'sub_category': item.sub_category,
        'oem_reference': item.oem_reference,
        'engine_type': item.engine_type,
        'vehicle_make': item.vehicle_make,
        'vehicle_model': item.vehicle_model,
        'year_from': item.year_from,
        'year_to': item.year_to,
        'description': item.description,
        'technical_notes': item.technical_notes,
        'quantity_in_stock': int(item.quantity_in_stock or 0),
        'sale_price_base': float(_q2(item.sale_price_base)),
        'taxable': bool(item.taxable),
        'primary_image_url': _primary_image_url(db, item.id),
        'images': images,
    }




@router.get('/customer-history/{customer_id}')
def customer_history(
    customer_id: int,
    limit: int = Query(default=6, ge=1, le=20),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED_ROLES)),
):
    customer = db.get(Customer, customer_id)
    if not customer or not bool(customer.is_active):
        raise HTTPException(status_code=404, detail='Customer not found')

    stmt = (
        select(Invoice)
        .where(Invoice.customer_id == customer_id)
        .options(joinedload(Invoice.items))
        .order_by(Invoice.created_at.desc())
        .limit(limit)
    )
    invoices = list(db.execute(stmt).unique().scalars().all())

    recommendations_map: dict[int, dict] = {}
    recent_out = []
    for inv in invoices:
        inv_items = []
        for it in list(inv.items or []):
            inv_items.append({
                'invoice_item_id': it.id,
                'inventory_item_id': it.inventory_item_id,
                'description': it.description,
                'qty': float(it.qty or 0),
                'unit_price': float(_q2(it.unit_price)),
                'line_total': float(_q2(it.line_total)),
            })
            if it.inventory_item_id:
                rec = recommendations_map.setdefault(it.inventory_item_id, {
                    'inventory_item_id': it.inventory_item_id,
                    'description': it.description,
                    'times': 0,
                })
                rec['times'] += 1

        recent_out.append({
            'invoice_id': inv.id,
            'invoice_number': inv.invoice_number or f'INV-{inv.id:06d}',
            'created_at_label': _fmt_dt_label(inv.created_at),
            'payment_method': _payment_label(inv.payment_method),
            'total': float(_q2(inv.total)),
            'items': inv_items,
        })

    recommendations = sorted(recommendations_map.values(), key=lambda x: (-x['times'], x['description'] or ''))[:8]

    return {
        'customer_id': customer.id,
        'customer_name': customer.name,
        'recent_invoices': recent_out,
        'recommendations': recommendations,
    }

@router.get('/search-customers')
def search_customers(
    q: str = Query(..., min_length=1),
    limit: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED_ROLES)),
):
    like = f"%{q.strip()}%"
    stmt = (
        select(Customer)
        .where(
            Customer.is_active.is_(True),
            or_(
                Customer.name.ilike(like),
                Customer.phone.ilike(like),
                Customer.email.ilike(like),
            ),
        )
        .order_by(Customer.name.asc())
        .limit(limit)
    )
    rows = list(db.execute(stmt).scalars().all())
    return [
        {
            'id': c.id,
            'name': c.name,
            'phone': c.phone,
            'email': c.email,
        }
        for c in rows
    ]


@router.post('/quick-customer')
def quick_customer_create(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED_ROLES)),
):
    name = str(payload.get('name') or '').strip()
    phone = str(payload.get('phone') or '').strip() or None
    email = str(payload.get('email') or '').strip() or None
    if not name:
        raise HTTPException(status_code=422, detail='Customer name is required')

    if phone:
        existing = db.execute(select(Customer).where(Customer.phone == phone)).scalars().first()
        if existing:
            return {'id': existing.id, 'name': existing.name, 'phone': existing.phone, 'email': existing.email, 'existing': True}

    customer = Customer(name=name, phone=phone, email=email)
    if hasattr(customer, 'is_active'):
        customer.is_active = True  # type: ignore[attr-defined]
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return {'id': customer.id, 'name': customer.name, 'phone': customer.phone, 'email': customer.email, 'existing': False}


@router.post('/checkout')
def checkout_parts_store(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    payment_method = str(payload.get('payment_method') or '').strip().upper()
    if payment_method not in {'CASH', 'CARD', 'ZELLE', 'CHECK'}:
        raise HTTPException(status_code=422, detail='payment_method must be CASH, CARD, ZELLE or CHECK')

    raw_items = payload.get('items') or []
    if not isinstance(raw_items, list) or not raw_items:
        raise HTTPException(status_code=422, detail='At least one cart item is required')

    customer_mode = str(payload.get('customer_mode') or 'WALK_IN').strip().upper()
    customer_id = payload.get('customer_id')
    quick_customer = payload.get('quick_customer') or {}
    notes = str(payload.get('notes') or '').strip() or None
    cash_taxable = bool(payload.get('cash_taxable', True))

    customer: Optional[Customer] = None
    if customer_mode == 'EXISTING':
        if not customer_id:
            raise HTTPException(status_code=422, detail='customer_id is required for existing customer')
        customer = db.get(Customer, int(customer_id))
        if not customer:
            raise HTTPException(status_code=404, detail='Customer not found')
    elif customer_mode == 'QUICK':
        name = str(quick_customer.get('name') or '').strip()
        phone = str(quick_customer.get('phone') or '').strip() or None
        email = str(quick_customer.get('email') or '').strip() or None
        if not name:
            raise HTTPException(status_code=422, detail='Quick customer name is required')
        if phone:
            existing = db.execute(select(Customer).where(Customer.phone == phone)).scalars().first()
            customer = existing
        if customer is None:
            customer = Customer(name=name, phone=phone, email=email)
            if hasattr(customer, 'is_active'):
                customer.is_active = True  # type: ignore[attr-defined]
            db.add(customer)
            db.flush()
    elif customer_mode == 'WALK_IN':
        customer = None
    else:
        raise HTTPException(status_code=422, detail='customer_mode must be EXISTING, QUICK, or WALK_IN')

    cart_lines = []
    subtotal = Decimal('0.00')
    taxable_subtotal = Decimal('0.00')

    for raw in raw_items:
        item_id = int(raw.get('item_id') or 0)
        qty = int(raw.get('qty') or 0)
        if item_id <= 0 or qty <= 0:
            raise HTTPException(status_code=422, detail='Each cart line requires valid item_id and qty')

        item = db.get(InventoryItem, item_id)
        if not item or item.deleted_at is not None or not bool(item.is_active):
            raise HTTPException(status_code=404, detail=f'Inventory item {item_id} not found or inactive')
        if int(item.quantity_in_stock or 0) < qty:
            raise HTTPException(status_code=422, detail=f'Insufficient stock for {item.part_code} - {item.part_name}')

        base_price = _q2(item.sale_price_base)
        unit_price = _q2(raw.get('unit_price') if raw.get('unit_price') is not None else item.sale_price_base)
        if unit_price < Decimal('0.00'):
            raise HTTPException(status_code=422, detail=f'Invalid unit price for {item.part_code} - {item.part_name}')
        line_total = _q2(unit_price * Decimal(qty))

        cart_lines.append({
            'item': item,
            'qty': qty,
            'base_price': base_price,
            'unit_price': unit_price,
            'line_total': line_total,
            'taxable': bool(item.taxable),
        })
        subtotal += line_total
        if bool(item.taxable):
            taxable_subtotal += line_total

    subtotal = _q2(subtotal)
    taxable_subtotal = _q2(taxable_subtotal)

    tax = Decimal('0.00')
    if payment_method == 'CASH':
        tax = _q2(taxable_subtotal * TAX_RATE) if cash_taxable else Decimal('0.00')
        processing_fee = Decimal('0.00')
    elif payment_method == 'CARD':
        tax = _q2(taxable_subtotal * TAX_RATE)
        processing_fee = _q2((subtotal + tax) * CARD_FEE_RATE)
    else:  # ZELLE or CHECK
        tax = _q2(taxable_subtotal * TAX_RATE)
        processing_fee = Decimal('0.00')

    total = _q2(subtotal + tax + processing_fee)

    description_bits = ['POS sale']
    if customer and customer.name:
        description_bits.append(customer.name)
    elif customer_mode == 'WALK_IN':
        description_bits.append('Walk-in Customer')

    work_order = WorkOrder(
        description=' - '.join(description_bits),
        status='DONE',
        customer_id=customer.id if customer else None,
    )
    db.add(work_order)
    db.flush()
    work_order.work_order_number = _format_wo_number(work_order.id)

    price_override_lines = []
    for line in cart_lines:
        if line['unit_price'] != line['base_price']:
            item = line['item']
            price_override_lines.append(
                f"{item.part_code or item.id}: base {line['base_price']} sold {line['unit_price']} qty {line['qty']}"
            )

    invoice_notes = notes
    if customer_mode == 'WALK_IN':
        invoice_notes = ('Walk-in Customer' + (' | ' + notes if notes else ''))
    if payment_method == 'ZELLE':
        extra = f'Zelle payment destination: {ZELLE_EMAIL}'
        invoice_notes = f'{invoice_notes} | {extra}' if invoice_notes else extra
    if payment_method == 'CARD':
        extra = 'POS card processing fee 4% applied.'
        invoice_notes = f'{invoice_notes} | {extra}' if invoice_notes else extra
    if payment_method == 'CASH':
        extra = f'Cash sale | Taxable: {"YES" if cash_taxable else "NO"}'
        invoice_notes = f'{invoice_notes} | {extra}' if invoice_notes else extra
    if price_override_lines:
        extra = 'Price overrides: ' + '; '.join(price_override_lines)
        invoice_notes = f'{invoice_notes} | {extra}' if invoice_notes else extra

    invoice = Invoice(
        work_order_id=work_order.id,
        customer_id=customer.id if customer else None,
        status='PAID',
        subtotal=subtotal,
        tax=tax,
        total=total,
        notes=invoice_notes,
        payment_method=payment_method,
        processing_fee=processing_fee,
        paid_at=datetime.utcnow(),
    )
    db.add(invoice)
    db.flush()
    invoice.invoice_number = _format_invoice_number(invoice.id)

    for line in cart_lines:
        item = line['item']
        ii = InvoiceItem(
            invoice_id=invoice.id,
            item_type='PART',
            description=item.part_name,
            qty=_q2(line['qty']),
            unit_price=line['unit_price'],
            line_total=line['line_total'],
            inventory_item_id=item.id,
            work_order_item_id=None,
            cost_snapshot=_q2(item.cost_price),
        )
        db.add(ii)

        item.quantity_in_stock = int(item.quantity_in_stock or 0) - int(line['qty'])
        item.times_sold = int(item.times_sold or 0) + int(line['qty'])
        item.last_used_date = date.today()

        mv = InventoryMovement(
            item_id=item.id,
            movement_type='out',
            quantity_moved=int(line['qty']),
            unit_cost=None,
            movement_date=datetime.utcnow(),
            user_id=current_user.id,
            related_job_id=work_order.id,
            movement_notes=f'POS sale {invoice.invoice_number}',
        )
        db.add(mv)
        db.add(item)

    db.commit()

    return {
        'ok': True,
        'invoice_id': invoice.id,
        'invoice_number': invoice.invoice_number,
        'work_order_id': work_order.id,
        'work_order_number': work_order.work_order_number,
        'customer_id': customer.id if customer else None,
        'customer_name': customer.name if customer else 'Walk-in Customer',
        'payment_method': payment_method,
        'cash_taxable': cash_taxable if payment_method == 'CASH' else None,
        'subtotal': float(subtotal),
        'tax': float(tax),
        'processing_fee': float(processing_fee),
        'total': float(total),
        'zelle_email': ZELLE_EMAIL if payment_method == 'ZELLE' else None,
        'invoice_pdf_url': f'/invoices/{invoice.id}/pdf',
    }
