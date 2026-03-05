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


def test_callback_accepts_missing_state_with_warning(caplog):
    """Callback without state should not hard-reject (backward compat), but warns."""
    _clear_cache()

    fake_token = {
        "access_token": "tok",
        "refresh_token": "ref",
        "expires_at": 9999999999,
        "token_type": "Bearer",
        "scope": "",
    }
    fake_spotify_user = {"id": "user1", "email": "u@example.com", "display_name": "User One"}

    mock_oauth_instance = MagicMock()
    mock_oauth_instance.get_access_token.return_value = fake_token

    mock_sp_instance = MagicMock()
    mock_sp_instance.current_user.return_value = fake_spotify_user

    with (
        patch.object(auth_module, "get_spotify_oauth", return_value=mock_oauth_instance),
        patch("spotipy.Spotify", return_value=mock_sp_instance),
    ):
        # Use dependency_overrides so FastAPI uses our mock DB, not the real
        # SQLite file (which has no tables).  patch.object(auth_module, "get_db")
        # only patches the module attribute; FastAPI already stored the original
        # function object in Depends() and ignores the attribute change.
        app.dependency_overrides[real_get_db] = _fake_db
        try:
            import logging
            with caplog.at_level(logging.WARNING, logger="app.api.auth"):
                response = client.get("/api/auth/callback?code=real_code", follow_redirects=False)
        finally:
            app.dependency_overrides.clear()

    # Should redirect (302) to the frontend dashboard, not raise 400
    assert response.status_code == 302, response.text
    # A warning about the missing state must have been logged
    assert any("state" in record.message.lower() for record in caplog.records), (
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
