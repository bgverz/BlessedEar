from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import uvicorn
from typing import List, Optional
import asyncio
from contextlib import asynccontextmanager
import time
import logging
from app.models import User, Playlist

from app.api import auth, recommendations, analytics, playlists
from app.core.config import get_settings
from app.core.database import init_db
from app.ml.recommender import RecommendationEngine

settings = get_settings()
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    app.state.recommendation_engine = RecommendationEngine()
    await app.state.recommendation_engine.load_models()
    yield
    pass

app = FastAPI(
    title="BlessedEar API",
    description="AI-Powered Playlist Generation with Advanced Analytics",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["authentication"])
app.include_router(recommendations.router, prefix="/api/recommendations", tags=["recommendations"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["analytics"])
app.include_router(playlists.router, prefix="/api/playlists", tags=["playlists"])


@app.middleware("http")
async def request_timing_middleware(request, call_next):
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
    return {"status": "healthy", "ml_engine": "loaded"}

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
