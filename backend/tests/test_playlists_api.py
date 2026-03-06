"""
API regression tests for AI playlist generator endpoints.
"""

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_playlists.db")
os.environ.setdefault("SPOTIFY_CLIENT_ID", "test_client_id")
os.environ.setdefault("SPOTIFY_CLIENT_SECRET", "test_client_secret")
os.environ.setdefault("SPOTIFY_REDIRECT_URI", "http://localhost:8000/api/auth/callback")
os.environ.setdefault("JWT_SECRET_KEY", "test_secret_key_for_testing_only")
os.environ.setdefault("FRONTEND_URL", "http://localhost:3000")

from app.api import playlists as playlists_module  # noqa: E402
from app.api.auth import get_current_user  # noqa: E402


app = FastAPI()
app.include_router(playlists_module.router, prefix="/api/playlists")
client = TestClient(app, raise_server_exceptions=False)


def test_normalize_generated_track_full_spotify_shape():
    track = {
        "id": "track_full",
        "name": "Full Track",
        "artists": [{"name": "Artist A"}, {"name": "Artist B"}],
        "album": {
            "name": "Album Full",
            "images": [
                {"url": "https://i.scdn.co/image/640", "width": 640, "height": 640},
                {"url": "https://i.scdn.co/image/300", "width": 300, "height": 300},
            ],
        },
        "external_urls": {"spotify": "https://open.spotify.com/track/track_full"},
    }
    out = playlists_module._normalize_generated_track(track)
    assert out["track_id"] == "track_full"
    assert out["artist"] == "Artist A, Artist B"
    assert out["album"] == "Album Full"
    assert out["album_cover_url"] == "https://i.scdn.co/image/300"


def test_normalize_generated_track_simplified_shape_with_album_string():
    track = {
        "track_id": "track_simple",
        "name": "Simple Track",
        "artist": "Solo Artist",
        "album": "String Album",
        "album_cover_url": "https://img/simple.jpg",
        "spotify_url": "https://open.spotify.com/track/track_simple",
    }
    out = playlists_module._normalize_generated_track(track)
    assert out["track_id"] == "track_simple"
    assert out["artist"] == "Solo Artist"
    assert out["album"] == "String Album"
    assert out["album_cover_url"] == "https://img/simple.jpg"


def test_normalize_generated_track_missing_album_images_is_safe():
    track = {
        "id": "track_no_album",
        "name": "No Album Track",
        "artists": ["Artist C"],
    }
    out = playlists_module._normalize_generated_track(track)
    assert out["track_id"] == "track_no_album"
    assert out["album"] == ""
    assert out["album_cover_url"] is None
    assert out["spotify_url"] == "https://open.spotify.com/track/track_no_album"


def test_parse_prompt_profile_spanish_hits():
    profile = playlists_module._parse_prompt_profile("spanish hits")
    assert profile["prompt_type"] == "concrete"
    assert profile["language"] == "spanish"
    assert profile["region"] == "latin"
    assert profile["popularity_bias"] == "popular"


def test_parse_prompt_profile_late_night_vibes_is_abstract():
    profile = playlists_module._parse_prompt_profile("late night vibes")
    assert profile["prompt_type"] == "abstract"
    assert "late_night" in profile["moods"]
    assert any("late night" in term for term in profile["search_terms"])


def test_parse_prompt_profile_late_night_rb_is_hybrid():
    profile = playlists_module._parse_prompt_profile("late night r&b")
    assert profile["prompt_type"] == "hybrid"
    assert "r&b" in profile["genres"]
    assert "late_night" in profile["moods"]


def test_prompt_score_penalizes_non_latin_for_spanish_prompt():
    profile = playlists_module._parse_prompt_profile("spanish hits")
    track = {
        "track_id": "en1",
        "name": "Firework",
        "artist": "Katy Perry",
        "seed_genres": ["dance pop"],
        "popularity": 95,
    }
    score = playlists_module._prompt_score_track(track, profile)
    assert score < 1.0


