from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import sqlalchemy
import uvicorn
from contextlib import asynccontextmanager
import time
import logging
from app.models import User, Playlist

from app.api import auth, recommendations, analytics, playlists
from app.core.config import get_settings
from app.core.database import init_db
from app.core.logging_config import configure_logging
from app.ml.recommender import RecommendationEngine

settings = get_settings()

configure_logging(
    log_level=settings.log_level,
    use_json=not settings.debug,
)
logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    app.state.recommendation_engine = RecommendationEngine()
    await app.state.recommendation_engine.load_models()
    yield


app = FastAPI(
    title="BlessedEar API",
    description="AI-Powered Playlist Generation with Advanced Analytics",
    version="1.0.0",
    lifespan=lifespan,
    debug=settings.debug,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["authentication"])
app.include_router(recommendations.router, prefix="/api/recommendations", tags=["recommendations"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["analytics"])
app.include_router(playlists.router, prefix="/api/playlists", tags=["playlists"])


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """Add HTTP security headers to every response.

    These defend against common web attacks regardless of client behaviour:
    - X-Content-Type-Options: prevents MIME-sniffing attacks
    - X-Frame-Options: blocks clickjacking via iframes
    - Referrer-Policy: prevents leaking URLs in Referer headers to third parties
    - Permissions-Policy: opts out of browser features the API never uses
    - Content-Security-Policy: defence-in-depth for the API (not an HTML app,
      but still good practice; tighten further if you add an SSR frontend here)
    """
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    response.headers["Content-Security-Policy"] = "default-src 'none'"
    return response


@app.middleware("http")
async def request_timing_middleware(request: Request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    logger.info(
        "[http] path=%s method=%s status=%s duration_ms=%s",
        request.url.path,
        request.method,
        response.status_code,
        elapsed_ms,
    )
    return response


@app.get("/")
async def root():
    return {"message": "BlessedEar API", "version": "1.0.0"}


@app.get("/health")
async def health_check():
    """Liveness + readiness probe.

    Returns {"status": "healthy"} only when the database and cache are both
    reachable.  Orchestrators (Docker HEALTHCHECK, Kubernetes readiness probe)
    use this endpoint to decide whether to route traffic to this instance.
    """
    from app.core.database import get_cache, set_cache, engine
    checks: dict = {}

    try:
        with engine.connect() as conn:
            conn.execute(sqlalchemy.text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        logger.error("Health check: database unreachable: %s", exc)
        checks["database"] = "error"

    try:
        await set_cache("health:probe", "1", expire=5)
        val = await get_cache("health:probe")
        checks["cache"] = "ok" if val == "1" else "read-mismatch"
    except Exception as exc:
        logger.error("Health check: cache unreachable: %s", exc)
        checks["cache"] = "error"

    all_ok = all(v == "ok" for v in checks.values())
    return {
        "status": "healthy" if all_ok else "degraded",
        "ml_engine": "loaded",
        "checks": checks,
    }


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
