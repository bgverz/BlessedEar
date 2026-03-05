"""
Regression tests for RecommendationEngine (no real network calls).

Run with:
    cd backend
    pip install pytest pytest-asyncio
    pytest tests/test_recommender.py -v

pytest-asyncio >= 0.21 uses "asyncio_mode = auto" in pytest.ini or pyproject.toml.
Alternatively, mark each async test with @pytest.mark.asyncio.
"""

import pytest
import pandas as pd
import spotipy
from unittest.mock import AsyncMock, MagicMock, patch

from app.ml.recommender import RecommendationEngine


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def engine():
    return RecommendationEngine()


def _make_track(track_id: str, artist_id: str = "artist1") -> dict:
    return {
        "id": track_id,
        "name": f"Track {track_id}",
        "artists": [{"id": artist_id, "name": "Test Artist"}],
        "album": {"id": "album1", "name": "Test Album", "images": []},
        "preview_url": None,
        "external_urls": {},
    }


def _fake_audio_features(batch):
    """Return a minimal audio-features dict for each ID in batch."""
    return [
        {
            "id": tid,
            "danceability": 0.5,
            "energy": 0.6,
            "valence": 0.4,
            "speechiness": 0.05,
            "acousticness": 0.3,
            "instrumentalness": 0.0,
            "liveness": 0.1,
            "tempo": 120.0,
        }
        for tid in batch
    ]


# ---------------------------------------------------------------------------
# 1. Batching: sp.audio_features must never receive more than 100 IDs
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_extract_audio_features_batches_at_100(engine):
    sp = MagicMock()
    sp.audio_features.side_effect = _fake_audio_features

    ids = [f"id{i}" for i in range(250)]  # 3 batches: 100 + 100 + 50
    df = await engine.extract_audio_features(sp, ids)

    assert sp.audio_features.call_count == 3, "Expected exactly 3 API calls for 250 IDs"
    for call in sp.audio_features.call_args_list:
        batch = call[0][0]
        assert len(batch) <= 100, f"Batch size {len(batch)} exceeds 100"

    assert len(df) == 250


@pytest.mark.asyncio
async def test_extract_audio_features_skips_none_ids(engine):
    sp = MagicMock()
    sp.audio_features.side_effect = _fake_audio_features

    ids = ["id1", None, "id2", "", "id3"]
    df = await engine.extract_audio_features(sp, ids)

    # Only the 3 valid IDs should reach the API
    actual_batch = sp.audio_features.call_args[0][0]
    assert None not in actual_batch
    assert "" not in actual_batch
    assert len(df) == 3


# ---------------------------------------------------------------------------
# 2. 401 on audio_features propagates (so caller can refresh the token)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_extract_audio_features_raises_on_401(engine):
    sp = MagicMock()
    sp.audio_features.side_effect = spotipy.SpotifyException(
        http_status=401, code=-1, msg="Unauthorized"
    )

    with pytest.raises(spotipy.SpotifyException) as exc_info:
        await engine.extract_audio_features(sp, ["id1", "id2"])

    assert exc_info.value.http_status == 401


# ---------------------------------------------------------------------------
# 3. 403 on audio_features returns empty DataFrame (deprecated API)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_extract_audio_features_returns_empty_on_403(engine):
    sp = MagicMock()
    sp.audio_features.side_effect = spotipy.SpotifyException(
        http_status=403, code=-1, msg="Forbidden"
    )

    df = await engine.extract_audio_features(sp, ["id1", "id2", "id3"])

    assert isinstance(df, pd.DataFrame)
    assert df.empty
    # Should not try additional batches after a 403
    assert sp.audio_features.call_count == 1


