from __future__ import annotations

# models.py
# Comentarios en español. Nombres en inglés.

from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List

from sqlalchemy import (
    String, Integer, DateTime, Date, Boolean, ForeignKey,
    Text, Numeric, CheckConstraint, Index, UniqueConstraint,
    Table, Column
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


# ======================================================
# AUTH
# ======================================================
class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)

    users: Mapped[List["User"]] = relationship("User", back_populates="role")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    full_name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(120), unique=True, nullable=True, index=True)

    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), nullable=False, index=True)
    role: Mapped["Role"] = relationship("Role", back_populates="users")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


# ======================================================
# COMPANIES / CUSTOMERS / VEHICLES
# ======================================================
customer_companies = Table(
    "customer_companies",
    Base.metadata,
    Column("customer_id", ForeignKey("customers.id", ondelete="CASCADE"), primary_key=True, nullable=False),
    Column("company_id", ForeignKey("companies.id", ondelete="CASCADE"), primary_key=True, nullable=False),
    Index("ix_customer_companies_customer_id", "customer_id"),
    Index("ix_customer_companies_company_id", "company_id"),
)


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true", index=True)

    customers: Mapped[List["Customer"]] = relationship(
        "Customer",
        secondary=customer_companies,
        back_populates="companies",
        passive_deletes=True,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true", index=True)

    companies: Mapped[List["Company"]] = relationship(
        "Company",
        secondary=customer_companies,
        back_populates="customers",
        passive_deletes=True,
    )

    vehicles: Mapped[List["Vehicle"]] = relationship(
        "Vehicle",
        back_populates="customer",
        passive_deletes=True,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class Vehicle(Base):
    __tablename__ = "vehicles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    vin: Mapped[Optional[str]] = mapped_column(String(17), unique=True, nullable=True, index=True)
    unit_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    make: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true", index=True)

    customer_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("customers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    customer: Mapped[Optional["Customer"]] = relationship("Customer", back_populates="vehicles")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


# ======================================================
# WORK ORDERS
# ======================================================
class WorkOrder(Base):
    __tablename__ = "work_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    work_order_number: Mapped[Optional[str]] = mapped_column(String(30), unique=True, nullable=True, index=True)

    customer_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("customers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    company_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    vehicle_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("vehicles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    mechanic_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True, default="OPEN")
    description: Mapped[str] = mapped_column(String(1000), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    customer: Mapped[Optional["Customer"]] = relationship("Customer")
    company: Mapped[Optional["Company"]] = relationship("Company")
    vehicle: Mapped[Optional["Vehicle"]] = relationship("Vehicle")
    mechanic: Mapped[Optional["User"]] = relationship("User")

    invoice: Mapped[Optional["Invoice"]] = relationship(
        "Invoice",
        back_populates="work_order",
        uselist=False,
        cascade="all, delete-orphan",
    )

    items: Mapped[List["WorkOrderItem"]] = relationship(
        "WorkOrderItem",
        back_populates="work_order",
        cascade="all, delete-orphan",
    )

    labors: Mapped[List["WorkOrderLabor"]] = relationship(
        "WorkOrderLabor",
        back_populates="work_order",
        cascade="all, delete-orphan",
    )


class WorkOrderItem(Base):
    __tablename__ = "work_order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    work_order_id: Mapped[int] = mapped_column(
        ForeignKey("work_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    inventory_item_id: Mapped[int] = mapped_column(
        ForeignKey("inventory_items.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    description_snapshot: Mapped[str] = mapped_column(String(255), nullable=False)
    qty: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("1.00"))
    unit_price_snapshot: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    line_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    cost_snapshot = Column(Numeric(12, 2), nullable=False, server_default="0")

    added_by_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    work_order: Mapped["WorkOrder"] = relationship("WorkOrder", back_populates="items")
    inventory_item: Mapped["InventoryItem"] = relationship("InventoryItem")
    added_by: Mapped[Optional["User"]] = relationship("User")

    @property
    def part_code(self) -> Optional[str]:
        inv = getattr(self, "inventory_item", None)
        return getattr(inv, "part_code", None) if inv else None


class WorkOrderLabor(Base):
    __tablename__ = "work_order_labors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    work_order_id: Mapped[int] = mapped_column(
        ForeignKey("work_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    mechanic_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    mechanic_name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    hours: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    rate: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    line_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    work_order: Mapped["WorkOrder"] = relationship("WorkOrder", back_populates="labors")
    mechanic: Mapped[Optional["User"]] = relationship("User")


# ======================================================
# INVOICES
# ======================================================
class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    invoice_number: Mapped[Optional[str]] = mapped_column(String(30), unique=True, nullable=True, index=True)

    work_order_id: Mapped[int] = mapped_column(
        ForeignKey("work_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    customer_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("customers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT", index=True)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    tax: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    payment_method: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)
    processing_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, server_default="0.00")
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Quotes / lifecycle
    document_type: Mapped[str] = mapped_column(String(20), nullable=False, default="SALE", index=True)
    settlement_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
    converted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    inventory_applied: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    quote_origin: Mapped[Optional[str]] = mapped_column(String(30), nullable=True, index=True)

    work_order: Mapped["WorkOrder"] = relationship("WorkOrder", back_populates="invoice")
    customer: Mapped[Optional["Customer"]] = relationship("Customer")
    items: Mapped[List["InvoiceItem"]] = relationship(
        "InvoiceItem",
        back_populates="invoice",
        cascade="all, delete-orphan",
    )


class InvoiceItem(Base):
    __tablename__ = "invoice_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True)
    inventory_item_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("inventory_items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    work_order_item_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("work_order_items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    item_type: Mapped[str] = mapped_column(String(20), nullable=False, default="LABOR", index=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    qty: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("1.00"))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    line_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    cost_snapshot: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, server_default="0.00")

    invoice: Mapped["Invoice"] = relationship("Invoice", back_populates="items")
    inventory_item: Mapped[Optional["InventoryItem"]] = relationship("InventoryItem")
    work_order_item: Mapped[Optional["WorkOrderItem"]] = relationship("WorkOrderItem")

    @property
    def part_code(self) -> Optional[str]:
        inv = getattr(self, "inventory_item", None)
        return getattr(inv, "part_code", None) if inv else None


# ======================================================
# INVENTORY
# ======================================================
class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    phone: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    items: Mapped[List["InventoryItem"]] = relationship("InventoryItem", back_populates="supplier")


class InventoryItem(Base):
    __tablename__ = "inventory_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    part_code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    part_name: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    brand: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, index=True)
    category: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, index=True)
    sub_category: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, index=True)

    barcode: Mapped[Optional[str]] = mapped_column(String(80), nullable=True, index=True)
    oem_reference: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, index=True)

    engine_type: Mapped[Optional[str]] = mapped_column(String(80), nullable=True, index=True)
    vehicle_make: Mapped[Optional[str]] = mapped_column(String(80), nullable=True, index=True)
    vehicle_model: Mapped[Optional[str]] = mapped_column(String(80), nullable=True, index=True)
    year_from: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    year_to: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    technical_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    quantity_in_stock: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    minimum_stock: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reorder_quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    location: Mapped[Optional[str]] = mapped_column(String(80), nullable=True, index=True)

    auto_reorder_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    critical_part: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    seasonal: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    cost_price: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        default=Decimal("0.00"),
        nullable=False
    )

    markup_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        default=Decimal("0.00"),
        nullable=False
    )

    sale_price_base: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        default=Decimal("0.00"),
        nullable=False
    )
    price_level_a: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    price_level_b: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    price_level_c: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    taxable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    supplier_id: Mapped[Optional[int]] = mapped_column(ForeignKey("suppliers.id"), nullable=True, index=True)
    supplier_part_number: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    lead_time_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    last_purchase_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    last_purchase_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    average_monthly_usage: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    last_used_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    times_sold: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    auto_reorder_last_run: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    created_by: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    updated_by: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    editable_price: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    supplier: Mapped[Optional["Supplier"]] = relationship("Supplier", back_populates="items")
    movements: Mapped[List["InventoryMovement"]] = relationship(
        "InventoryMovement", back_populates="item", cascade="all, delete-orphan"
    )
    images: Mapped[List["InventoryItemImage"]] = relationship(
        "InventoryItemImage", back_populates="item", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("part_code", name="uq_inventory_part_code"),
        CheckConstraint("quantity_in_stock >= 0", name="ck_inventory_qty_nonneg"),
        CheckConstraint("minimum_stock >= 0", name="ck_inventory_min_nonneg"),
        CheckConstraint("reorder_quantity >= 0", name="ck_inventory_reorder_nonneg"),
        CheckConstraint("cost_price >= 0", name="ck_inventory_cost_nonneg"),
        CheckConstraint("sale_price_base >= 0", name="ck_inventory_sale_nonneg"),
        CheckConstraint("(year_from is null) or (year_from >= 1900)", name="ck_inventory_year_from"),
        CheckConstraint("(year_to is null) or (year_to >= 1900)", name="ck_inventory_year_to"),
        Index("ix_inventory_search", "part_name", "brand", "category", "sub_category"),
    )


class InventoryMovement(Base):
    __tablename__ = "inventory_movements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("inventory_items.id"), nullable=False, index=True)

    movement_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)  # in|out|adjustment
    quantity_moved: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_cost: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    movement_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    related_job_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    movement_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    item: Mapped["InventoryItem"] = relationship("InventoryItem", back_populates="movements")

    __table_args__ = (
        CheckConstraint("quantity_moved != 0", name="ck_movement_qty_not_zero"),
        CheckConstraint("movement_type in ('in','out','adjustment')", name="ck_movement_type_valid"),
        CheckConstraint("(unit_cost is null) or (unit_cost >= 0)", name="ck_movement_unit_cost_nonneg"),
        Index("ix_movement_item_date", "item_id", "movement_date"),
        Index("ix_movement_type_date", "movement_type", "movement_date"),
    )


class InventoryItemImage(Base):
    __tablename__ = "inventory_item_images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("inventory_items.id"), nullable=False, index=True)

    image_url: Mapped[str] = mapped_column(String(500), nullable=False)
    alt_text: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    item: Mapped["InventoryItem"] = relationship("InventoryItem", back_populates="images")
