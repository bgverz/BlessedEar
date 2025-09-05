# app/core/config.py
from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional

class Settings(BaseSettings):
    # App Config
    app_name: str = "BlessedEar"
    debug: bool = True
    
    # Database
    database_url: str = "sqlite:///./blessedear.db"
    redis_url: str = "redis://localhost:6379"
    
    # Spotify API
    spotify_client_id: str
    spotify_client_secret: str
    spotify_redirect_uri: str = "http://localhost:8000/api/auth/callback"
    
    # Security
    jwt_secret_key: str = "your-super-secret-jwt-key-change-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    
    # ML Model Settings
    model_cache_ttl: int = 3600  # 1 hour
    recommendation_batch_size: int = 50
    
    class Config:
        env_file = ".env"

@lru_cache()
def get_settings():
    return Settings()