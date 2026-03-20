from __future__ import annotations

# schemas.py
# Comentarios en español. Nombres/strings en inglés.

from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List

from pydantic import BaseModel, EmailStr, Field, ConfigDict, field_validator


# ======================================================
# AUTH
# ======================================================
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class RoleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    is_active: bool

    # Si tu ORM trae role como relación:
    role: Optional[RoleOut] = None

    # Si tu API a veces devuelve role_name directo:
    role_name: Optional[str] = None


class BootstrapSuperAdminSchema(BaseModel):
    username: str
    email: Optional[EmailStr] = None
    password: str
    full_name: Optional[str] = None


class UserCreate(BaseModel):
    username: str
    password: str
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None

    # puedes mandar role_id o role_name
    role_id: Optional[int] = None
    role_name: Optional[str] = None


class UserUpdate(BaseModel):
    role_name: Optional[str] = None
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None


class UserSetActive(BaseModel):
    is_active: bool


class UserPasswordReset(BaseModel):
    new_password: str


# ======================================================
# COMPANIES
# ======================================================
class CompanyCreate(BaseModel):
    name: str


class CompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    is_active: bool = True

class CompanySetActive(BaseModel):
    is_active: bool

# ======================================================
# CUSTOMERS  ✅ many-to-many (customer -> many companies)
# ======================================================
class CustomerCreate(BaseModel):
    name: str
    phone: Optional[str] = None
    email: Optional[EmailStr] = None

    # ✅ ahora un customer puede pertenecer a varias companies
    company_ids: List[int] = Field(default_factory=list)

    @field_validator("company_ids")
    @classmethod
    def validate_company_ids(cls, v: List[int]):
        # limpia duplicados + valida ids
        cleaned: List[int] = []
        seen = set()
        for x in (v or []):
            ix = int(x)
            if ix <= 0:
                raise ValueError("company_ids must contain positive integers")
            if ix not in seen:
                cleaned.append(ix)
                seen.add(ix)
        return cleaned


class CustomerUpdate(BaseModel):
    # ✅ update flexible
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    is_active: Optional[bool] = None

    # ✅ reemplaza lista completa
    company_ids: Optional[List[int]] = None

    @field_validator("company_ids")
    @classmethod
    def validate_company_ids_optional(cls, v: Optional[List[int]]):
        if v is None:
            return v
        cleaned: List[int] = []
        seen = set()
        for x in v:
            ix = int(x)
            if ix <= 0:
                raise ValueError("company_ids must contain positive integers")
            if ix not in seen:
                cleaned.append(ix)
                seen.add(ix)
        return cleaned


class CustomerOut(BaseModel):
    """
    ✅ IMPORTANTE:
    - 'companies' funciona perfecto con ORM relationship.
    - 'company_ids' NO se puede auto-construir en schemas con facilidad sin computed_field,
      así que lo ideal es que el BACKEND lo llene al devolver el customer:
         company_ids = [c.id for c in customer.companies]
    """
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    is_active: bool = True  # ✅ NUEVO
    # ✅ Para forms simples (lo llena el backend)
    company_ids: List[int] = Field(default_factory=list)

    # ✅ Para UI (mostrar nombres)
    companies: List[CompanyOut] = Field(default_factory=list)

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class CustomerSetActive(BaseModel):
    is_active: bool
# ======================================================
# VEHICLES
# ======================================================
class VehicleCreate(BaseModel):
    vin: Optional[str] = None
    unit_number: Optional[str] = None
    make: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    customer_id: Optional[int] = None

    @field_validator("vin")
    @classmethod
    def validate_vin(cls, v: Optional[str]):
        if v is None:
            return v
        vv = v.strip().upper()
        if vv == "":
            return None
        if len(vv) != 17:
            raise ValueError("VIN must be exactly 17 characters")
        return vv


class VehicleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    vin: Optional[str] = None
    unit_number: Optional[str] = None
    make: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    customer_id: Optional[int] = None
    is_active: bool = True  # ✅ NUEVO


class VehicleSetActive(BaseModel):
    is_active: bool

# ======================================================
# WORK ORDERS
# ======================================================
ALLOWED_WORK_ORDER_STATUS = {"OPEN", "IN_PROGRESS", "DONE", "CANCELLED"}


class WorkOrderItemAdd(BaseModel):
    inventory_item_id: int
    qty: Decimal = Field(default=Decimal("1.00"), gt=0)
    unit_price: Optional[Decimal] = Field(default=None, ge=0)
    markup_percent: Optional[Decimal] = None


class WorkOrderItemUpdate(BaseModel):
    qty: Decimal = Field(gt=0)

class WorkOrderItemPriceUpdate(BaseModel):
    unit_price: Optional[Decimal] = Field(default=None, ge=0)
    markup_percent: Optional[Decimal] = None


class WorkOrderItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    work_order_id: int
    inventory_item_id: int

    description_snapshot: str
    qty: Decimal
    unit_price_snapshot: Decimal
    line_total: Decimal
    cost_snapshot: Decimal = Decimal("0.00")

    added_by_user_id: Optional[int] = None
    part_code: Optional[str] = None
    created_at: datetime


class WorkOrderLaborCreate(BaseModel):
    description: str
    hours: Decimal = Field(default=Decimal("1.00"), ge=0)
    rate: Decimal = Field(default=Decimal("0.00"), ge=0)

class WorkOrderLaborUpdate(BaseModel):
    description: Optional[str] = None
    hours: Optional[Decimal] = Field(default=None, ge=0)
    rate: Optional[Decimal] = Field(default=None, ge=0)

class WorkOrderLaborOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    work_order_id: int
    description: str
    hours: Decimal
    rate: Decimal
    line_total: Decimal
    created_at: datetime

class WorkOrderCreate(BaseModel):
    description: str

    customer_id: Optional[int] = None
    company_id: Optional[int] = None
    vehicle_id: Optional[int] = None
    mechanic_id: Optional[int] = None

    status: Optional[str] = "OPEN"

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]):
        vv = (v or "OPEN").strip().upper()
        if vv not in ALLOWED_WORK_ORDER_STATUS:
            raise ValueError(f"Invalid status. Use: {', '.join(sorted(ALLOWED_WORK_ORDER_STATUS))}")
        return vv


class WorkOrderUpdate(BaseModel):
    description: Optional[str] = None

    customer_id: Optional[int] = None
    company_id: Optional[int] = None
    vehicle_id: Optional[int] = None
    mechanic_id: Optional[int] = None

    status: Optional[str] = None

    @field_validator("status")
    @classmethod
    def validate_status_optional(cls, v: Optional[str]):
        if v is None:
            return v
        vv = (v or "").strip().upper()
        if vv not in ALLOWED_WORK_ORDER_STATUS:
            raise ValueError(f"Invalid status. Use: {', '.join(sorted(ALLOWED_WORK_ORDER_STATUS))}")
        return vv


class WorkOrderStatusUpdate(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str):
        vv = (v or "").strip().upper()
        if vv not in ALLOWED_WORK_ORDER_STATUS:
            raise ValueError(f"Invalid status. Use: {', '.join(sorted(ALLOWED_WORK_ORDER_STATUS))}")
        return vv


# ======================================================
# INVOICES
# ======================================================
ALLOWED_INVOICE_STATUS = {"DRAFT", "SENT", "PAID", "VOID"}
ALLOWED_ITEM_TYPES = {"LABOR", "PART", "FEE"}


class InvoiceCreateFromWorkOrder(BaseModel):
    notes: Optional[str] = None


class InvoiceItemCreate(BaseModel):
    item_type: str = "LABOR"
    description: str
    qty: Decimal = Field(default=Decimal("1.00"), gt=0)
    unit_price: Decimal = Field(default=Decimal("0.00"), ge=0)

    @field_validator("item_type")
    @classmethod
    def validate_item_type(cls, v: str):
        vv = (v or "").strip().upper()
        if vv not in ALLOWED_ITEM_TYPES:
            raise ValueError("Invalid item_type. Use: LABOR, PART, FEE")
        return vv


class InvoiceItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    item_type: str
    description: str
    qty: Decimal
    unit_price: Decimal
    line_total: Decimal

    # ✅ NUEVO: links opcionales
    inventory_item_id: Optional[int] = None
    work_order_item_id: Optional[int] = None
    part_code: Optional[str] = None


class InvoiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    invoice_number: Optional[str] = None
    work_order_id: int
    customer_id: Optional[int] = None
    status: str
    subtotal: Decimal
    tax: Decimal
    total: Decimal
    notes: Optional[str] = None
    created_at: datetime
    items: List[InvoiceItemOut] = []


class InvoiceStatusUpdate(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str):
        vv = (v or "").strip().upper()
        if vv not in ALLOWED_INVOICE_STATUS:
            raise ValueError("Invalid status. Use: DRAFT, SENT, PAID, VOID")
        return vv

class InvoicePay(BaseModel):
    """
    Pago de invoice.
    - CASH: puede ser sin taxes si tú decides (regla de negocio en backend)
    - ZELLE / CARD: normalmente con taxes
    """
    payment_method: str = Field(..., description="CASH, ZELLE, CARD")
    amount_paid: Decimal = Field(default=Decimal("0.00"), ge=0)
    notes: Optional[str] = None

    @field_validator("payment_method")
    @classmethod
    def validate_payment_method(cls, v: str):
        vv = (v or "").strip().upper()
        if vv not in {"CASH", "ZELLE", "CARD"}:
            raise ValueError("Invalid payment_method. Use: CASH, ZELLE, CARD")
        return vv

