"""
Unit tests for RecommendationEngine.build_music_dna.

Run with:
    cd backend
    pytest tests/test_dna.py -v
"""

import json
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.ml.recommender import RecommendationEngine


@pytest.fixture
def engine():
    return RecommendationEngine()


def _make_artist(artist_id: str, genres: list, popularity: int = 70) -> dict:
    return {"id": artist_id, "name": f"Artist {artist_id}", "genres": genres, "popularity": popularity}


def _make_track(track_id: str, popularity: int = 70, release_year: int = 2020, explicit: bool = False) -> dict:
    return {
        "id": track_id,
        "name": f"Track {track_id}",
        "popularity": popularity,
        "explicit": explicit,
        "album": {
            "name": "Test Album",
            "release_date": f"{release_year}-01-01",
            "images": [{"url": "https://example.com/img.jpg", "width": 640, "height": 640}],
        },
        "artists": [{"id": "a1", "name": "Artist 1"}],
        "preview_url": None,
        "external_urls": {"spotify": f"https://open.spotify.com/track/{track_id}"},
    }


def _make_sp(artists: list, tracks: list) -> MagicMock:
    """Mock Spotify client that returns the same artists/tracks for all time ranges."""
    sp = MagicMock()
    sp.current_user_top_artists.return_value = {"items": artists}
    sp.current_user_top_tracks.return_value = {"items": tracks}
    return sp


# ---------------------------------------------------------------------------
# 1. DNA payload shape
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_build_music_dna_shape(engine):
    """build_music_dna must return the expected payload shape."""
    artists = [_make_artist("a1", ["pop", "dance pop"]), _make_artist("a2", ["hip hop", "rap"])]
    tracks = [_make_track(f"t{i}") for i in range(5)]
    sp = _make_sp(artists, tracks)

    engine.get_spotify_client = AsyncMock(return_value=sp)

    with patch("app.ml.recommender.get_cache", new=AsyncMock(return_value=None)), \
         patch("app.ml.recommender.set_cache", new=AsyncMock()):
        result = await engine.build_music_dna("user1", "token")

    assert "error" not in result
    assert result["spotify_id"] == "user1"
    assert "dimensions" in result
    dims = result["dimensions"]
    for key in ("energy", "valence", "danceability", "acousticness", "speechiness", "diversity"):
        assert key in dims, f"Missing dimension: {key}"
        assert 0.0 <= dims[key] <= 1.0, f"Dimension {key}={dims[key]} out of range"
    assert result["source"] == "genres+popularity+era"
    assert "metadata" in result


# ---------------------------------------------------------------------------
# 2. Different users → different DNA
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_build_music_dna_user_specific(engine):
    """Rock listener and classical listener should have significantly different Energy scores."""
    rock_artists = [
        _make_artist("r1", ["rock", "hard rock", "metal", "classic rock", "alternative rock"]),
    ]
    classical_artists = [
        _make_artist("c1", ["classical", "chamber music", "opera", "baroque", "orchestral"]),
    ]
    tracks = [_make_track("t1")]

    sp_rock = _make_sp(rock_artists, tracks)
    sp_classical = _make_sp(classical_artists, tracks)

    engine.get_spotify_client = AsyncMock(side_effect=[sp_rock, sp_classical])

    with patch("app.ml.recommender.get_cache", new=AsyncMock(return_value=None)), \
         patch("app.ml.recommender.set_cache", new=AsyncMock()):
        dna_rock = await engine.build_music_dna("rock_user", "token_rock")
        dna_classical = await engine.build_music_dna("classical_user", "token_classical")

    assert "error" not in dna_rock
    assert "error" not in dna_classical
    assert dna_rock["dimensions"]["energy"] > dna_classical["dimensions"]["energy"], (
        f"Rock energy {dna_rock['dimensions']['energy']} should be > "
        f"Classical energy {dna_classical['dimensions']['energy']}"
    )


# ---------------------------------------------------------------------------
# 3. Hip-hop listener has high speechiness
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_build_music_dna_hiphop_speechiness(engine):
    """Hip-hop/rap genres should yield a speechiness score > 0.55."""
    artists = [
        _make_artist("h1", ["hip hop", "rap", "trap", "conscious hip hop", "east coast hip hop"]),
    ]
    tracks = [_make_track("t1")]
    sp = _make_sp(artists, tracks)
    engine.get_spotify_client = AsyncMock(return_value=sp)

    with patch("app.ml.recommender.get_cache", new=AsyncMock(return_value=None)), \
         patch("app.ml.recommender.set_cache", new=AsyncMock()):
        dna = await engine.build_music_dna("hiphop_user", "token")

    assert dna["dimensions"]["speechiness"] > 0.55, (
        f"Hip-hop listener speechiness {dna['dimensions']['speechiness']} should be > 0.55"
    )


