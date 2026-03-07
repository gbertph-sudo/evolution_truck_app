# main.py
from __future__ import annotations

from routers.invoices import router as invoices_router  # ✅ FIX

from datetime import datetime, timedelta
from typing import Optional, List
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from jose import jwt, JWTError
from passlib.context import CryptContext

import models
import schemas
from database import Base, engine, get_db

# Router del inventario NUEVO (inventory.html + inventory.js -> /api/...)
from routers.inventory import router as inventory_router

from routers import companies, customers, vehicles
from routers import work_orders


# ======================================================
# CONFIG
# ======================================================
SECRET_KEY = "CHANGE_THIS_SECRET_KEY_NOW_123456789"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 1 day

# IMPORTANTE: tu BD YA TIENE hashes pbkdf2_sha256
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")

ROLE_SUPERADMIN = "SUPERADMIN"
ROLE_ADMIN = "ADMIN"
ROLE_SALES = "VENDEDOR"
ROLE_MECHANIC = "MECANICO"


# ======================================================
# APP
# ======================================================
app = FastAPI(title="Evolution Truck API")

Base.metadata.create_all(bind=engine)

app.mount("/static", StaticFiles(directory="static"), name="static")

# Todo lo nuevo de UI bajo /api
app.include_router(invoices_router)  # ✅ FIX
app.include_router(companies.router, prefix="/api")
app.include_router(customers.router, prefix="/api")
app.include_router(vehicles.router, prefix="/api")
app.include_router(work_orders.router)

app.include_router(inventory_router, prefix="/api")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # en producción: pon tu dominio o IP
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ======================================================
# PAGES (HTML)
# ======================================================
@app.get("/")
def home():
    return FileResponse("static/index.html")


@app.get("/dashboard.html")
def dashboard_html():
    return FileResponse("static/dashboard.html")


@app.get("/test")
def test():
    return {"status": "ok", "message": "Backend connected successfully"}


@app.get("/api/health")
def api_health():
    return {"status": "ok", "time": datetime.utcnow().isoformat() + "Z"}


# ======================================================
# HELPERS
# ======================================================
def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def ensure_role(db: Session, name: str) -> models.Role:
    name = name.strip().upper()
    role = db.query(models.Role).filter(models.Role.name == name).first()
    if not role:
        role = models.Role(name=name)
        db.add(role)
        db.commit()
        db.refresh(role)
    return role


def get_role_from_payload(db: Session, role_id: Optional[int], role_name: Optional[str]) -> Optional[models.Role]:
    role = None
    if role_id is not None:
        role = db.query(models.Role).filter(models.Role.id == role_id).first()
    if role is None and role_name:
        role = db.query(models.Role).filter(models.Role.name == role_name.strip().upper()).first()
    return role


def user_to_out(u: models.User) -> dict:
    return {
        "id": u.id,
        "username": u.username,
        "email": u.email,
        "full_name": u.full_name,
        "is_active": u.is_active,
        "role_id": u.role_id,
        "role_name": (u.role.name if getattr(u, "role", None) else None),
    }


def customer_to_out(c: models.Customer) -> dict:
    """
    ✅ Devuelve CustomerOut con companies y company_ids
    """
    comps = list(getattr(c, "companies", []) or [])
    return {
        "id": c.id,
        "name": c.name,
        "phone": c.phone,
        "email": c.email,
        "companies": [{"id": x.id, "name": x.name} for x in comps],
        "company_ids": [x.id for x in comps],
        "created_at": getattr(c, "created_at", None),
        "updated_at": getattr(c, "updated_at", None),
    }


# ======================================================
# AUTH DEPENDENCIES (🔒)
# ======================================================
def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> models.User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(models.User).filter(models.User.id == int(user_id)).first()
    if not user:
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(status_code=403, detail="User is inactive")

    return user


@app.get("/auth/me")
def read_me(current_user: models.User = Depends(get_current_user)):
    return {"id": current_user.id, "username": current_user.username, "role": current_user.role.name}


