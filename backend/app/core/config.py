import logging
from pydantic import model_validator
from pydantic_settings import BaseSettings
from functools import lru_cache

logger = logging.getLogger(__name__)

_LOCALHOST_MARKERS = ("localhost", "127.0.0.1", "0.0.0.0")

class Settings(BaseSettings):
    app_name: str = "BlessedEar"
    debug: bool = False

    database_url: str = "sqlite:///./blessedear.db"
    redis_url: str = "redis://localhost:6379"

    frontend_url: str = "http://localhost:3000"

    spotify_client_id: str
    spotify_client_secret: str
    spotify_redirect_uri: str = "http://127.0.0.1:8000/api/auth/callback"

    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    model_cache_ttl: int = 3600
    recommendation_batch_size: int = 50

    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    log_level: str = "INFO"

    class Config:
        env_file = ".env"

    @model_validator(mode="after")
    def _check_production_safety(self) -> "Settings":
        """Detect dangerous misconfigurations at startup when debug=False."""
        if self.debug:
            return self

        warnings: list[str] = []

        if self.database_url.startswith("sqlite"):
            warnings.append(
                "DATABASE_URL is SQLite — use PostgreSQL in production "
                "(set DATABASE_URL=postgresql://...)"
            )

        for origin in self.cors_origins_list:
            if any(m in origin for m in _LOCALHOST_MARKERS):
                warnings.append(
                    f"CORS_ORIGINS contains a localhost entry ({origin!r}). "
                    "Set CORS_ORIGINS to your production HTTPS domain."
                )
                break

        redirect = self.spotify_redirect_uri
        if redirect.startswith("http://") and not any(
            m in redirect for m in _LOCALHOST_MARKERS
        ):
            warnings.append(
                f"SPOTIFY_REDIRECT_URI uses plain HTTP on a non-localhost host ({redirect!r}). "
                "Use HTTPS for production."
            )

        for w in warnings:
            logger.warning("[production-guard] %s", w)

        return self


@lru_cache()
def get_settings():
    return Settings()

settings = get_settings()
