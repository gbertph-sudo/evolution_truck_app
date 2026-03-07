# security.py
# Comentarios en español. Respuestas/UI en inglés.

from typing import List

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from sqlalchemy.orm import Session

from database import get_db
from models import User

# ✅ IMPORTANTE:
# Esta SECRET_KEY y ALGORITHM DEBEN ser EXACTAMENTE iguales a main.py
SECRET_KEY = "CHANGE_THIS_SECRET_KEY_NOW_123456789"
ALGORITHM = "HS256"

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    payload = decode_token(token)

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(status_code=403, detail="User is inactive")

    return user


def require_roles(*allowed_roles: str):
    """
    ✅ Uso correcto:
      current_user: User = Depends(require_roles("ADMIN", "SUPERADMIN"))
    """
    allowed = {r.strip().upper() for r in allowed_roles if r and r.strip()}

    def _dep(current_user: User = Depends(get_current_user)) -> User:
        role_name = ((current_user.role.name if current_user.role else "") or "").strip().upper()
        if role_name not in allowed:
            raise HTTPException(status_code=403, detail="Not enough permissions")
        return current_user

    return _dep
