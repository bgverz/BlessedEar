import os


def _normalize_debug_env() -> None:
    raw = os.environ.get("DEBUG")
    if raw is None:
        os.environ["DEBUG"] = "false"
        return
    if raw.strip().lower() not in {"true", "false"}:
        os.environ["DEBUG"] = "false"


_normalize_debug_env()

# Provide test-safe defaults for required settings when not explicitly set.
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("SPOTIFY_CLIENT_ID", "test_client_id")
os.environ.setdefault("SPOTIFY_CLIENT_SECRET", "test_client_secret")
os.environ.setdefault("SPOTIFY_REDIRECT_URI", "http://localhost:8000/api/auth/callback")
os.environ.setdefault("JWT_SECRET_KEY", "test_secret_key_for_testing_only")
os.environ.setdefault("FRONTEND_URL", "http://localhost:3000")