def test_build_candidates_concrete_prompt_uses_playlist_search():
    profile = playlists_module._parse_prompt_profile("spanish hits")
    with (
        patch.object(playlists_module.recommendation_engine, "_get_user_top_artists", new=AsyncMock(return_value=[])),
        patch.object(playlists_module, "_collect_playlist_search_candidates", new=AsyncMock(return_value=[])) as playlist_search_mock,
        patch.object(playlists_module, "_search_prompt_tracks", new=AsyncMock(return_value=[])),
        patch.object(playlists_module, "_search_prompt_artists", new=AsyncMock(return_value=[])),
        patch.object(playlists_module, "_load_generator_exclusions", new=AsyncMock(return_value=set())),
        patch.object(playlists_module.recommendation_engine, "generate_mood_playlist", new=AsyncMock(return_value=[])),
    ):
        asyncio.run(
            playlists_module._build_prompt_first_candidates(
                sp=object(),
                spotify_id="u1",
                access_token="tok",
                prompt="spanish hits",
                profile=profile,
                limit=25,
            )
        )
    assert playlist_search_mock.await_count == 1


def test_build_candidates_abstract_prompt_skips_playlist_search():
    profile = playlists_module._parse_prompt_profile("late night vibes")
    with (
        patch.object(playlists_module.recommendation_engine, "_get_user_top_artists", new=AsyncMock(return_value=[])),
        patch.object(playlists_module, "_collect_playlist_search_candidates", new=AsyncMock(return_value=[])) as playlist_search_mock,
        patch.object(playlists_module, "_search_prompt_tracks", new=AsyncMock(return_value=[])),
        patch.object(playlists_module, "_search_prompt_artists", new=AsyncMock(return_value=[])),
        patch.object(playlists_module, "_load_generator_exclusions", new=AsyncMock(return_value=set())),
        patch.object(playlists_module.recommendation_engine, "generate_mood_playlist", new=AsyncMock(return_value=[])),
    ):
        asyncio.run(
            playlists_module._build_prompt_first_candidates(
                sp=object(),
                spotify_id="u1",
                access_token="tok",
                prompt="late night vibes",
                profile=profile,
                limit=25,
            )
        )
    assert playlist_search_mock.await_count == 0


def test_get_playlist_tracks_skips_null_and_unusable_items():
    spotify_client = MagicMock()
    result = {
        "items": [
            None,
            {"track": None},
            {"track": {"name": "Missing ID"}},
            {"track": {"id": "ok1", "name": "Valid", "artists": [{"name": "Artist A"}]}},
        ]
    }
    with patch.object(
        playlists_module.recommendation_engine,
        "_spotify_call_with_timeout",
        new=AsyncMock(return_value=result),
    ):
        tracks = asyncio.run(playlists_module._get_playlist_tracks(spotify_client, "pl1", limit=20))
    assert len(tracks) == 1
    assert tracks[0]["id"] == "ok1"


def test_collect_playlist_candidates_skips_malformed_playlists_and_tracks():
    profile = {"search_terms": ["spanish hits"], "raw_prompt": "spanish hits"}
    source_counts = {}
    with (
        patch.object(
            playlists_module,
            "_search_public_playlists",
            new=AsyncMock(
                return_value=[
                    None,
                    {},
                    {"id": ""},
                    {"id": "pl_small", "tracks": {"total": 4}},
                    {"id": "pl1", "tracks": {"total": 20}},
                ]
            ),
        ),
        patch.object(
            playlists_module,
            "_get_playlist_tracks",
            new=AsyncMock(
                return_value=[
                    {"id": "t1", "name": "Track 1", "artists": [{"name": "Artist 1"}], "album": {"name": "A1", "images": []}},
                    {"name": "Missing ID"},
                ]
            ),
        ),
    ):
        candidates = asyncio.run(
            playlists_module._collect_playlist_search_candidates(
                sp=object(),
                profile=profile,
                source_counts=source_counts,
            )
        )
    assert len(candidates) == 1
    assert candidates[0]["track_id"] == "t1"
    assert candidates[0]["source"] == "playlist_search"
    assert source_counts["playlist_search"] == 1


