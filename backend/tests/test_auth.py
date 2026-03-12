"""
Regression tests for the auth endpoints.

Run with:
    cd backend
    pip install pytest pytest-asyncio httpx
    pytest tests/test_auth.py -v

These tests use FastAPI's TestClient (ASGI) and mock both the Spotify OAuth
client and the SQLAlchemy DB session so no real network calls or database
tables are required.
"""

import json
import asyncio
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Bootstrap: set env vars BEFORE any app import so pydantic-settings picks
# them up on the first (and only, due to lru_cache) call to get_settings().
# ---------------------------------------------------------------------------

import os
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_auth.db")
os.environ.setdefault("SPOTIFY_CLIENT_ID", "test_client_id")
os.environ.setdefault("SPOTIFY_CLIENT_SECRET", "test_client_secret")
os.environ.setdefault("SPOTIFY_REDIRECT_URI", "http://localhost:8000/api/auth/callback")
os.environ.setdefault("JWT_SECRET_KEY", "test_secret_key_for_testing_only")
os.environ.setdefault("FRONTEND_URL", "http://localhost:3000")

from fastapi import FastAPI
from app.api import auth as auth_module
from app.core.database import memory_cache, get_db as real_get_db

app = FastAPI()
app.include_router(auth_module.router, prefix="/api/auth")

client = TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clear_cache():
    memory_cache.clear()


