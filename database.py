from __future__ import annotations
# database.py
# Comentarios en español


import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# ==========================
# CARGAR .env (sin librerías)
# ==========================
# Comentario ES:
# Leemos el archivo .env manualmente para NO depender de python-dotenv.
# Así siempre funciona igual.

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"

def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        # Comentario ES: no sobreescribe si ya existe en el sistema
        os.environ.setdefault(k, v)

load_env_file(ENV_PATH)

# ==========================
# ARMAR DATABASE_URL
# ==========================
# Comentario ES:
# Preferimos DATABASE_URL directo si existe (más simple).
# Si no existe, armamos desde DB_USER/DB_PASSWORD/DB_HOST/DB_PORT/DB_NAME

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

if not DATABASE_URL:
    db_user = os.getenv("DB_USER", "").strip()
    db_pass = os.getenv("DB_PASSWORD", "").strip()
    db_host = os.getenv("DB_HOST", "localhost").strip()
    db_port = os.getenv("DB_PORT", "5432").strip()
    db_name = os.getenv("DB_NAME", "").strip()

    if db_user and db_pass and db_name:
        # Comentario ES: URL para Postgres
        DATABASE_URL = f"postgresql+psycopg2://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"
    else:
        # Comentario ES: fallback SOLO si no hay variables completas (para no romper)
        DATABASE_URL = f"sqlite:///{(BASE_DIR / 'evolution_truck.db').as_posix()}"

# ==========================
# CREAR ENGINE
# ==========================
# Comentario ES:
# connect_args solo aplica para SQLite.
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,  # Comentario ES: evita conexiones muertas
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# ==========================
# DEPENDENCY FASTAPI
# ==========================
def get_db():
    # Comentario ES: abre sesión y garantiza cierre
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()