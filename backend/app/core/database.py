from sqlalchemy import create_engine, MetaData
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.core.config import get_settings

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

memory_cache = {}

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
    memory_cache[key] = value

async def get_cache(key: str):
    return memory_cache.get(key)

async def delete_cache(key: str):
    """Delete a key from cache"""
    try:
        print(f"Deleting cache key: {key}")
        pass
    except Exception as e:
        print(f"Cache deletion failed for {key}: {e}")
        pass