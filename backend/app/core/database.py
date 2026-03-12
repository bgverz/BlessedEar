from sqlalchemy import create_engine, MetaData
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool
from app.core.config import get_settings
import logging
import time
from typing import Optional
import asyncio

settings = get_settings()
logger = logging.getLogger(__name__)

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


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def init_db():
    """Create database tables (dev/test only — production uses Alembic)."""
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables ensured.")


memory_cache: dict = {}

_redis_client = None
_redis_available: Optional[bool] = None
_redis_loop_id: Optional[int] = None


async def _get_redis():
    """Return an async Redis client if Redis is reachable, else None."""
    global _redis_client, _redis_available, _redis_loop_id

    current_loop = asyncio.get_running_loop()
    current_loop_id = id(current_loop)

    # Async Redis clients are bound to their creation loop; never reuse across loops.
    if _redis_client is not None and _redis_loop_id is not None and _redis_loop_id != current_loop_id:
        try:
            await _redis_client.aclose()
        except Exception:
            pass
        _redis_client = None
        _redis_available = None
        _redis_loop_id = None

    if _redis_available is True:
        return _redis_client
    if _redis_available is False:
        return None

    try:
        import redis.asyncio as aioredis
        client = aioredis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        await client.ping()
        _redis_client = client
        _redis_available = True
        _redis_loop_id = current_loop_id
        logger.info("Cache backend: Redis at %s", settings.redis_url)
        return _redis_client
    except Exception as exc:
        _redis_available = False
        _redis_loop_id = None
        logger.warning(
            "Redis not reachable (%s) — falling back to in-memory cache. "
            "This is NOT suitable for multi-worker production deployments.",
            exc,
        )
        return None


async def set_cache(key: str, value: str, expire: int = 3600):
    r = await _get_redis()
    if r is not None:
        await r.setex(key, expire, value)
        return
    expires_at = time.time() + expire if expire > 0 else None
    memory_cache[key] = (value, expires_at)


async def get_cache(key: str) -> Optional[str]:
    r = await _get_redis()
    if r is not None:
        return await r.get(key)
    entry = memory_cache.get(key)
    if entry is None:
        return None
    value, expires_at = entry
    if expires_at is not None and time.time() > expires_at:
        del memory_cache[key]
        return None
    return value


async def delete_cache(key: str):
    r = await _get_redis()
    if r is not None:
        await r.delete(key)
        return
    memory_cache.pop(key, None)
