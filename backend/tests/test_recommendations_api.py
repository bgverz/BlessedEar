"""
API regression tests for /api/recommendations endpoints.
"""

import os
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_recommendations.db")
os.environ.setdefault("SPOTIFY_CLIENT_ID", "test_client_id")
os.environ.setdefault("SPOTIFY_CLIENT_SECRET", "test_client_secret")
os.environ.setdefault("SPOTIFY_REDIRECT_URI", "http://localhost:8000/api/auth/callback")
os.environ.setdefault("JWT_SECRET_KEY", "test_secret_key_for_testing_only")
os.environ.setdefault("FRONTEND_URL", "http://localhost:3000")

from app.api import recommendations as recommendations_module  # noqa: E402
from app.api.auth import get_current_user  # noqa: E402


app = FastAPI()
app.include_router(recommendations_module.router, prefix="/api/recommendations")
client = TestClient(app, raise_server_exceptions=False)


def test_top_tracks_includes_album_image_url():
    async def _fake_user():
        return {
            "spotify_id": "u1",
            "spotify_tokens": {"access_token": "test-token"},
        }

    app.dependency_overrides[get_current_user] = _fake_user

    fake_tracks = [{
        "id": "track_1",
        "name": "Track 1",
        "artists": [{"name": "Artist 1"}],
        "album": {
            "name": "Album 1",
            "images": [
                {"url": "https://i.scdn.co/image/640", "width": 640, "height": 640},
                {"url": "https://i.scdn.co/image/300", "width": 300, "height": 300},
                {"url": "https://i.scdn.co/image/64", "width": 64, "height": 64},
            ],
        },
        "popularity": 72,
        "preview_url": None,
        "external_urls": {"spotify": "https://open.spotify.com/track/track_1"},
    }]

    with (
        patch.object(recommendations_module, "get_valid_access_token", new=AsyncMock(return_value="test-token")),
        patch.object(recommendations_module.recommendation_engine, "get_spotify_client", new=AsyncMock(return_value=object())),
        patch.object(recommendations_module.recommendation_engine, "get_user_top_tracks", new=AsyncMock(return_value=fake_tracks)),
    ):
        response = client.get("/api/recommendations/top-tracks?time_range=medium_term&limit=20")

    app.dependency_overrides.clear()

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["top_tracks"], "Expected non-empty top_tracks"
    first = payload["top_tracks"][0]
    assert "album_image_url" in first
    assert first["album_image_url"] == "https://i.scdn.co/image/300"


def test_dna_endpoint_payload_has_consistent_shape_for_analytics():
    async def _fake_user():
        return {
            "spotify_id": "u1",
            "spotify_tokens": {"access_token": "test-token"},
        }

    app.dependency_overrides[get_current_user] = _fake_user

    fake_dna = {
        "spotify_id": "u1",
        "status": "ok",
        "dimensions": {
            "energy": 0.66,
            "valence": 0.52,
            "danceability": 0.71,
            "acousticness": 0.31,
            "speechiness": 0.22,
            "diversity": 0.57,
        },
        "metadata": {
            "total_artists_analyzed": 24,
            "total_tracks_analyzed": 81,
            "unique_genres": ["pop", "indie pop"],
            "avg_popularity": 0.63,
            "avg_era": 0.87,
            "source": "genres+popularity+era",
            "fallback_reasons": [],
        },
        "source": "genres+popularity+era",
    }

    with (
        patch.object(recommendations_module, "get_valid_access_token", new=AsyncMock(return_value="test-token")),
        patch.object(recommendations_module.recommendation_engine, "build_music_dna", new=AsyncMock(return_value=fake_dna)),
    ):
        response = client.get("/api/recommendations/dna")

    app.dependency_overrides.clear()

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["spotify_id"] == "u1"
    assert payload["status"] == "ok"
    assert set(payload["dimensions"].keys()) == {
        "energy", "valence", "danceability", "acousticness", "speechiness", "diversity",
    }
    assert "avg_popularity" in payload["metadata"]
    assert isinstance(payload["metadata"]["avg_popularity"], float)