# ---------------------------------------------------------------------------
# 4. 429 on audio_features sleeps and retries once
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_extract_audio_features_retries_on_429(engine):
    sp = MagicMock()
    call_count = {"n": 0}

    def rate_limit_then_succeed(batch):
        call_count["n"] += 1
        if call_count["n"] == 1:
            exc = spotipy.SpotifyException(http_status=429, code=-1, msg="Too Many Requests")
            exc.headers = {"Retry-After": "1"}
            raise exc
        return _fake_audio_features(batch)

    sp.audio_features.side_effect = rate_limit_then_succeed

    with patch("app.ml.recommender.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        df = await engine.extract_audio_features(sp, ["id1", "id2"])

    mock_sleep.assert_called_once_with(1)
    assert len(df) == 2


# ---------------------------------------------------------------------------
# 5. Saved-tracks pagination: fetches until 'next' is None
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_all_saved_tracks_paginates(engine):
    sp = MagicMock()

    page1 = {
        "items": [{"track": _make_track(f"t{i}")} for i in range(50)],
        "next": "https://api.spotify.com/v1/me/tracks?offset=50",
    }
    page2 = {
        "items": [{"track": _make_track(f"t{i}")} for i in range(50, 90)],
        "next": None,
    }
    sp.current_user_saved_tracks.side_effect = [page1, page2]

    tracks = await engine._fetch_all_saved_tracks(sp, max_tracks=2000)

    assert len(tracks) == 90
    assert sp.current_user_saved_tracks.call_count == 2


@pytest.mark.asyncio
async def test_fetch_all_saved_tracks_respects_max(engine):
    sp = MagicMock()

    # Each page returns 50 tracks; we cap at 60
    def make_page(offset):
        return {
            "items": [{"track": _make_track(f"t{offset + i}")} for i in range(50)],
            "next": f"https://api.spotify.com/v1/me/tracks?offset={offset + 50}",
        }

    sp.current_user_saved_tracks.side_effect = [make_page(0), make_page(50)]

    tracks = await engine._fetch_all_saved_tracks(sp, max_tracks=60)

    assert len(tracks) == 60


# ---------------------------------------------------------------------------
# 6. Deduplication across sources
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_user_all_tracks_deduplicates(engine):
    sp = MagicMock()
    sp.me.return_value = {"id": "user1"}

    shared = _make_track("shared")
    engine._fetch_all_top_tracks = AsyncMock(return_value=[shared, _make_track("top1")])
    engine._fetch_all_saved_tracks = AsyncMock(return_value=[shared, _make_track("saved1")])
    engine._fetch_all_playlist_tracks = AsyncMock(return_value=[])
    engine._fetch_recently_played = AsyncMock(return_value=[shared])

    unique = await engine.get_user_all_tracks(sp, limit=100)

    ids = [t["id"] for t in unique]
    assert ids.count("shared") == 1, "Duplicate 'shared' should appear only once"
    assert set(ids) == {"shared", "top1", "saved1"}


# ---------------------------------------------------------------------------
# 7. Spotify recommendations 404 returns empty list (deprecated endpoint)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_spotify_recommendations_returns_empty_on_404(engine):
    sp = MagicMock()
    sp.recommendations.side_effect = spotipy.SpotifyException(
        http_status=404, code=-1, msg="Not Found"
    )

    result = await engine._spotify_recommendations(
        sp, seed_artists=["artist1"], user_track_ids=set()
    )

    assert result == []


@pytest.mark.asyncio
async def test_spotify_recommendations_returns_empty_on_403(engine):
    sp = MagicMock()
    sp.recommendations.side_effect = spotipy.SpotifyException(
        http_status=403, code=-1, msg="Forbidden"
    )

    result = await engine._spotify_recommendations(
        sp, seed_artists=["artist1"], user_track_ids=set()
    )

    assert result == []


# ---------------------------------------------------------------------------
# 8. Spotify recommendations: enforce max 5 seeds
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_spotify_recommendations_respects_seed_limit(engine):
    sp = MagicMock()

    captured_params = {}

    def fake_recommendations(**kwargs):
        captured_params.update(kwargs)
        return {"tracks": []}

    sp.recommendations.side_effect = fake_recommendations

    # Pass 10 artists — should be capped to 5
    await engine._spotify_recommendations(
        sp,
        seed_artists=[f"artist{i}" for i in range(10)],
        user_track_ids=set(),
        limit=5,
    )

    total_seeds = len(captured_params.get("seed_artists", [])) + len(
        captured_params.get("seed_tracks", [])
    )
    assert total_seeds <= 5, f"Total seeds {total_seeds} exceeds 5"


# ---------------------------------------------------------------------------
# 9. Recommendations exclude tracks already in user's library
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_spotify_recommendations_excludes_known_tracks(engine):
    sp = MagicMock()

    known_id = "known_track"
    new_id = "new_track"

    def fake_recommendations(**kwargs):
        return {
            "tracks": [
                {
                    "id": known_id,
                    "name": "Known",
                    "artists": [{"name": "A"}],
                    "album": {"name": "B", "images": []},
                    "preview_url": None,
                    "external_urls": {},
                },
                {
                    "id": new_id,
                    "name": "New",
                    "artists": [{"name": "A"}],
                    "album": {"name": "B", "images": []},
                    "preview_url": None,
                    "external_urls": {},
                },
            ]
        }

    sp.recommendations.side_effect = fake_recommendations

    result = await engine._spotify_recommendations(
        sp,
        seed_artists=["artist1"],
        user_track_ids={known_id},
        limit=10,
    )

    result_ids = [r["id"] for r in result]
    assert known_id not in result_ids, "Known track should be excluded from recommendations"
    assert new_id in result_ids


# ---------------------------------------------------------------------------
# New: recommendation history, deduplication, diversity, and exclusion
# ---------------------------------------------------------------------------

def _catalog_track(track_id: str, artist_id: str = "artist1") -> dict:
    """Return a track in the shape that _get_artist_catalog_tracks returns."""
    return {
        "id": track_id,
        "name": f"Catalog {track_id}",
        "artists": ["Test Artist"],
        "artist_ids": [artist_id],
        "album": "Test Album",
        "album_images": [],
        "preview_url": None,
        "external_urls": {},
    }


@pytest.mark.asyncio
async def test_generate_recommendations_no_duplicates(engine):
    """A single response must not contain duplicate track IDs."""
    artist_id = "artist1"
    engine._get_user_library_cached = AsyncMock(
        return_value=[_make_track(f"known{i}") for i in range(10)]
    )
    engine._load_rec_history = AsyncMock(return_value=set())
    engine._save_rec_history = AsyncMock()
    engine._get_user_top_artists = AsyncMock(return_value=[{"id": artist_id}])
    engine._get_artist_top_tracks_cached = AsyncMock(
        return_value=[_make_track(f"top{i}", artist_id) for i in range(15)]
    )
    engine._get_artist_catalog_tracks = AsyncMock(
        return_value=[_catalog_track(f"cat{i}", artist_id) for i in range(15)]
    )

    result = await engine.generate_recommendations(
        user_id="user1", access_token="token", limit=10
    )

    ids = [t["id"] for t in result]
    assert len(ids) == len(set(ids)), f"Duplicate track IDs found: {ids}"


@pytest.mark.asyncio
async def test_generate_recommendations_excludes_history(engine):
    """Tracks in recent recommendation history must not appear in new results."""
    artist_id = "artist1"
    rec_history = {"top0", "top1", "top2"}

    engine._get_user_library_cached = AsyncMock(return_value=[])
    engine._load_rec_history = AsyncMock(return_value=rec_history)
    engine._save_rec_history = AsyncMock()
    engine._get_user_top_artists = AsyncMock(return_value=[{"id": artist_id}])
    # top0–top2 are in history; top3–top9 are new
    engine._get_artist_top_tracks_cached = AsyncMock(
        return_value=[_make_track(f"top{i}", artist_id) for i in range(10)]
    )
    engine._get_artist_catalog_tracks = AsyncMock(return_value=[])

    result = await engine.generate_recommendations(
        user_id="user1", access_token="token", limit=10
    )

    result_ids = {t["id"] for t in result}
    overlap = result_ids & rec_history
    assert not overlap, f"History tracks appeared in results: {overlap}"


@pytest.mark.asyncio
async def test_generate_recommendations_excludes_library_tracks(engine):
    """Tracks already in the user's library must not appear in recommendations."""
    artist_id = "artist1"
    library = [_make_track(f"lib{i}", artist_id) for i in range(5)]
    library_ids = {t["id"] for t in library}

    # Catalog returns library tracks + new tracks
    catalog = (
        [_catalog_track(f"lib{i}", artist_id) for i in range(5)]
        + [_catalog_track(f"new{i}", artist_id) for i in range(10)]
    )

    engine._get_user_library_cached = AsyncMock(return_value=library)
    engine._load_rec_history = AsyncMock(return_value=set())
    engine._save_rec_history = AsyncMock()
    engine._get_user_top_artists = AsyncMock(return_value=[{"id": artist_id}])
    engine._get_artist_top_tracks_cached = AsyncMock(return_value=[])
    engine._get_artist_catalog_tracks = AsyncMock(return_value=catalog)

    result = await engine.generate_recommendations(
        user_id="user1", access_token="token", limit=10
    )

    result_ids = {t["id"] for t in result}
    overlap = result_ids & library_ids
    assert not overlap, f"Library tracks appeared in results: {overlap}"


@pytest.mark.asyncio
async def test_generate_recommendations_artist_diversity(engine):
    """Max 2 tracks per artist in a single recommendation response."""
    from collections import Counter

    artist_id = "mono_artist"
    # 20 catalog tracks all from the same artist
    catalog = [_catalog_track(f"t{i}", artist_id) for i in range(20)]

    engine._get_user_library_cached = AsyncMock(return_value=[])
    engine._load_rec_history = AsyncMock(return_value=set())
    engine._save_rec_history = AsyncMock()
    engine._get_user_top_artists = AsyncMock(return_value=[{"id": artist_id}])
    engine._get_artist_top_tracks_cached = AsyncMock(return_value=[])
    engine._get_artist_catalog_tracks = AsyncMock(return_value=catalog)

    result = await engine.generate_recommendations(
        user_id="user1", access_token="token", limit=10
    )

    artist_counts = Counter(
        (t.get("artist_ids") or [t["artists"][0]])[0] for t in result
    )
    for artist, count in artist_counts.items():
        assert count <= 2, f"Artist {artist} appears {count} times (max 2 allowed)"


@pytest.mark.asyncio
async def test_generate_recommendations_saves_history(engine):
    """generate_recommendations must persist the returned track IDs to history."""
    artist_id = "artist1"
    save_mock = AsyncMock()

    # Library must be non-empty so the function doesn't abort early
    engine._get_user_library_cached = AsyncMock(
        return_value=[_make_track("lib0", "known_artist")]
    )
    engine._load_rec_history = AsyncMock(return_value=set())
    engine._save_rec_history = save_mock
    engine._get_user_top_artists = AsyncMock(return_value=[{"id": artist_id}])
    engine._get_artist_top_tracks_cached = AsyncMock(
        return_value=[_make_track(f"t{i}", artist_id) for i in range(10)]
    )
    engine._get_artist_catalog_tracks = AsyncMock(return_value=[])

    result = await engine.generate_recommendations(
        user_id="user1", access_token="token", limit=5
    )

    assert save_mock.called, "_save_rec_history was not called"
    saved_user_id, saved_ids = save_mock.call_args[0]
    assert saved_user_id == "user1"
    result_ids = {t["id"] for t in result}
    assert set(saved_ids) == result_ids, (
        f"Saved history IDs {set(saved_ids)} don't match returned IDs {result_ids}"
    )
