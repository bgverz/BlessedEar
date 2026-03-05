from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    app_name: str = "BlessedEar"
    debug: bool = True

    database_url: str = "sqlite:///./blessedear.db"
    redis_url: str = "redis://localhost:6379"

    frontend_url: str = "http://localhost:3000"

    spotify_client_id: str
    spotify_client_secret: str
    spotify_redirect_uri: str = "http://127.0.0.1:8000/api/auth/callback"

    jwt_secret_key: str  # Required — no default; set JWT_SECRET_KEY in .env
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    model_cache_ttl: int = 3600
    recommendation_batch_size: int = 50

    class Config:
        env_file = ".env"

@lru_cache()
def get_settings():
    return Settings()

settings = get_settings()
