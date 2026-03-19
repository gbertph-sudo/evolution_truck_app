
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from jose import jwt, JWTError
from passlib.context import CryptContext
from sqlalchemy.orm import Session

import models
import schemas
from database import Base, engine, get_db

from routers.invoices import router as invoices_router
from routers.inventory import router as inventory_router
from routers import companies, customers, vehicles
from routers import work_orders, parts_store

_ESTIMATES_QUOTES_AVAILABLE = False
try:
    from routers.estimates_quotes import router as estimates_quotes_router
    _ESTIMATES_QUOTES_AVAILABLE = True
except Exception:
    estimates_quotes_router = None


SECRET_KEY = "CHANGE_THIS_SECRET_KEY_NOW_123456789"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")

ROLE_SUPERADMIN = "SUPERADMIN"
ROLE_ADMIN = "ADMIN"
ROLE_SALES = "VENDEDOR"
ROLE_MECHANIC = "MECANICO"
ROLE_ACCOUNTANT = "ACCOUNTANT"

app = FastAPI(title="Evolution Truck API")

Base.metadata.create_all(bind=engine)

app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(invoices_router)
if _ESTIMATES_QUOTES_AVAILABLE and estimates_quotes_router is not None:
    app.include_router(estimates_quotes_router)

app.include_router(companies.router, prefix="/api")
app.include_router(customers.router, prefix="/api")
app.include_router(vehicles.router, prefix="/api")
app.include_router(work_orders.router)
app.include_router(parts_store.router, prefix="/api")
app.include_router(inventory_router, prefix="/api")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    return {
        "status": "ok",
        "time": datetime.utcnow().isoformat() + "Z",
        "quotes_router_loaded": _ESTIMATES_QUOTES_AVAILABLE,
    }

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
        "role": (
            {"id": u.role.id, "name": u.role.name}
            if getattr(u, "role", None) else None
        ),
    }

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
    return {
        "id": current_user.id,
        "username": current_user.username,
        "role": current_user.role.name if current_user.role else None,
    }

def require_roles(*allowed_roles: str):
    allowed = {r.strip().upper() for r in allowed_roles}
    def checker(user: models.User = Depends(get_current_user)) -> models.User:
        role_name = (user.role.name or "").upper() if user.role else ""
        if role_name not in allowed:
            raise HTTPException(
                status_code=403,
                detail=f"Not authorized. Required: {', '.join(sorted(allowed))}",
            )
        return user
    return checker

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
    ensure_role(db, ROLE_ACCOUNTANT)

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
    _ = user.role
    return user_to_out(user)

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

    role_name = user.role.name if user.role else None
    token = create_access_token(
        {"sub": str(user.id), "username": user.username, "role": role_name}
    )
    return schemas.Token(access_token=token)

@app.get("/roles", response_model=List[schemas.RoleOut])
def list_roles(
    _: models.User = Depends(require_roles(ROLE_SUPERADMIN, ROLE_ADMIN)),
    db: Session = Depends(get_db),
):
    return db.query(models.Role).order_by(models.Role.id).all()

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
    creator_role = (current_user.role.name or "").upper() if current_user.role else ""
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

@app.patch("/users/{user_id}", response_model=schemas.UserOut)
def update_user(
    user_id: int,
    payload: schemas.UserUpdate,
    current_user: models.User = Depends(require_roles(ROLE_SUPERADMIN, ROLE_ADMIN)),
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if payload.full_name is not None:
        user.full_name = payload.full_name

    if payload.email is not None:
        existing = db.query(models.User).filter(
            models.User.email == str(payload.email),
            models.User.id != user_id,
        ).first()
        if existing:
            raise HTTPException(status_code=409, detail="Email already exists")
        user.email = str(payload.email) if payload.email else None

    role_name = getattr(payload, "role_name", None)
    if role_name:
        role = db.query(models.Role).filter(models.Role.name == role_name.strip().upper()).first()
        if not role:
            raise HTTPException(status_code=422, detail="Invalid role_name")
        actor_role = (current_user.role.name or "").upper() if current_user.role else ""
        target_role = (role.name or "").upper()
        if actor_role == ROLE_ADMIN and target_role == ROLE_SUPERADMIN:
            raise HTTPException(status_code=403, detail="ADMIN cannot assign SUPERADMIN")
        user.role_id = role.id

    db.commit()
    db.refresh(user)
    _ = user.role
    return user_to_out(user)

@app.post("/users/{user_id}/set-active", response_model=schemas.UserOut)
def set_user_active(
    user_id: int,
    payload: schemas.UserSetActive,
    current_user: models.User = Depends(require_roles(ROLE_SUPERADMIN, ROLE_ADMIN)),
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    actor_role = (current_user.role.name or "").upper() if current_user.role else ""
    target_role = (user.role.name or "").upper() if user.role else ""
    if actor_role == ROLE_ADMIN and target_role == ROLE_SUPERADMIN:
        raise HTTPException(status_code=403, detail="ADMIN cannot modify SUPERADMIN")

    user.is_active = bool(payload.is_active)
    db.commit()
    db.refresh(user)
    _ = user.role
    return user_to_out(user)

@app.post("/users/{user_id}/reset-password")
def reset_user_password(
    user_id: int,
    payload: schemas.UserPasswordReset,
    current_user: models.User = Depends(require_roles(ROLE_SUPERADMIN, ROLE_ADMIN)),
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    actor_role = (current_user.role.name or "").upper() if current_user.role else ""
    target_role = (user.role.name or "").upper() if user.role else ""
    if actor_role == ROLE_ADMIN and target_role == ROLE_SUPERADMIN:
        raise HTTPException(status_code=403, detail="ADMIN cannot reset SUPERADMIN password")

    user.password_hash = get_password_hash(payload.new_password)
    db.commit()
    return {"ok": True, "message": "Password updated successfully"}