class InvoiceItemPriceUpdate(BaseModel):
    qty: Optional[Decimal] = Field(default=None, gt=0)
    unit_price: Optional[Decimal] = Field(default=None, ge=0)


class PartsStoreCheckoutItem(BaseModel):
    item_id: int
    qty: Decimal = Field(default=Decimal("1.00"), gt=0)
    unit_price: Decimal = Field(default=Decimal("0.00"), ge=0)
    base_price: Optional[Decimal] = Field(default=Decimal("0.00"), ge=0)
    discount_percent: Decimal = Field(default=Decimal("0.00"), ge=0, le=15)
    price_mode: str = "NORMAL"
    manual_price: bool = False

    @field_validator("price_mode")
    @classmethod
    def validate_price_mode(cls, v: str):
        vv = (v or "NORMAL").strip().upper()
        if vv not in {"NORMAL", "DISC_5", "DISC_10", "DISC_15", "MANUAL"}:
            raise ValueError("Invalid price_mode. Use: NORMAL, DISC_5, DISC_10, DISC_15, MANUAL")
        return vv


class PartsStoreCheckoutPayload(BaseModel):
    document_type: str
    settlement_type: Optional[str] = None
    payment_method: Optional[str] = None
    cash_taxable: bool = True
    customer_mode: str
    customer_id: Optional[int] = None
    quick_customer: Optional[dict] = None
    notes: Optional[str] = None
    items: List[PartsStoreCheckoutItem] = Field(default_factory=list)

       
# ======================================================
# WORK ORDER OUT (al final para poder referenciar InvoiceOut)
# ======================================================
class WorkOrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    work_order_number: Optional[str] = None

    description: str

    customer_id: Optional[int] = None
    company_id: Optional[int] = None
    vehicle_id: Optional[int] = None
    mechanic_id: Optional[int] = None

    status: str
    created_at: datetime

    # ✅ joins para UI/PDF
    customer: Optional[CustomerOut] = None
    company: Optional[CompanyOut] = None
    vehicle: Optional[VehicleOut] = None
    mechanic: Optional[UserOut] = None

    # ✅ NUEVO: carrito de piezas
    items: List[WorkOrderItemOut] = Field(default_factory=list)

    # ✅ Labor lines
    labors: List[WorkOrderLaborOut] = Field(default_factory=list)

    # ✅ Invoice (si existe)
    invoice: Optional[InvoiceOut] = None


# ======================================================
# INVENTORY (NEW)
# ======================================================
# ✅ DB (models.py) exige: ('in','out','adjustment')
ALLOWED_MOVEMENT_TYPES = {"in", "out", "adjustment"}


# ---------- Supplier ----------
class SupplierBase(BaseModel):
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None
    is_active: bool = True


class SupplierCreate(SupplierBase):
    pass


class SupplierUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class SupplierOut(SupplierBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None


# ---------- Images ----------
class InventoryItemImageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    item_id: int
    image_url: str
    position: int
    is_primary: bool
    alt_text: Optional[str] = None
    created_at: datetime


class InventoryItemImageCreate(BaseModel):
    image_url: str = Field(..., min_length=10, max_length=500)
    position: int = 0
    is_primary: bool = False
    alt_text: Optional[str] = None


# ---------- Inventory Movement ----------
class InventoryMovementBase(BaseModel):
    item_id: int
    movement_type: str = Field(..., description="in, out, adjustment")
    quantity_moved: int = Field(..., gt=0, description="Debe ser > 0")

    # costo unitario para entradas (in)
    unit_cost: Optional[Decimal] = Field(None, ge=0)

    movement_date: Optional[datetime] = None

    user_id: Optional[int] = None
    related_job_id: Optional[int] = None
    movement_notes: Optional[str] = None

    @field_validator("movement_type")
    @classmethod
    def validate_movement_type(cls, v: str):
        """
        Acepta:
          - in/out/adjustment
          - IN/OUT/ADJUST
          - adjust/adj/adjustment
        Normaliza SIEMPRE a: in/out/adjustment (como exige DB)
        """
        raw = (v or "").strip()
        if raw == "":
            raise ValueError("movement_type is required")

        vv = raw.lower()

        if vv in {"in"}:
            return "in"
        if vv in {"out"}:
            return "out"
        if vv in {"adjustment", "adjust", "adj"}:
            return "adjustment"

        # por si llega "ADJUST" etc
        up = raw.strip().upper()
        if up == "IN":
            return "in"
        if up == "OUT":
            return "out"
        if up in {"ADJUST", "ADJUSTMENT"}:
            return "adjustment"

        raise ValueError("Invalid movement_type. Use: in, out, adjustment")


class InventoryMovementCreate(InventoryMovementBase):
    pass


class InventoryMovementOut(InventoryMovementBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    movement_date: datetime
    created_at: datetime


# ---------- Inventory Item ----------
class InventoryItemBase(BaseModel):
    part_code: str = Field(..., max_length=80)
    part_name: str = Field(..., max_length=180)

    description: Optional[str] = None
    brand: Optional[str] = None
    category: Optional[str] = None
    sub_category: Optional[str] = None
    barcode: Optional[str] = None
    oem_reference: Optional[str] = None

    engine_type: Optional[str] = None
    vehicle_make: Optional[str] = None
    vehicle_model: Optional[str] = None

    year_from: Optional[int] = None
    year_to: Optional[int] = None
    technical_notes: Optional[str] = None

    quantity_in_stock: int = 0
    minimum_stock: int = 0
    reorder_quantity: int = 0
    location: Optional[str] = None

    auto_reorder_enabled: bool = False
    critical_part: bool = False
    seasonal: bool = False

    cost_price: Decimal = Decimal("0.00")
    markup_percent: Optional[Decimal] = Decimal("0.00")
    sale_price_base: Decimal = Decimal("0.00")
    price_level_a: Optional[Decimal] = None
    price_level_b: Optional[Decimal] = None
    price_level_c: Optional[Decimal] = None
    taxable: bool = True

    supplier_id: Optional[int] = None
    supplier_part_number: Optional[str] = None
    lead_time_days: Optional[int] = None
    last_purchase_price: Optional[Decimal] = None
    last_purchase_date: Optional[date] = None

    average_monthly_usage: Optional[Decimal] = None
    last_used_date: Optional[date] = None
    times_sold: int = 0
    auto_reorder_last_run: Optional[datetime] = None

    editable_price: bool = False
    is_active: bool = True


class InventoryItemCreate(InventoryItemBase):
    created_by: Optional[int] = None


class InventoryItemUpdate(BaseModel):
    part_name: Optional[str] = None
    description: Optional[str] = None
    brand: Optional[str] = None
    category: Optional[str] = None
    sub_category: Optional[str] = None
    barcode: Optional[str] = None
    oem_reference: Optional[str] = None

    engine_type: Optional[str] = None
    vehicle_make: Optional[str] = None
    vehicle_model: Optional[str] = None
    year_from: Optional[int] = None
    year_to: Optional[int] = None
    technical_notes: Optional[str] = None

    quantity_in_stock: Optional[int] = None
    minimum_stock: Optional[int] = None
    reorder_quantity: Optional[int] = None
    location: Optional[str] = None

    auto_reorder_enabled: Optional[bool] = None
    critical_part: Optional[bool] = None
    seasonal: Optional[bool] = None

    cost_price: Optional[Decimal] = None
    sale_price_base: Optional[Decimal] = None
    price_level_a: Optional[Decimal] = None
    price_level_b: Optional[Decimal] = None
    price_level_c: Optional[Decimal] = None
    taxable: Optional[bool] = None

    supplier_id: Optional[int] = None
    supplier_part_number: Optional[str] = None
    lead_time_days: Optional[int] = None
    last_purchase_price: Optional[Decimal] = None
    last_purchase_date: Optional[date] = None

    average_monthly_usage: Optional[Decimal] = None
    last_used_date: Optional[date] = None
    times_sold: Optional[int] = None
    auto_reorder_last_run: Optional[datetime] = None

    editable_price: Optional[bool] = None
    is_active: Optional[bool] = None
    updated_by: Optional[int] = None


class InventoryItemOut(InventoryItemBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_by: Optional[int] = None
    updated_by: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None
    supplier: Optional[SupplierOut] = None


class InventoryItemOutFull(InventoryItemOut):
    model_config = ConfigDict(from_attributes=True)

    movements: List[InventoryMovementOut] = []
    images: List[InventoryItemImageOut] = []


# ======================================================
# INVENTORY (LEGACY - SKU)
# used by main.py endpoints: /inventory/items, /inventory/move, /inventory/stock
# ======================================================
class LegacyInventoryItemCreate(BaseModel):
    sku: str
    name: str
    description: Optional[str] = None
    unit: Optional[str] = "EA"
    cost: Optional[float] = None
    price: Optional[float] = None


class LegacyInventoryItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sku: str
    name: str
    description: Optional[str] = None
    unit: str
    cost: Optional[float] = None
    price: Optional[float] = None
    is_active: bool


class StockMoveCreate(BaseModel):
    item_id: int
    qty: float
    reason: Optional[str] = "ADJUST"
    note: Optional[str] = None


class StockMoveOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    item_id: int
    qty: float
    reason: str
    note: Optional[str] = None
    created_at: datetime


class InventoryStockOut(BaseModel):
    item_id: int
    sku: str
    name: str
    stock: float