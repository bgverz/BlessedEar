from sqlalchemy import create_engine, MetaData
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.core.config import get_settings
import time

settings = get_settings()

if settings.database_url.startswith("sqlite"):
    engine = create_engine(
        settings.database_url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
else:
    engine = create_engine(settings.database_url)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

memory_cache: dict = {}

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

async def init_db():
    """Create database tables"""
    Base.metadata.create_all(bind=engine)
    print("Database initialized!")

async def set_cache(key: str, value: str, expire: int = 3600):
    expires_at = time.time() + expire if expire > 0 else None
    memory_cache[key] = (value, expires_at)

async def get_cache(key: str):
    entry = memory_cache.get(key)
    if entry is None:
        return None
    value, expires_at = entry
    if expires_at is not None and time.time() > expires_at:
        del memory_cache[key]
        return None
    return value

async def delete_cache(key: str):
    memory_cache.pop(key, None)