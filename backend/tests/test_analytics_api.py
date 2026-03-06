"""
API regression tests for /api/analytics endpoints.
"""

import os
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_analytics.db")
os.environ.setdefault("SPOTIFY_CLIENT_ID", "test_client_id")
os.environ.setdefault("SPOTIFY_CLIENT_SECRET", "test_client_secret")
os.environ.setdefault("SPOTIFY_REDIRECT_URI", "http://localhost:8000/api/auth/callback")
os.environ.setdefault("JWT_SECRET_KEY", "test_secret_key_for_testing_only")
os.environ.setdefault("FRONTEND_URL", "http://localhost:3000")

from app.api import analytics as analytics_module  # noqa: E402
from app.api.auth import get_current_user  # noqa: E402


app = FastAPI()
app.include_router(analytics_module.router, prefix="/api/analytics")
client = TestClient(app, raise_server_exceptions=False)


def test_taste_profile_shape():
    async def _fake_user():
        return {
            "spotify_id": "u1",
            "spotify_tokens": {"access_token": "test-token"},
        }

    app.dependency_overrides[get_current_user] = _fake_user

    fake_signals = {
        "total_tracks": 120,
        "unique_artists": 66,
        "artist_play_counts": {"a1": 10},
        "discovery_score": 0.55,
        "artist_loyalty": 0.41,
        "mainstream_index": 0.62,
        "deep_cut_ratio": 0.18,
        "genre_breakdown": [
            {"genre": "indie pop", "percentage": 33.0},
            {"genre": "neo soul", "percentage": 20.0},
        ],
        "top_genres": ["indie pop", "neo soul"],
        "hidden_gems": [],
        "avg_release_year": 2019.4,
    }

    with (
        patch.object(analytics_module, "get_valid_access_token", new=AsyncMock(return_value="test-token")),
        patch.object(analytics_module.recommendation_engine, "get_spotify_client", new=AsyncMock(return_value=object())),
        patch.object(analytics_module, "_get_signals_cached", new=AsyncMock(return_value=fake_signals)),
    ):
        response = client.get("/api/analytics/taste-profile")

    app.dependency_overrides.clear()

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["spotify_id"] == "u1"
    assert isinstance(payload["archetype"], str)
    assert isinstance(payload["top_genres"], list)
    assert isinstance(payload["traits"], list)
    assert "signals" in payload


def test_listening_insights_shape():
    async def _fake_user():
        return {
            "spotify_id": "u2",
            "spotify_tokens": {"access_token": "test-token"},
        }

    app.dependency_overrides[get_current_user] = _fake_user

    fake_signals = {
        "total_tracks": 98,
        "unique_artists": 58,
        "artist_play_counts": {"a1": 12},
        "discovery_score": 0.59,
        "artist_loyalty": 0.38,
        "mainstream_index": 0.48,
        "deep_cut_ratio": 0.33,
        "genre_breakdown": [
            {"genre": "alternative r&b", "percentage": 31.0},
            {"genre": "hip hop", "percentage": 17.0},
        ],
        "top_genres": ["alternative r&b", "hip hop"],
        "hidden_gems": [{
            "id": "t1",
            "name": "Hidden Song",
            "artists": ["Artist 1"],
            "popularity": 22,
            "album_image_url": "https://i.scdn.co/image/300",
        }],
        "avg_release_year": 2017.0,
    }

    with (
        patch.object(analytics_module, "get_valid_access_token", new=AsyncMock(return_value="test-token")),
        patch.object(analytics_module.recommendation_engine, "get_spotify_client", new=AsyncMock(return_value=object())),
        patch.object(analytics_module, "_get_signals_cached", new=AsyncMock(return_value=fake_signals)),
    ):
        response = client.get("/api/analytics/listening-insights?time_range=medium_term")

    app.dependency_overrides.clear()

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["spotify_id"] == "u2"
    assert payload["time_range"] == "medium_term"
    assert set(payload["listening_insights"].keys()) == {
        "discovery_score", "artist_loyalty", "mainstream_index",
    }
    assert "genre_breakdown" in payload["sound_profile"]
    assert isinstance(payload["hidden_gems"], list)
