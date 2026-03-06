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


def test_discover_outside_bubble_returns_genre_cards():
    async def _fake_user():
        return {
            "spotify_id": "u1",
            "spotify_tokens": {"access_token": "test-token"},
        }

    app.dependency_overrides[get_current_user] = _fake_user

    fake_context = {
        "sp": object(),
        "top_genres": ["rap", "hip hop"],
        "top_artists": [],
        "top_tracks": [],
        "top_artist_ids": set(),
        "user_genres_set": {"rap", "hip hop"},
        "user_track_ids": set(),
    }

    with (
        patch.object(recommendations_module, "get_valid_access_token", new=AsyncMock(return_value="test-token")),
        patch.object(recommendations_module, "_build_discover_context", new=AsyncMock(return_value=fake_context)),
        patch.object(
            recommendations_module.recommendation_engine,
            "_spotify_call_with_timeout",
            new=AsyncMock(return_value={"artists": {"items": [{"name": "Artist X"}, {"name": "Artist Y"}]}}),
        ),
    ):
        response = client.get("/api/recommendations/discover/outside-bubble?limit=4")

    app.dependency_overrides.clear()

    assert response.status_code == 200, response.text
    payload = response.json()
    assert "outside_your_bubble" in payload
    assert len(payload["outside_your_bubble"]) > 0
    assert {"genre", "description", "sample_artists"} <= set(payload["outside_your_bubble"][0].keys())


def test_discover_explorer_returns_all_modules():
    async def _fake_user():
        return {
            "spotify_id": "u1",
            "spotify_tokens": {"access_token": "test-token"},
        }

    app.dependency_overrides[get_current_user] = _fake_user

    with (
        patch.object(recommendations_module, "get_valid_access_token", new=AsyncMock(return_value="test-token")),
        patch.object(recommendations_module, "_build_discover_context", new=AsyncMock(return_value={
            "sp": object(),
            "top_genres": ["rap"],
            "top_artists": [],
            "top_tracks": [],
            "top_artist_ids": set(),
            "user_genres_set": {"rap"},
            "user_track_ids": set(),
        })),
        patch.object(recommendations_module, "_module_outside_bubble", new=AsyncMock(return_value=[])),
        patch.object(recommendations_module, "_module_artists_you_should_know", new=AsyncMock(return_value=[])),
        patch.object(recommendations_module, "_module_underground_radar", new=AsyncMock(return_value=[])),
        patch.object(recommendations_module, "_module_trending_outside", new=AsyncMock(return_value=[])),
    ):
        response = client.get("/api/recommendations/discover/explorer")

    app.dependency_overrides.clear()

    assert response.status_code == 200, response.text
    payload = response.json()
    assert set(payload.keys()) == {
        "outside_your_bubble",
        "artists_you_should_know",
        "underground_radar",
        "trending_outside_your_taste",
    }


def test_discover_explorer_degrades_when_one_module_fails():
    async def _fake_user():
        return {
            "spotify_id": "u1",
            "spotify_tokens": {"access_token": "test-token"},
        }

    app.dependency_overrides[get_current_user] = _fake_user

    with (
        patch.object(recommendations_module, "get_valid_access_token", new=AsyncMock(return_value="test-token")),
        patch.object(recommendations_module, "_build_discover_context", new=AsyncMock(return_value={
            "sp": object(),
            "top_genres": ["rap"],
            "top_artists": [],
            "top_tracks": [],
            "top_artist_ids": set(),
            "user_genres_set": {"rap"},
            "user_track_ids": set(),
        })),
        patch.object(recommendations_module, "_module_outside_bubble", new=AsyncMock(side_effect=RuntimeError("fail"))),
        patch.object(recommendations_module, "_module_artists_you_should_know", new=AsyncMock(return_value=[{
            "id": "a1", "name": "Artist 1", "genres": [], "image_url": None, "popularity": 0, "reason": "x", "external_urls": {}
        }])),
        patch.object(recommendations_module, "_module_underground_radar", new=AsyncMock(return_value=[])),
        patch.object(recommendations_module, "_module_trending_outside", new=AsyncMock(return_value=[])),
    ):
        response = client.get("/api/recommendations/discover/explorer")

    app.dependency_overrides.clear()
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["outside_your_bubble"] == []
    assert len(payload["artists_you_should_know"]) == 1


def test_discover_explorer_ignores_related_artists_failures():
    async def _fake_user():
        return {
            "spotify_id": "u1",
            "spotify_tokens": {"access_token": "test-token"},
        }

    app.dependency_overrides[get_current_user] = _fake_user

    with (
        patch.object(recommendations_module, "get_valid_access_token", new=AsyncMock(return_value="test-token")),
        patch.object(recommendations_module, "_build_discover_context", new=AsyncMock(return_value={
            "sp": object(),
            "top_genres": ["rap"],
            "top_artists": [],
            "top_tracks": [],
            "top_artist_ids": set(),
            "user_genres_set": {"rap"},
            "user_track_ids": set(),
        })),
        patch.object(recommendations_module, "_module_outside_bubble", new=AsyncMock(return_value=[])),
        patch.object(recommendations_module, "_module_artists_you_should_know", new=AsyncMock(return_value=[])),
        patch.object(recommendations_module, "_module_underground_radar", new=AsyncMock(return_value=[])),
        patch.object(recommendations_module, "_module_trending_outside", new=AsyncMock(return_value=[])),
        patch.object(recommendations_module.recommendation_engine, "_get_related_artists_cached", new=AsyncMock(side_effect=RuntimeError("404"))),
    ):
        response = client.get("/api/recommendations/discover/explorer")

    app.dependency_overrides.clear()
    assert response.status_code == 200, response.text
    payload = response.json()
    assert "outside_your_bubble" in payload
    assert isinstance(payload["outside_your_bubble"], list)


