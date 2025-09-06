from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional

class Settings(BaseSettings):
    app_name: str = "BlessedEar"
    debug: bool = True
    
    database_url: str = "sqlite:///./blessedear.db"
    redis_url: str = "redis://localhost:6379"
    
    spotify_client_id: str
    spotify_client_secret: str
    spotify_redirect_uri: str = "http://127.0.0.1:8000/api/auth/callback"
    
    jwt_secret_key: str = "your-super-secret-jwt-key-change-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    
    model_cache_ttl: int = 3600
    recommendation_batch_size: int = 50
    
    class Config:
        env_file = ".env"

@lru_cache()
def get_settings():
    settings = Settings()
    print(f"DEBUG: Using Spotify Client ID: {settings.spotify_client_id[:10]}...")
    print(f"DEBUG: Using redirect URI: {settings.spotify_redirect_uri}")
    return settings

settings = get_settings()