def test_build_candidates_fallback_when_playlist_source_partially_fails():
    profile = playlists_module._parse_prompt_profile("spanish hits")
    with (
        patch.object(playlists_module.recommendation_engine, "_get_user_top_artists", new=AsyncMock(return_value=[])),
        patch.object(playlists_module, "_collect_playlist_search_candidates", new=AsyncMock(side_effect=RuntimeError("playlist source failed"))),
        patch.object(
            playlists_module,
            "_search_prompt_tracks",
            new=AsyncMock(return_value=[{"id": "t1", "name": "Track 1", "artists": [{"name": "Artist 1"}], "album": {"name": "A1", "images": []}}]),
        ),
        patch.object(playlists_module, "_search_prompt_artists", new=AsyncMock(return_value=[])),
        patch.object(playlists_module, "_load_generator_exclusions", new=AsyncMock(return_value=set())),
        patch.object(playlists_module.recommendation_engine, "generate_mood_playlist", new=AsyncMock(return_value=[])),
    ):
        candidates, source_counts, _, _ = asyncio.run(
            playlists_module._build_prompt_first_candidates(
                sp=object(),
                spotify_id="u1",
                access_token="tok",
                prompt="spanish hits",
                profile=profile,
                limit=25,
            )
        )
    assert candidates
    assert source_counts["prompt_search_tracks"] >= 1


def test_generate_playlist_from_prompt_shape():
    async def _fake_user():
        return {
            "id": 1,
            "spotify_id": "u1",
            "spotify_tokens": {"access_token": "test-token"},
        }

    app.dependency_overrides[get_current_user] = _fake_user

    generated = [{
        "id": "track1",
        "name": "Noche de Fiesta",
        "artists": [{"id": "a1", "name": "Artist 1"}],
        "album_images": [{"url": "https://i.scdn.co/image/300", "width": 300, "height": 300}],
        "external_urls": {"spotify": "https://open.spotify.com/track/track1"},
        "popularity": 80,
        "seed_genres": ["reggaeton"],
        "source_tag": "prompt_search_tracks",
    }]

    with (
        patch.object(playlists_module, "get_valid_access_token", new=AsyncMock(return_value="test-token")),
        patch.object(playlists_module.recommendation_engine, "get_spotify_client", new=AsyncMock(return_value=object())),
        patch.object(playlists_module, "_build_prompt_first_candidates", new=AsyncMock(return_value=(generated, {"prompt_search_tracks": 1}, {"reggaeton"}, {"a1"}))),
        patch.object(playlists_module, "_load_generator_exclusions", new=AsyncMock(return_value=set())),
        patch.object(playlists_module, "_save_generator_history", new=AsyncMock()),
        patch.object(playlists_module.recommendation_engine, "generate_recommendations", new=AsyncMock(return_value=[])),
    ):
        response = client.post("/api/playlists/generate", json={"prompt": "late night drive"})

    app.dependency_overrides.clear()

    assert response.status_code == 200, response.text
    payload = response.json()
    assert "playlist_title" in payload
    assert payload["tracks"]
    assert set(payload["tracks"][0].keys()) == {
        "track_id", "name", "artist", "artists", "album", "album_cover_url", "album_images", "spotify_url",
    }


def test_generate_playlist_200_with_junk_candidates():
    async def _fake_user():
        return {
            "id": 1,
            "spotify_id": "u1",
            "spotify_tokens": {"access_token": "test-token"},
        }

    app.dependency_overrides[get_current_user] = _fake_user

    malformed_and_valid = [
        None,
        {},
        {"name": "No ID"},
        {
            "track_id": "ok-track",
            "name": "Good Song",
            "artist": "Good Artist",
            "artists": ["Good Artist"],
            "album": "Album",
            "album_cover_url": None,
            "album_images": [],
            "spotify_url": "https://open.spotify.com/track/ok-track",
            "genres": ["indie"],
            "popularity": 61,
            "source": "prompt_search_tracks",
        },
    ]

    with (
        patch.object(playlists_module, "get_valid_access_token", new=AsyncMock(return_value="test-token")),
        patch.object(playlists_module.recommendation_engine, "get_spotify_client", new=AsyncMock(return_value=object())),
        patch.object(
            playlists_module,
            "_build_prompt_first_candidates",
            new=AsyncMock(return_value=(malformed_and_valid, {"prompt_search_tracks": 1}, {"indie"}, set())),
        ),
        patch.object(playlists_module, "_load_generator_exclusions", new=AsyncMock(return_value=set())),
        patch.object(playlists_module, "_save_generator_history", new=AsyncMock()),
        patch.object(playlists_module.recommendation_engine, "generate_recommendations", new=AsyncMock(return_value=[])),
    ):
        response = client.post("/api/playlists/generate", json={"prompt": "late night vibes"})

    app.dependency_overrides.clear()
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["track_count"] >= 1
    assert payload["tracks"][0]["track_id"] == "ok-track"