def test_discover_trending_outside_skips_malformed_search_data():
    async def _fake_user():
        return {
            "spotify_id": "u1",
            "spotify_tokens": {"access_token": "test-token"},
        }

    app.dependency_overrides[get_current_user] = _fake_user
    fake_context = {
        "sp": object(),
        "top_genres": ["rap"],
        "top_artists": [],
        "top_tracks": [],
        "top_artist_ids": set(),
        "user_genres_set": {"rap"},
        "user_track_ids": set(),
    }
    with (
        patch.object(recommendations_module, "get_valid_access_token", new=AsyncMock(return_value="test-token")),
        patch.object(recommendations_module, "_build_discover_context", new=AsyncMock(return_value=fake_context)),
        patch.object(
            recommendations_module.recommendation_engine,
            "_spotify_call_with_timeout",
            new=AsyncMock(return_value={"tracks": {"items": [None, {"id": None}, {"id": "t1", "name": "Good", "artists": [{"name": "A"}], "album": {"name": "X", "images": []}, "popularity": 78}]}}),
        ),
    ):
        response = client.get("/api/recommendations/discover/trending-outside?limit=10")

    app.dependency_overrides.clear()
    assert response.status_code == 200, response.text
    payload = response.json()
    assert "trending_outside_your_taste" in payload
    assert isinstance(payload["trending_outside_your_taste"], list)


def test_diversify_track_candidates_enforces_artist_and_album_caps():
    candidates = [
        {"id": "t1", "name": "A1", "artists": ["Same Artist"], "album": "Same Album", "popularity": 70, "_source": "s1", "_score": 10},
        {"id": "t2", "name": "A2", "artists": ["Same Artist"], "album": "Same Album", "popularity": 68, "_source": "s1", "_score": 9},
        {"id": "t3", "name": "B1", "artists": ["Artist B"], "album": "Album B", "popularity": 55, "_source": "s2", "_score": 8},
        {"id": "t4", "name": "C1", "artists": ["Artist C"], "album": "Album C", "popularity": 30, "_source": "s3", "_score": 7},
        {"id": "t5", "name": "D1", "artists": ["Artist D"], "album": "Album D", "popularity": 80, "_source": "s2", "_score": 6},
    ]
    out = recommendations_module._diversify_track_candidates(
        candidates,
        limit=4,
        max_per_artist=1,
        max_per_album=1,
        max_per_source=2,
        enforce_pop_band_mix=False,
    )
    ids = [t["id"] for t in out]
    assert len(ids) == len(set(ids))
    artists = [t["artists"][0] for t in out]
    assert len(artists) == len(set(artists))
    albums = [t["album"] for t in out]
    assert len(albums) == len(set(albums))


def test_diversify_track_candidates_source_balance():
    candidates = [
        {"id": f"s1_{i}", "name": f"S1-{i}", "artists": [f"A{i}"], "album": f"AL{i}", "popularity": 70, "_source": "source1", "_score": 20 - i}
        for i in range(6)
    ] + [
        {"id": f"s2_{i}", "name": f"S2-{i}", "artists": [f"B{i}"], "album": f"BL{i}", "popularity": 50, "_source": "source2", "_score": 10 - i}
        for i in range(4)
    ]
    out = recommendations_module._diversify_track_candidates(
        candidates,
        limit=6,
        max_per_artist=1,
        max_per_album=1,
        max_per_source=3,
        enforce_pop_band_mix=False,
    )
    sources = [t["_source"] for t in out]
    assert "source1" in sources and "source2" in sources
    assert sources.count("source1") <= 4


def test_discover_genre_feed_avoids_duplicate_tracks():
    async def _fake_user():
        return {
            "spotify_id": "u1",
            "spotify_tokens": {"access_token": "test-token"},
        }

    app.dependency_overrides[get_current_user] = _fake_user

    duplicate_track = {"id": "dup1", "name": "Dup", "artists": [{"name": "A"}], "album": {"name": "Alb", "images": []}, "popularity": 60}
    with (
        patch.object(recommendations_module, "get_valid_access_token", new=AsyncMock(return_value="test-token")),
        patch.object(recommendations_module.recommendation_engine, "get_spotify_client", new=AsyncMock(return_value=object())),
        patch.object(
            recommendations_module.recommendation_engine,
            "_spotify_call_with_timeout",
            new=AsyncMock(return_value={"tracks": {"items": [duplicate_track, duplicate_track]}, "playlists": {"items": []}}),
        ),
        patch.object(recommendations_module, "_safe_playlist_tracks", new=AsyncMock(return_value=[])),
    ):
        response = client.get("/api/recommendations/discover/genre/indie%20rock?limit=8")

    app.dependency_overrides.clear()
    assert response.status_code == 200, response.text
    tracks = response.json()["tracks"]
    ids = [t["id"] for t in tracks]
    assert len(ids) == len(set(ids))
