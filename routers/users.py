from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

import models
import schemas
from database import get_db
from security import hash_password
from auth import get_current_user   # <-- importa tu dependencia real

router = APIRouter(prefix="/api", tags=["users"])

def user_to_out(u: models.User) -> schemas.UserOut:
    return schemas.UserOut(
        id=u.id,
        username=u.username,
        full_name=u.full_name,
        email=u.email,
        role_name=u.role.name if u.role else "",
        is_active=u.is_active,
    )

def require_admin(current_user: models.User = Depends(get_current_user)):
    role = (current_user.role.name if current_user and current_user.role else "").lower()
    if role not in ("admin", "superadmin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    return current_user

@router.get("/roles", response_model=List[schemas.RoleOut])
def list_roles(
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin)  # <-- admin only
):
    return db.query(models.Role).order_by(models.Role.id.asc()).all()

@router.get("/users", response_model=List[schemas.UserOut])
def list_users(
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin)  # <-- admin only
):
    users = db.query(models.User).order_by(models.User.id.desc()).all()
    return [user_to_out(u) for u in users]

@router.post("/users", response_model=schemas.UserOut, status_code=201)
def create_user(
    payload: schemas.UserCreate,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin)  # <-- admin only
):
    username = payload.username.strip()

    if db.query(models.User).filter(models.User.username == username).first():
        raise HTTPException(status_code=409, detail="Username already exists")

    role = db.query(models.Role).filter(models.Role.name == payload.role_name).first()
    if not role:
        raise HTTPException(status_code=400, detail="Invalid role_name")

    if not payload.password or len(payload.password) < 6:
        raise HTTPException(status_code=400, detail="Password min 6")

    u = models.User(
        username=username,
        full_name=payload.full_name,
        email=str(payload.email) if payload.email else None,
        password_hash=hash_password(payload.password),
        is_active=True,
        role_id=role.id,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return user_to_out(u)

@router.put("/users/{user_id}", response_model=schemas.UserOut)
def update_user(
    user_id: int,
    payload: schemas.UserUpdate,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin)  # <-- admin only (opcional)
):
    u = db.query(models.User).filter(models.User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")

    if payload.role_name:
        role = db.query(models.Role).filter(models.Role.name == payload.role_name).first()
        if not role:
            raise HTTPException(status_code=400, detail="Invalid role_name")
        u.role_id = role.id

    if payload.full_name is not None:
        u.full_name = payload.full_name

    if payload.email is not None:
        u.email = str(payload.email) if payload.email else None

    db.commit()
    db.refresh(u)
    return user_to_out(u)

@router.patch("/users/{user_id}/active", response_model=schemas.UserOut)
def set_active(
    user_id: int,
    payload: schemas.UserSetActive,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin)  # <-- admin only (opcional)
):
    u = db.query(models.User).filter(models.User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")

    u.is_active = payload.is_active
    db.commit()
    db.refresh(u)
    return user_to_out(u)

@router.patch("/users/{user_id}/password", response_model=schemas.UserOut)
def reset_password(
    user_id: int,
    payload: schemas.UserPasswordReset,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin)  # <-- admin only ✅
):
    if not payload.new_password or len(payload.new_password) < 6:
        raise HTTPException(status_code=400, detail="Password min 6")

    u = db.query(models.User).filter(models.User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")

    u.password_hash = hash_password(payload.new_password)
    db.commit()
    db.refresh(u)
    return user_to_out(u)
