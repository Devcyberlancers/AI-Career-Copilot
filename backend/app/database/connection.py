import os
from pathlib import Path
from urllib.parse import urlparse
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

BACKEND_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(BACKEND_ROOT / ".env")

ENVIRONMENT = os.getenv("ENVIRONMENT", "development").strip().lower()
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./career_copilot.db")

if ENVIRONMENT in {"production", "prod"} and DATABASE_URL.startswith("sqlite"):
    raise RuntimeError("DATABASE_URL must use PostgreSQL when ENVIRONMENT=production.")


def _resolve_sqlite_url(database_url: str) -> str:
    if not database_url.startswith("sqlite"):
        return database_url
    parsed = urlparse(database_url)
    raw_path = parsed.path or ""
    if database_url.startswith("sqlite:///") and not database_url.startswith("sqlite:////"):
        relative_path = raw_path.lstrip("/")
        absolute_path = (BACKEND_ROOT / relative_path).resolve()
        return f"sqlite:///{absolute_path.as_posix()}"
    return database_url


DATABASE_URL = _resolve_sqlite_url(DATABASE_URL)

# If using SQLite, we need connect_args to prevent multi-threading session errors
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Dependency to get db session in API routes
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