def require_roles(*allowed_roles: str):
    allowed = {r.strip().upper() for r in allowed_roles}

    def checker(user: models.User = Depends(get_current_user)) -> models.User:
        role_name = (user.role.name or "").upper()
        if role_name not in allowed:
            raise HTTPException(
                status_code=403,
                detail=f"Not authorized. Required: {', '.join(sorted(allowed))}",
            )
        return user

    return checker


# ======================================================
# AUTH / BOOTSTRAP (SIN 🔒)
# ======================================================
@app.post("/auth/bootstrap-superadmin", response_model=schemas.UserOut)
def bootstrap_superadmin(
    payload: schemas.BootstrapSuperAdminSchema,
    db: Session = Depends(get_db),
):
    existing_sa = (
        db.query(models.User)
        .join(models.Role)
        .filter(models.Role.name == ROLE_SUPERADMIN)
        .first()
    )
    if existing_sa:
        raise HTTPException(status_code=403, detail="Superadmin already exists. Bootstrap disabled.")

    role_sa = ensure_role(db, ROLE_SUPERADMIN)
    ensure_role(db, ROLE_ADMIN)
    ensure_role(db, ROLE_SALES)
    ensure_role(db, ROLE_MECHANIC)

    user = models.User(
        username=payload.username.strip(),
        email=str(payload.email) if payload.email else None,
        full_name=payload.full_name,
        password_hash=get_password_hash(payload.password),
        role_id=role_sa.id,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@app.post("/auth/token", response_model=schemas.Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(models.User.username == form_data.username).first()

    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="User is inactive")

    token = create_access_token({"sub": str(user.id), "username": user.username, "role": user.role.name})
    return schemas.Token(access_token=token)


# ======================================================
# ROLES (🔒 SUPERADMIN/ADMIN)
# ======================================================
@app.get("/roles", response_model=List[schemas.RoleOut])
def list_roles(
    _: models.User = Depends(require_roles(ROLE_SUPERADMIN, ROLE_ADMIN)),
    db: Session = Depends(get_db),
):
    return db.query(models.Role).order_by(models.Role.id).all()


# ======================================================
# USERS (🔒 SUPERADMIN/ADMIN)
# ======================================================
@app.get("/users", response_model=List[schemas.UserOut])
def list_users(
    _: models.User = Depends(require_roles(ROLE_SUPERADMIN, ROLE_ADMIN)),
    db: Session = Depends(get_db),
):
    users = db.query(models.User).order_by(models.User.id).all()
    return [user_to_out(u) for u in users]


@app.post("/users", response_model=schemas.UserOut)
def create_user(
    payload: schemas.UserCreate,
    current_user: models.User = Depends(require_roles(ROLE_SUPERADMIN, ROLE_ADMIN)),
    db: Session = Depends(get_db),
):
    if db.query(models.User).filter(models.User.username == payload.username).first():
        raise HTTPException(status_code=409, detail="Username already exists")

    if payload.email:
        if db.query(models.User).filter(models.User.email == str(payload.email)).first():
            raise HTTPException(status_code=409, detail="Email already exists")

    role = get_role_from_payload(db, getattr(payload, "role_id", None), getattr(payload, "role_name", None))
    if not role:
        raise HTTPException(status_code=422, detail="Invalid role. Use an existing role_id or role_name.")

    target_role = (role.name or "").upper()
    creator_role = (current_user.role.name or "").upper()

    if creator_role == ROLE_ADMIN and target_role == ROLE_SUPERADMIN:
        raise HTTPException(status_code=403, detail="ADMIN cannot create SUPERADMIN")

    user = models.User(
        username=payload.username.strip(),
        full_name=payload.full_name,
        email=str(payload.email) if payload.email else None,
        password_hash=get_password_hash(payload.password),
        role_id=role.id,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    _ = user.role
    return user_to_out(user)


@app.patch("/users/{user_id}/password", response_model=schemas.UserOut)
def admin_reset_password(
    user_id: int,
    payload: schemas.UserPasswordReset,
    _: models.User = Depends(require_roles(ROLE_SUPERADMIN, ROLE_ADMIN)),
    db: Session = Depends(get_db),
):
    if not payload.new_password or len(payload.new_password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    u = db.query(models.User).filter(models.User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")

    u.password_hash = get_password_hash(payload.new_password)
    db.commit()
    db.refresh(u)

    _ = u.role
    return user_to_out(u)


# ======================================================
# COMPANIES
# ======================================================
@app.get("/companies", response_model=List[schemas.CompanyOut])
def list_companies(
    _: models.User = Depends(require_roles(ROLE_SUPERADMIN, ROLE_ADMIN, ROLE_SALES)),
    db: Session = Depends(get_db),
):
    return db.query(models.Company).order_by(models.Company.id).all()


@app.post("/companies", response_model=schemas.CompanyOut)
def create_company(
    payload: schemas.CompanyCreate,
    _: models.User = Depends(require_roles(ROLE_SUPERADMIN, ROLE_ADMIN)),
    db: Session = Depends(get_db),
):
    name = (payload.name or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="Company name is required")

    existing = db.query(models.Company).filter(models.Company.name == name).first()
    if existing:
        return existing

    company = models.Company(name=name)
    db.add(company)
    db.commit()
    db.refresh(company)
    return company


# ======================================================
# CUSTOMERS ✅ many-to-many
# ======================================================
@app.get("/customers", response_model=List[schemas.CustomerOut])
def list_customers(
    _: models.User = Depends(require_roles(ROLE_SUPERADMIN, ROLE_ADMIN, ROLE_SALES)),
    db: Session = Depends(get_db),
):
    customers = db.query(models.Customer).order_by(models.Customer.id).all()
    return [customer_to_out(c) for c in customers]


@app.post("/customers", response_model=schemas.CustomerOut)
def create_customer(
    payload: schemas.CustomerCreate,
    _: models.User = Depends(require_roles(ROLE_SUPERADMIN, ROLE_ADMIN, ROLE_SALES)),
    db: Session = Depends(get_db),
):
    name = (payload.name or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="Customer name is required")

    # ✅ Validar companies por IDs
    company_ids = payload.company_ids or []
    companies: List[models.Company] = []
    if company_ids:
        companies = db.query(models.Company).filter(models.Company.id.in_(company_ids)).all()
        found_ids = {c.id for c in companies}
        missing = [cid for cid in company_ids if cid not in found_ids]
        if missing:
            raise HTTPException(status_code=422, detail=f"Invalid company_ids: {missing}")

    customer = models.Customer(
        name=name,
        phone=payload.phone,
        email=str(payload.email) if payload.email else None,
    )

    # ✅ asignar companies (many-to-many)
    if hasattr(customer, "companies"):
        customer.companies = companies

    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer_to_out(customer)


@app.patch("/customers/{customer_id}", response_model=schemas.CustomerOut)
def update_customer(
    customer_id: int,
    payload: schemas.CustomerUpdate,
    _: models.User = Depends(require_roles(ROLE_SUPERADMIN, ROLE_ADMIN, ROLE_SALES)),
    db: Session = Depends(get_db),
):
    c = db.query(models.Customer).filter(models.Customer.id == customer_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Customer not found")

    if payload.name is not None:
        nm = payload.name.strip()
        if not nm:
            raise HTTPException(status_code=422, detail="Customer name cannot be empty")
        c.name = nm

    if payload.phone is not None:
        c.phone = payload.phone

    if payload.email is not None:
        c.email = str(payload.email) if payload.email else None

    # ✅ reemplazar lista completa de companies si viene
    if payload.company_ids is not None:
        ids = payload.company_ids or []
        companies: List[models.Company] = []
        if ids:
            companies = db.query(models.Company).filter(models.Company.id.in_(ids)).all()
            found = {x.id for x in companies}
            missing = [cid for cid in ids if cid not in found]
            if missing:
                raise HTTPException(status_code=422, detail=f"Invalid company_ids: {missing}")

        if not hasattr(c, "companies"):
            raise HTTPException(status_code=500, detail="Customer.companies relationship not configured")

        c.companies = companies

    db.commit()
    db.refresh(c)
    return customer_to_out(c)


@app.post("/customers/{customer_id}/companies/{company_id}", response_model=schemas.CustomerOut)
def add_company_to_customer(
    customer_id: int,
    company_id: int,
    _: models.User = Depends(require_roles(ROLE_SUPERADMIN, ROLE_ADMIN, ROLE_SALES)),
    db: Session = Depends(get_db),
):
    c = db.query(models.Customer).filter(models.Customer.id == customer_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Customer not found")

    comp = db.query(models.Company).filter(models.Company.id == company_id).first()
    if not comp:
        raise HTTPException(status_code=404, detail="Company not found")

    if not hasattr(c, "companies"):
        raise HTTPException(status_code=500, detail="Customer.companies relationship not configured")

    # evita duplicado
    if all(x.id != comp.id for x in c.companies):
        c.companies.append(comp)

    db.commit()
    db.refresh(c)
    return customer_to_out(c)


@app.delete("/customers/{customer_id}/companies/{company_id}", response_model=schemas.CustomerOut)
def remove_company_from_customer(
    customer_id: int,
    company_id: int,
    _: models.User = Depends(require_roles(ROLE_SUPERADMIN, ROLE_ADMIN, ROLE_SALES)),
    db: Session = Depends(get_db),
):
    c = db.query(models.Customer).filter(models.Customer.id == customer_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Customer not found")

    if not hasattr(c, "companies"):
        raise HTTPException(status_code=500, detail="Customer.companies relationship not configured")

    c.companies = [x for x in c.companies if x.id != company_id]

    db.commit()
    db.refresh(c)
    return customer_to_out(c)


# ======================================================
# VEHICLES
# ======================================================
@app.get("/vehicles", response_model=List[schemas.VehicleOut])
def list_vehicles(
    _: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return db.query(models.Vehicle).order_by(models.Vehicle.id).all()


@app.post("/vehicles", response_model=schemas.VehicleOut)
def create_vehicle(
    payload: schemas.VehicleCreate,
    _: models.User = Depends(require_roles(ROLE_SUPERADMIN, ROLE_ADMIN, ROLE_SALES)),
    db: Session = Depends(get_db),
):
    if payload.customer_id is not None:
        cust = db.query(models.Customer).filter(models.Customer.id == payload.customer_id).first()
        if not cust:
            raise HTTPException(status_code=422, detail="customer_id does not exist")

    vin = payload.vin.strip().upper() if payload.vin else None
    if vin:
        exists = db.query(models.Vehicle).filter(models.Vehicle.vin == vin).first()
        if exists:
            raise HTTPException(status_code=409, detail="VIN already exists")

    vehicle = models.Vehicle(
        vin=vin,
        unit_number=payload.unit_number,
        make=payload.make,
        model=payload.model,
        year=payload.year,
        customer_id=payload.customer_id,
    )
    db.add(vehicle)
    db.commit()
    db.refresh(vehicle)
    return vehicle


# ======================================================
# WORK ORDERS
# ======================================================
@app.get("/work-orders", response_model=List[schemas.WorkOrderOut])
def list_work_orders(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    role = (current_user.role.name or "").upper()
    q = db.query(models.WorkOrder).order_by(models.WorkOrder.id.desc())

    if role == ROLE_MECHANIC:
        q = q.filter(models.WorkOrder.mechanic_id == current_user.id)

    return q.all()


@app.post("/work-orders", response_model=schemas.WorkOrderOut)
def create_work_order(
    payload: schemas.WorkOrderCreate,
    _: models.User = Depends(require_roles(ROLE_SUPERADMIN, ROLE_ADMIN, ROLE_SALES)),
    db: Session = Depends(get_db),
):
    if payload.customer_id is not None:
        cust = db.query(models.Customer).filter(models.Customer.id == payload.customer_id).first()
        if not cust:
            raise HTTPException(status_code=422, detail="customer_id does not exist")

    if payload.vehicle_id is not None:
        veh = db.query(models.Vehicle).filter(models.Vehicle.id == payload.vehicle_id).first()
        if not veh:
            raise HTTPException(status_code=422, detail="vehicle_id does not exist")

    if payload.mechanic_id is not None:
        mech = db.query(models.User).filter(models.User.id == payload.mechanic_id).first()
        if not mech:
            raise HTTPException(status_code=422, detail="mechanic_id does not exist")

        mech_role = (mech.role.name or "").upper()
        if mech_role != ROLE_MECHANIC:
            raise HTTPException(status_code=422, detail="mechanic_id must be a user with MECANICO role")

    status_value = (payload.status or "OPEN").strip().upper()
    allowed_status = {"OPEN", "IN_PROGRESS", "DONE", "CANCELLED"}
    if status_value not in allowed_status:
        raise HTTPException(status_code=422, detail="Invalid status. Use: OPEN, IN_PROGRESS, DONE, CANCELLED")

    wo = models.WorkOrder(
        description=payload.description.strip(),
        customer_id=payload.customer_id,
        vehicle_id=payload.vehicle_id,
        mechanic_id=payload.mechanic_id,
        status=status_value,
    )
    db.add(wo)
    db.commit()
    db.refresh(wo)
    return wo


@app.put("/work-orders/{work_order_id}/status")
def update_work_order_status(
    work_order_id: int,
    payload: schemas.WorkOrderStatusUpdate,
    _: models.User = Depends(require_roles(ROLE_SUPERADMIN, ROLE_ADMIN, ROLE_MECHANIC)),
    db: Session = Depends(get_db),
):
    wo = db.query(models.WorkOrder).filter(models.WorkOrder.id == work_order_id).first()
    if not wo:
        raise HTTPException(status_code=404, detail="Work order not found")

    wo.status = payload.status
    if hasattr(wo, "updated_at"):
        wo.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(wo)
    return {"id": wo.id, "status": wo.status}


# ======================================================
# INVOICES
# ======================================================
def recalc_invoice_totals(inv: models.Invoice):
    subtotal = Decimal("0")
    for it in inv.items:
        subtotal += Decimal(str(it.line_total))
    inv.subtotal = subtotal
    inv.tax = Decimal("0")
    inv.total = inv.subtotal + inv.tax


@app.post("/invoices/from-work-order/{work_order_id}", response_model=schemas.InvoiceOut)
def create_invoice_from_work_order(
    work_order_id: int,
    payload: schemas.InvoiceCreateFromWorkOrder,
    _: models.User = Depends(require_roles(ROLE_SUPERADMIN, ROLE_ADMIN, ROLE_SALES)),
    db: Session = Depends(get_db),
):
    wo = db.query(models.WorkOrder).filter(models.WorkOrder.id == work_order_id).first()
    if not wo:
        raise HTTPException(status_code=404, detail="Work order not found")

    existing = db.query(models.Invoice).filter(models.Invoice.work_order_id == work_order_id).first()
    if existing:
        return existing

    inv = models.Invoice(
        work_order_id=work_order_id,
        customer_id=wo.customer_id,
        status="DRAFT",
        notes=payload.notes,
    )
    db.add(inv)
    db.commit()
    db.refresh(inv)

    inv.invoice_number = f"INV-{inv.id:06d}"
    db.commit()
    db.refresh(inv)

    return inv


@app.get("/invoices", response_model=List[schemas.InvoiceOut])
def list_invoices(
    _: models.User = Depends(require_roles(ROLE_SUPERADMIN, ROLE_ADMIN, ROLE_SALES)),
    db: Session = Depends(get_db),
):
    return db.query(models.Invoice).order_by(models.Invoice.id.desc()).all()


@app.get("/invoices/{invoice_id}", response_model=schemas.InvoiceOut)
def get_invoice(
    invoice_id: int,
    _: models.User = Depends(require_roles(ROLE_SUPERADMIN, ROLE_ADMIN, ROLE_SALES)),
    db: Session = Depends(get_db),
):
    inv = db.query(models.Invoice).filter(models.Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return inv


@app.post("/invoices/{invoice_id}/items", response_model=schemas.InvoiceOut)
def add_invoice_item(
    invoice_id: int,
    payload: schemas.InvoiceItemCreate,
    _: models.User = Depends(require_roles(ROLE_SUPERADMIN, ROLE_ADMIN, ROLE_SALES)),
    db: Session = Depends(get_db),
):
    inv = db.query(models.Invoice).filter(models.Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if inv.status in {"PAID", "VOID"}:
        raise HTTPException(status_code=409, detail="Cannot modify a PAID/VOID invoice")

    qty = Decimal(str(payload.qty))
    unit_price = Decimal(str(payload.unit_price))
    line_total = qty * unit_price

    item = models.InvoiceItem(
        invoice_id=invoice_id,
        item_type=payload.item_type,
        description=payload.description.strip(),
        qty=qty,
        unit_price=unit_price,
        line_total=line_total,
    )
    db.add(item)
    db.commit()

    db.refresh(inv)
    recalc_invoice_totals(inv)
    db.commit()
    db.refresh(inv)
    return inv


@app.put("/invoices/{invoice_id}/status", response_model=schemas.InvoiceOut)
def update_invoice_status(
    invoice_id: int,
    payload: schemas.InvoiceStatusUpdate,
    _: models.User = Depends(require_roles(ROLE_SUPERADMIN, ROLE_ADMIN)),
    db: Session = Depends(get_db),
):
    inv = db.query(models.Invoice).filter(models.Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")

    inv.status = payload.status
    db.commit()
    db.refresh(inv)
    return inv


# ======================================================
# INVENTORY (LEGACY)  ✅ ARREGLADO para tus models actuales
# - usa LegacyInventoryItem + LegacyStockMovement
# ======================================================
@app.post("/inventory/items", response_model=schemas.LegacyInventoryItemOut)
def create_inventory_item(
    payload: schemas.LegacyInventoryItemCreate,
    _: models.User = Depends(require_roles(ROLE_SUPERADMIN, ROLE_ADMIN)),
    db: Session = Depends(get_db),
):
    sku = (payload.sku or "").strip().upper()
    if not sku:
        raise HTTPException(status_code=422, detail="sku is required")

    if db.query(models.LegacyInventoryItem).filter(models.LegacyInventoryItem.sku == sku).first():
        raise HTTPException(status_code=409, detail="SKU already exists")

    item = models.LegacyInventoryItem(
        sku=sku,
        name=payload.name.strip(),
        description=payload.description,
        unit=(payload.unit or "EA").strip().upper(),
        cost=payload.cost,
        price=payload.price,
        is_active=True,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@app.get("/inventory/items", response_model=List[schemas.LegacyInventoryItemOut])
def list_inventory_items(
    _: models.User = Depends(require_roles(ROLE_SUPERADMIN, ROLE_ADMIN)),
    db: Session = Depends(get_db),
):
    return db.query(models.LegacyInventoryItem).order_by(models.LegacyInventoryItem.id).all()


@app.post("/inventory/move", response_model=schemas.StockMoveOut)
def move_stock(
    payload: schemas.StockMoveCreate,
    _: models.User = Depends(require_roles(ROLE_SUPERADMIN, ROLE_ADMIN)),
    db: Session = Depends(get_db),
):
    item = db.query(models.LegacyInventoryItem).filter(models.LegacyInventoryItem.id == payload.item_id).first()
    if not item:
        raise HTTPException(status_code=422, detail="item_id does not exist")

    mv = models.LegacyStockMovement(
        item_id=item.id,
        qty=Decimal(str(payload.qty)),
        reason=(payload.reason or "ADJUST").strip().upper(),
        note=payload.note,
    )
    db.add(mv)
    db.commit()
    db.refresh(mv)
    return mv


@app.get("/inventory/stock", response_model=List[schemas.InventoryStockOut])
def get_stock(
    _: models.User = Depends(require_roles(ROLE_SUPERADMIN, ROLE_ADMIN)),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(
            models.LegacyInventoryItem.id.label("item_id"),
            models.LegacyInventoryItem.sku,
            models.LegacyInventoryItem.name,
            func.coalesce(func.sum(models.LegacyStockMovement.qty), 0).label("stock"),
        )
        .outerjoin(models.LegacyStockMovement, models.LegacyStockMovement.item_id == models.LegacyInventoryItem.id)
        .group_by(models.LegacyInventoryItem.id)
        .order_by(models.LegacyInventoryItem.id)
        .all()
    )

    return [
        schemas.InventoryStockOut(
            item_id=r.item_id,
            sku=r.sku,
            name=r.name,
            stock=float(r.stock or 0),
        )
        for r in rows
    ]