# ---------------------------------------------------------------------------
# 4. Diverse listener has high diversity score
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_build_music_dna_diversity(engine):
    """A listener with 30+ unique genres should have diversity close to 1.0."""
    genres = [
        "pop", "hip hop", "rock", "classical", "jazz", "folk", "electronic", "r&b",
        "country", "metal", "ambient", "soul", "reggae", "indie", "blues", "funk",
        "latin", "gospel", "afrobeats", "drum and bass", "house", "techno", "trance",
        "punk", "grunge", "emo", "trap", "grime", "bossa nova", "flamenco",
    ]
    artists = [_make_artist("d1", genres)]
    tracks = [_make_track("t1")]
    sp = _make_sp(artists, tracks)
    engine.get_spotify_client = AsyncMock(return_value=sp)

    with patch("app.ml.recommender.get_cache", new=AsyncMock(return_value=None)), \
         patch("app.ml.recommender.set_cache", new=AsyncMock()):
        dna = await engine.build_music_dna("diverse_user", "token")

    assert dna["dimensions"]["diversity"] >= 0.9, (
        f"Diverse listener diversity {dna['dimensions']['diversity']} should be >= 0.9"
    )


# ---------------------------------------------------------------------------
# 5. Cache hit returns cached result
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_build_music_dna_cache_hit(engine):
    """If a cached DNA entry exists, the Spotify client should not be called."""
    cached_dna = {
        "spotify_id": "user1",
        "dimensions": {"energy": 0.7, "valence": 0.6, "danceability": 0.65,
                       "acousticness": 0.3, "speechiness": 0.4, "diversity": 0.5},
        "metadata": {"total_artists_analyzed": 10, "total_tracks_analyzed": 20,
                     "unique_genres": ["pop"], "avg_popularity": 0.7, "avg_era": 0.8,
                     "source": "genres+popularity+era"},
        "source": "genres+popularity+era",
    }
    engine.get_spotify_client = AsyncMock()

    with patch("app.ml.recommender.get_cache", new=AsyncMock(return_value=json.dumps(cached_dna))):
        result = await engine.build_music_dna("user1", "token")

    engine.get_spotify_client.assert_not_called()
    assert result["dimensions"]["energy"] == 0.7


# ---------------------------------------------------------------------------
# 6. No Spotify data → error dict (not exception)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_build_music_dna_no_data(engine):
    """If Spotify returns no artists or tracks, return an error dict (not raise)."""
    sp = _make_sp([], [])
    engine.get_spotify_client = AsyncMock(return_value=sp)

    with patch("app.ml.recommender.get_cache", new=AsyncMock(return_value=None)), \
         patch("app.ml.recommender.set_cache", new=AsyncMock()):
        result = await engine.build_music_dna("empty_user", "token")

    assert "error" in result


# ---------------------------------------------------------------------------
# 7. Era metadata reflects release years
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_build_music_dna_era_recent(engine):
    """Tracks all from 2022+ should yield avg_era > 0.9."""
    artists = [_make_artist("a1", ["pop"])]
    tracks = [_make_track(f"t{i}", release_year=2023) for i in range(10)]
    sp = _make_sp(artists, tracks)
    engine.get_spotify_client = AsyncMock(return_value=sp)

    with patch("app.ml.recommender.get_cache", new=AsyncMock(return_value=None)), \
         patch("app.ml.recommender.set_cache", new=AsyncMock()):
        dna = await engine.build_music_dna("recent_user", "token")

    assert dna["metadata"]["avg_era"] > 0.9, (
        f"Recent-music listener era {dna['metadata']['avg_era']} should be > 0.9"
    )


# ---------------------------------------------------------------------------
# 8. Spotify timeout fallback returns non-hanging payload
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_build_music_dna_timeout_fallback(engine):
    """When Spotify calls time out, DNA returns an immediate fallback payload."""
    sp = _make_sp([], [])
    engine.get_spotify_client = AsyncMock(return_value=sp)
    engine._spotify_call_with_timeout = AsyncMock(side_effect=asyncio.TimeoutError())

    with patch("app.ml.recommender.get_cache", new=AsyncMock(return_value=None)), \
         patch("app.ml.recommender.set_cache", new=AsyncMock()):
        dna = await engine.build_music_dna("timeout_user", "token")

    assert dna["status"] == "fallback"
    assert dna["source"] == "fallback"
    assert dna["metadata"]["fallback_reasons"]
    assert dna["dimensions"]["energy"] == 0.5


@pytest.mark.asyncio
async def test_build_music_dna_avg_popularity_is_computed(engine):
    """avg_popularity should reflect real top-track popularity (not a fake fixed value)."""
    artists = [_make_artist("a1", ["pop"])]
    tracks = [
        _make_track("t1", popularity=80),
        _make_track("t2", popularity=60),
    ]
    sp = _make_sp(artists, tracks)
    engine.get_spotify_client = AsyncMock(return_value=sp)

    with patch("app.ml.recommender.get_cache", new=AsyncMock(return_value=None)), \
         patch("app.ml.recommender.set_cache", new=AsyncMock()):
        dna = await engine.build_music_dna("pop_user", "token")

    assert dna["status"] in {"ok", "degraded"}
    assert dna["metadata"]["avg_popularity"] == 0.7