def test_prompt_differentiation_low_overlap_between_sad_indie_and_gym_trap():
    sad_profile = playlists_module._parse_prompt_profile("sad indie")
    gym_profile = playlists_module._parse_prompt_profile("gym trap")

    sad_track = {
        "track_id": "sad1",
        "name": "Melancholy Lights",
        "artist": "Indie Band",
        "seed_genres": ["indie", "alternative"],
        "popularity": 42,
    }
    gym_track = {
        "track_id": "gym1",
        "name": "Trap Sprint",
        "artist": "Trap Artist",
        "seed_genres": ["trap", "hip hop"],
        "popularity": 70,
    }

    sad_score_on_sad = playlists_module._prompt_score_track(sad_track, sad_profile)
    sad_score_on_gym = playlists_module._prompt_score_track(sad_track, gym_profile)
    gym_score_on_gym = playlists_module._prompt_score_track(gym_track, gym_profile)
    gym_score_on_sad = playlists_module._prompt_score_track(gym_track, sad_profile)

    assert sad_score_on_sad > sad_score_on_gym
    assert gym_score_on_gym > gym_score_on_sad


def test_spanish_hits_prefers_latin_tracks_over_unrelated_pop():
    async def _fake_user():
        return {
            "id": 1,
            "spotify_id": "u1",
            "spotify_tokens": {"access_token": "test-token"},
        }

    app.dependency_overrides[get_current_user] = _fake_user

    latin_tracks = []
    for i in range(12):
        latin_tracks.append({
            "id": f"latin{i}",
            "name": f"Reggaeton Hit {i}",
            "artists": [{"id": f"a{i}", "name": f"Latin Artist {i}"}],
            "album_images": [{"url": f"https://i.scdn.co/image/{i}", "width": 300, "height": 300}],
            "external_urls": {"spotify": f"https://open.spotify.com/track/latin{i}"},
            "popularity": 82,
            "seed_genres": ["reggaeton", "latin pop"],
            "source_tag": "prompt_artist_top_tracks",
        })
    latin_tracks.append({
        "id": "katy",
        "name": "Firework",
        "artists": [{"id": "katy", "name": "Katy Perry"}],
        "album_images": [{"url": "https://i.scdn.co/image/katy", "width": 300, "height": 300}],
        "external_urls": {"spotify": "https://open.spotify.com/track/katy"},
        "popularity": 96,
        "seed_genres": ["dance pop"],
        "source_tag": "prompt_search_tracks",
    })

    with (
        patch.object(playlists_module, "get_valid_access_token", new=AsyncMock(return_value="test-token")),
        patch.object(playlists_module.recommendation_engine, "get_spotify_client", new=AsyncMock(return_value=object())),
        patch.object(playlists_module, "_build_prompt_first_candidates", new=AsyncMock(return_value=(latin_tracks, {"prompt_artist_top_tracks": 12, "prompt_search_tracks": 1}, {"reggaeton"}, set()))),
        patch.object(playlists_module, "_load_generator_exclusions", new=AsyncMock(return_value=set())),
        patch.object(playlists_module, "_save_generator_history", new=AsyncMock()),
        patch.object(playlists_module.recommendation_engine, "generate_recommendations", new=AsyncMock(return_value=[])),
    ):
        response = client.post("/api/playlists/generate", json={"prompt": "spanish hits", "limit": 20})

    app.dependency_overrides.clear()
    assert response.status_code == 200, response.text
    track_names = [t["name"] for t in response.json()["tracks"]]
    assert "Firework" not in track_names


def test_export_generated_playlist_to_spotify():
    async def _fake_user():
        return {
            "id": 1,
            "spotify_id": "u1",
            "spotify_tokens": {"access_token": "test-token"},
        }

    app.dependency_overrides[get_current_user] = _fake_user

    spotify_client = MagicMock()
    spotify_client.user_playlist_create.return_value = {
        "id": "pl123",
        "external_urls": {"spotify": "https://open.spotify.com/playlist/pl123"},
    }

    with (
        patch.object(playlists_module, "get_valid_access_token", new=AsyncMock(return_value="test-token")),
        patch("spotipy.Spotify", return_value=spotify_client),
    ):
        response = client.post(
            "/api/playlists/export",
            json={
                "prompt": "late night drive",
                "tracks": [{"track_id": "track1", "name": "Night Ride", "artist": "Artist 1"}],
            },
        )

    app.dependency_overrides.clear()

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["spotify_playlist_id"] == "pl123"
    assert payload["track_count"] == 1