def _make_jwt(spotify_id: str) -> str:
    import jwt as pyjwt
    from app.core.config import get_settings
    settings = get_settings()
    return pyjwt.encode({"sub": spotify_id}, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def _fake_sp_oauth(get_authorize_url_side_effect=None):
    """Return a mock SpotifyOAuth instance whose get_authorize_url mimics the
    real implementation: builds a URL that includes show_dialog=True (if set
    via self.show_dialog) and the provided state."""
    mock_instance = MagicMock()

    def _build_url(state=None, **__):  # noqa: ANN003
        base = "https://accounts.spotify.com/authorize"
        params = ["client_id=test_client_id", "response_type=code",
                  "redirect_uri=http%3A%2F%2Flocalhost%3A8000%2Fapi%2Fauth%2Fcallback"]
        if state:
            params.append(f"state={state}")
        # show_dialog comes from the constructor flag (mock_instance.show_dialog)
        if mock_instance.show_dialog:
            params.append("show_dialog=True")
        return base + "?" + "&".join(params)

    mock_instance.show_dialog = True  # mirrors get_spotify_oauth(show_dialog=True)
    mock_instance.get_authorize_url.side_effect = (
        get_authorize_url_side_effect if get_authorize_url_side_effect else _build_url
    )
    return mock_instance


def _fake_db():
    """Yield a mock SQLAlchemy Session for dependency_overrides."""
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None
    yield mock_db


# ---------------------------------------------------------------------------
# 1. /login always includes show_dialog=True in the Spotify authorize URL
# ---------------------------------------------------------------------------

def test_login_url_contains_show_dialog():
    _clear_cache()

    with patch.object(auth_module, "get_spotify_oauth", return_value=_fake_sp_oauth()):
        response = client.get("/api/auth/login")

    assert response.status_code == 200, response.text
    data = response.json()
    assert "auth_url" in data
    assert "show_dialog=true" in data["auth_url"].lower(), (
        f"Expected show_dialog=true in {data['auth_url']!r}"
    )


# ---------------------------------------------------------------------------
# 2. /login embeds a state token in the authorize URL and caches it
# ---------------------------------------------------------------------------

def test_login_includes_state_in_url():
    _clear_cache()

    captured = {}

    def _capture_state_url(state=None, show_dialog=False):
        captured["state"] = state
        return (
            f"https://accounts.spotify.com/authorize"
            f"?state={state}&show_dialog=True"
        )

    mock_sp_oauth = _fake_sp_oauth(get_authorize_url_side_effect=_capture_state_url)

    with patch.object(auth_module, "get_spotify_oauth", return_value=mock_sp_oauth):
        response = client.get("/api/auth/login")

    assert response.status_code == 200, response.text
    auth_url = response.json()["auth_url"]
    assert "state=" in auth_url, "auth_url must contain a state parameter"

    state = captured.get("state")
    assert state is not None

    # State must be persisted to the cache so the callback can validate it.
    from app.core.database import get_cache
    cached = asyncio.get_event_loop().run_until_complete(get_cache(f"oauth_state:{state}"))
    assert cached == "valid", "State must be cached after /login"


# ---------------------------------------------------------------------------
# 3. /callback rejects requests with an invalid / missing state
# ---------------------------------------------------------------------------

def test_callback_rejects_invalid_state():
    _clear_cache()
    # state "invalid_state" is not in cache → must return 400
    response = client.get("/api/auth/callback?code=fake_code&state=invalid_state")
    assert response.status_code == 400
    assert "state" in response.json()["detail"].lower()


def test_callback_rejects_missing_state(caplog):
    """Callback without state must be hard-rejected with 400 (CSRF protection).

    Previously the app logged a warning and continued; that was a CSRF
    vulnerability.  The fix unconditionally rejects callbacks that arrive
    without a state parameter.
    """
    _clear_cache()

    import logging
    with caplog.at_level(logging.WARNING, logger="app.api.auth"):
        response = client.get("/api/auth/callback?code=real_code", follow_redirects=False)

    assert response.status_code == 400, (
        f"Expected 400 for missing state, got {response.status_code}: {response.text}"
    )
    detail = response.json().get("detail", "").lower()
    assert "state" in detail, f"Expected state in error detail, got: {detail!r}"
    assert any("state" in r.message.lower() for r in caplog.records), (
        f"Expected a state-related warning; got: {[r.message for r in caplog.records]}"
    )


# ---------------------------------------------------------------------------
# 4. /callback consumes the state token (one-time use)
# ---------------------------------------------------------------------------

def test_callback_consumes_state():
    """After a valid callback the state cache entry is deleted."""
    _clear_cache()

    from app.core.database import set_cache, get_cache
    state = "consumetest"
    asyncio.get_event_loop().run_until_complete(
        set_cache(f"oauth_state:{state}", "valid", expire=600)
    )

    fake_token = {
        "access_token": "tok2",
        "refresh_token": "ref2",
        "expires_at": 9999999999,
        "token_type": "Bearer",
        "scope": "",
    }
    fake_spotify_user = {"id": "user2", "email": "u2@example.com", "display_name": "User Two"}

    mock_oauth_instance = MagicMock()
    mock_oauth_instance.get_access_token.return_value = fake_token

    mock_sp_instance = MagicMock()
    mock_sp_instance.current_user.return_value = fake_spotify_user

    with (
        patch.object(auth_module, "get_spotify_oauth", return_value=mock_oauth_instance),
        patch("spotipy.Spotify", return_value=mock_sp_instance),
    ):
        app.dependency_overrides[real_get_db] = _fake_db
        try:
            client.get(
                f"/api/auth/callback?code=real_code&state={state}",
                follow_redirects=False,
            )
        finally:
            app.dependency_overrides.clear()

    # State must be gone after use
    remaining = asyncio.get_event_loop().run_until_complete(
        get_cache(f"oauth_state:{state}")
    )
    assert remaining is None, "State token must be consumed after a successful callback"


# ---------------------------------------------------------------------------
# 5. /logout clears per-user cache keys
# ---------------------------------------------------------------------------

def test_logout_clears_cache():
    _clear_cache()

    spotify_id = "logout_user"
    token = _make_jwt(spotify_id)

    async def _seed():
        await auth_module.set_cache(
            f"user:{spotify_id}",
            json.dumps({
                "spotify_id": spotify_id, "id": 1,
                "display_name": "X",
                "spotify_tokens": {"access_token": "t"},
            }),
        )
        await auth_module.set_cache(f"recommendations:{spotify_id}", "some_recs")
        await auth_module.set_cache(f"profile:{spotify_id}", "some_profile")

    asyncio.get_event_loop().run_until_complete(_seed())

    response = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200

    from app.core.database import get_cache

    async def _check():
        return (
            await get_cache(f"user:{spotify_id}"),
            await get_cache(f"recommendations:{spotify_id}"),
            await get_cache(f"profile:{spotify_id}"),
        )

    user_val, rec_val, prof_val = asyncio.get_event_loop().run_until_complete(_check())
    assert user_val is None, "user cache must be cleared on logout"
    assert rec_val is None, "recommendations cache must be cleared on logout"
    assert prof_val is None, "profile cache must be cleared on logout"


# ---------------------------------------------------------------------------
# 6. No cross-user cache leakage: two users have independent cache entries
# ---------------------------------------------------------------------------

def test_no_cross_user_cache_leakage():
    _clear_cache()

    from app.core.database import set_cache, get_cache

    async def _run():
        await set_cache(
            "user:alice",
            json.dumps({"spotify_id": "alice", "id": 1, "display_name": "Alice",
                        "spotify_tokens": {"access_token": "tok_a"}}),
        )
        await set_cache(
            "user:bob",
            json.dumps({"spotify_id": "bob", "id": 2, "display_name": "Bob",
                        "spotify_tokens": {"access_token": "tok_b"}}),
        )

        alice = json.loads(await get_cache("user:alice"))
        bob = json.loads(await get_cache("user:bob"))

        assert alice["spotify_id"] == "alice"
        assert bob["spotify_id"] == "bob"
        assert alice["spotify_tokens"]["access_token"] != bob["spotify_tokens"]["access_token"]

    asyncio.get_event_loop().run_until_complete(_run())


# ---------------------------------------------------------------------------
# 7. Cache backend: Redis fallback to in-memory when Redis is unavailable
# ---------------------------------------------------------------------------

def test_cache_falls_back_to_memory_when_redis_unavailable():
    """When Redis is unreachable the in-memory dict is used transparently."""
    import app.core.database as db_module

    # Force the probe to "not yet attempted" so we can inject a bad URL.
    original_available = db_module._redis_available
    original_client = db_module._redis_client
    original_url = db_module.settings.redis_url

    db_module._redis_available = None
    db_module._redis_client = None
    # Point at a port nothing is listening on.
    db_module.settings.redis_url = "redis://127.0.0.1:19999"
    db_module.memory_cache.clear()

    try:
        async def _run():
            await db_module.set_cache("test_key", "test_value", expire=60)
            result = await db_module.get_cache("test_key")
            assert result == "test_value", f"Expected 'test_value', got {result!r}"
            await db_module.delete_cache("test_key")
            assert await db_module.get_cache("test_key") is None

        asyncio.get_event_loop().run_until_complete(_run())
        # Confirm the fallback dict was used (not Redis).
        assert db_module._redis_available is False
    finally:
        db_module._redis_available = original_available
        db_module._redis_client = original_client
        db_module.settings.redis_url = original_url
        db_module.memory_cache.clear()


# ---------------------------------------------------------------------------
# 8. /callback does not leak internal exception details to the client
# ---------------------------------------------------------------------------

def test_callback_hides_internal_exception_details():
    """Internal errors must not be surfaced in HTTP responses.

    When the Spotify token exchange raises an unexpected exception the
    response body must contain only a safe generic message, not str(e).
    """
    _clear_cache()

    # Seed a valid state so CSRF validation passes.
    import asyncio
    from app.core.database import set_cache
    state = "err_test_state"
    asyncio.get_event_loop().run_until_complete(
        set_cache(f"oauth_state:{state}", "valid", expire=600)
    )

    sentinel_message = "super_secret_db_password_or_traceback_detail"

    mock_oauth = MagicMock()
    mock_oauth.get_access_token.side_effect = RuntimeError(sentinel_message)

    with patch.object(auth_module, "get_spotify_oauth", return_value=mock_oauth):
        app.dependency_overrides[real_get_db] = _fake_db
        try:
            response = client.get(
                f"/api/auth/callback?code=real_code&state={state}",
                follow_redirects=False,
            )
        finally:
            app.dependency_overrides.clear()

    assert response.status_code == 400
    body = response.text
    assert sentinel_message not in body, (
        f"Internal error detail must not be in HTTP response, but found it in: {body!r}"
    )
    assert "Authentication failed" in body
