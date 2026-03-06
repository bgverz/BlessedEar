from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Dict, Any, List, Optional, Tuple
import logging
import json

from app.api.auth import get_current_user, get_valid_access_token
from app.core.database import get_cache, set_cache
from app.core.perf import RoutePerf
from app.ml.recommender import RecommendationEngine

router = APIRouter()
logger = logging.getLogger(__name__)
recommendation_engine = RecommendationEngine()


def _safe_ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return max(0.0, min(1.0, numerator / denominator))


def _trait_level(value: float) -> str:
    if value >= 0.67:
        return "High"
    if value >= 0.34:
        return "Medium"
    return "Low"


def _pick_album_image(track: Dict[str, Any]) -> Optional[str]:
    album = track.get("album") or {}
    images = album.get("images") or []
    return recommendation_engine._select_album_image_url(images)


def _parse_artist_list(track: Dict[str, Any]) -> List[Tuple[str, str]]:
    artists = track.get("artists") or []
    parsed: List[Tuple[str, str]] = []
    for artist in artists:
        if isinstance(artist, dict):
            aid = artist.get("id") or artist.get("name") or "unknown"
            name = artist.get("name") or "Unknown Artist"
            parsed.append((aid, name))
        elif isinstance(artist, str):
            parsed.append((artist, artist))
    return parsed


def _build_archetype(
    genre_variety: float,
    artist_loyalty: float,
    discovery_score: float,
    mainstream_index: float,
    deep_cut_ratio: float,
    top_genres: List[str],
    avg_release_year: Optional[float],
) -> str:
    lower_genres = " ".join(top_genres).lower()

    if any(k in lower_genres for k in ["ambient", "dream", "chill", "lofi"]):
        return "Atmospheric Explorer"
    if deep_cut_ratio >= 0.38 and mainstream_index <= 0.45:
        return "Deep Cut Hunter"
    if any(k in lower_genres for k in ["indie", "alternative"]) and mainstream_index < 0.6:
        return "Indie Curator"
    if genre_variety >= 0.65 and discovery_score >= 0.5:
        return "Genre Wanderer"
    if artist_loyalty >= 0.6:
        return "Album Loyalist"
    if avg_release_year is not None and avg_release_year <= 2006:
        return "Nostalgic Listener"
    return "Sonic Adventurer"


async def _get_top_artists_all_ranges(sp, timeout_seconds: float = 8.0) -> List[Dict[str, Any]]:
    artists: List[Dict[str, Any]] = []
    seen_ids = set()

    for time_range in ("short_term", "medium_term", "long_term"):
        try:
            result = await recommendation_engine._spotify_call_with_timeout(
                sp.current_user_top_artists,
                time_range=time_range,
                limit=30,
                timeout_seconds=timeout_seconds,
                call_name=f"analytics.current_user_top_artists[{time_range}]",
            )
            for artist in result.get("items", []):
                aid = artist.get("id")
                if aid and aid not in seen_ids:
                    artists.append(artist)
                    seen_ids.add(aid)
        except Exception as exc:
            logger.warning("Analytics top-artists fetch failed (%s): %s", time_range, exc)

    return artists


def _build_genre_breakdown(
    top_artists: List[Dict[str, Any]],
    artist_play_counts: Dict[str, int],
    limit: int = 8,
) -> List[Dict[str, Any]]:
    weighted: Dict[str, float] = {}
    for artist in top_artists:
        genres = artist.get("genres") or []
        if not genres:
            continue
        aid = artist.get("id")
        weight = float(artist_play_counts.get(aid, 1))
        per_genre_weight = weight / max(len(genres), 1)
        for genre in genres:
            weighted[genre] = weighted.get(genre, 0.0) + per_genre_weight

    if not weighted:
        return []

    total = sum(weighted.values()) or 1.0
    ranked = sorted(weighted.items(), key=lambda x: x[1], reverse=True)[:limit]
    return [
        {"genre": genre, "percentage": round((score / total) * 100, 1)}
        for genre, score in ranked
    ]


async def _compute_taste_signals(
    spotify_id: str,
    sp,
    time_range: str = "medium_term",
) -> Dict[str, Any]:
    all_tracks = await recommendation_engine._get_user_library_cached(spotify_id, sp)
    top_artists = await _get_top_artists_all_ranges(sp)

    if not all_tracks:
        return {
            "total_tracks": 0,
            "unique_artists": 0,
            "artist_play_counts": {},
            "discovery_score": 0.0,
            "artist_loyalty": 0.0,
            "mainstream_index": 0.0,
            "deep_cut_ratio": 0.0,
            "genre_breakdown": [],
            "top_genres": [],
            "hidden_gems": [],
            "avg_release_year": None,
        }

    artist_play_counts: Dict[str, int] = {}
    artist_names: Dict[str, str] = {}
    popularities: List[int] = []
    release_years: List[int] = []
    hidden_gems: List[Dict[str, Any]] = []

    for track in all_tracks:
        for aid, artist_name in _parse_artist_list(track):
            artist_play_counts[aid] = artist_play_counts.get(aid, 0) + 1
            artist_names[aid] = artist_name

        popularity = track.get("popularity")
        if isinstance(popularity, (int, float)):
            pop_int = int(popularity)
            popularities.append(pop_int)
            if pop_int < 30:
                hidden_gems.append({
                    "id": track.get("id"),
                    "name": track.get("name", "Unknown Track"),
                    "artists": [name for _, name in _parse_artist_list(track)],
                    "popularity": pop_int,
                    "album_image_url": _pick_album_image(track),
                })

        release_date = (track.get("album") or {}).get("release_date")
        if isinstance(release_date, str) and len(release_date) >= 4 and release_date[:4].isdigit():
            release_years.append(int(release_date[:4]))

    total_tracks = len(all_tracks)
    unique_artists = len(artist_play_counts)
    discovery_score = _safe_ratio(unique_artists, total_tracks)

    top_artist_counts = sorted(artist_play_counts.values(), reverse=True)[:5]
    artist_loyalty = _safe_ratio(sum(top_artist_counts), total_tracks)

    mainstream_index = _safe_ratio(sum(popularities), len(popularities) * 100) if popularities else 0.0
    deep_cut_ratio = _safe_ratio(sum(1 for p in popularities if p < 30), len(popularities)) if popularities else 0.0

    genre_breakdown = _build_genre_breakdown(top_artists, artist_play_counts, limit=8)
    top_genres = [g["genre"] for g in genre_breakdown[:6]]
    avg_release_year = (sum(release_years) / len(release_years)) if release_years else None

    unique_hidden = {}
    for gem in hidden_gems:
        tid = gem.get("id")
        if tid and tid not in unique_hidden:
            unique_hidden[tid] = gem
    hidden_gems_sorted = sorted(unique_hidden.values(), key=lambda t: t["popularity"])[:5]

    return {
        "total_tracks": total_tracks,
        "unique_artists": unique_artists,
        "artist_play_counts": artist_play_counts,
        "discovery_score": round(discovery_score, 3),
        "artist_loyalty": round(artist_loyalty, 3),
        "mainstream_index": round(mainstream_index, 3),
        "deep_cut_ratio": round(deep_cut_ratio, 3),
        "genre_breakdown": genre_breakdown,
        "top_genres": top_genres,
        "hidden_gems": hidden_gems_sorted,
        "avg_release_year": round(avg_release_year, 1) if avg_release_year is not None else None,
    }


async def _get_signals_cached(spotify_id: str, sp, time_range: str) -> Dict[str, Any]:
    cache_key = f"analytics:signals:{spotify_id}:{time_range}"
    cached = await get_cache(cache_key)
    if cached:
        try:
            logger.info("Analytics cache hit spotify_id=%s cache_key=%s", spotify_id, cache_key)
            return json.loads(cached)
        except Exception:
            pass

    signals = await _compute_taste_signals(spotify_id, sp, time_range=time_range)
    try:
        await set_cache(cache_key, json.dumps(signals), expire=900)
    except Exception:
        pass
    return signals


@router.get("/taste-profile")
async def get_taste_profile(current_user: dict = Depends(get_current_user)):
    perf = RoutePerf("analytics_taste_profile", current_user.get("spotify_id"))
    try:
        spotify_id = current_user.get("spotify_id", "unknown")
        with perf.step("auth"):
            access_token = await get_valid_access_token(current_user)
        with perf.step("spotify_client"):
            sp = await recommendation_engine.get_spotify_client(access_token)
        with perf.step("signals_cached"):
            signals = await _get_signals_cached(spotify_id, sp, time_range="medium_term")
        archetype = _build_archetype(
            genre_variety=_safe_ratio(len(signals["top_genres"]), 8),
            artist_loyalty=signals["artist_loyalty"],
            discovery_score=signals["discovery_score"],
            mainstream_index=signals["mainstream_index"],
            deep_cut_ratio=signals["deep_cut_ratio"],
            top_genres=signals["top_genres"],
            avg_release_year=signals["avg_release_year"],
        )

        traits = [
            {
                "name": "Genre Variety",
                "value": round(_safe_ratio(len(signals["top_genres"]), 8) * 100),
                "level": _trait_level(_safe_ratio(len(signals["top_genres"]), 8)),
            },
            {
                "name": "Artist Loyalty",
                "value": round(signals["artist_loyalty"] * 100),
                "level": _trait_level(signals["artist_loyalty"]),
            },
            {
                "name": "Exploration Level",
                "value": round(signals["discovery_score"] * 100),
                "level": _trait_level(signals["discovery_score"]),
            },
            {
                "name": "Underground Lean",
                "value": round((1 - signals["mainstream_index"]) * 100),
                "level": _trait_level(1 - signals["mainstream_index"]),
            },
        ]

        payload = {
            "spotify_id": spotify_id,
            "archetype": archetype,
            "top_genres": signals["top_genres"][:6],
            "traits": traits,
            "signals": {
                "discovery_score": signals["discovery_score"],
                "artist_loyalty": signals["artist_loyalty"],
                "mainstream_index": signals["mainstream_index"],
                "deep_cut_ratio": signals["deep_cut_ratio"],
            },
        }
        logger.info("Taste profile payload spotify_id=%s archetype=%s", spotify_id, archetype)
        perf.set_meta("top_genres", len(payload["top_genres"]))
        perf.set_meta("hidden_gems", len(signals["hidden_gems"]))
        logger.info("[perf] %s", perf.to_log_fields())
        return payload

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Taste profile failed: %s", exc)
        logger.info("[perf] %s", perf.to_log_fields())
        raise HTTPException(status_code=500, detail="Unable to compute taste profile")


@router.get("/listening-insights")
async def get_listening_insights(
    time_range: str = Query("medium_term", regex="^(short_term|medium_term|long_term)$"),
    current_user: dict = Depends(get_current_user),
):
    perf = RoutePerf("analytics_listening_insights", current_user.get("spotify_id"))
    try:
        spotify_id = current_user.get("spotify_id", "unknown")
        with perf.step("auth"):
            access_token = await get_valid_access_token(current_user)
        with perf.step("spotify_client"):
            sp = await recommendation_engine.get_spotify_client(access_token)
        with perf.step("signals_cached"):
            signals = await _get_signals_cached(spotify_id, sp, time_range=time_range)
        archetype = _build_archetype(
            genre_variety=_safe_ratio(len(signals["top_genres"]), 8),
            artist_loyalty=signals["artist_loyalty"],
            discovery_score=signals["discovery_score"],
            mainstream_index=signals["mainstream_index"],
            deep_cut_ratio=signals["deep_cut_ratio"],
            top_genres=signals["top_genres"],
            avg_release_year=signals["avg_release_year"],
        )

        payload = {
            "spotify_id": spotify_id,
            "time_range": time_range,
            "archetype": archetype,
            "listening_insights": {
                "discovery_score": signals["discovery_score"],
                "artist_loyalty": signals["artist_loyalty"],
                "mainstream_index": signals["mainstream_index"],
            },
            "sound_profile": {
                "genre_breakdown": signals["genre_breakdown"][:6],
            },
            "hidden_gems": signals["hidden_gems"][:5],
        }
        logger.info(
            "Listening insights payload spotify_id=%s time_range=%s discovery=%.3f loyalty=%.3f mainstream=%.3f",
            spotify_id,
            time_range,
            signals["discovery_score"],
            signals["artist_loyalty"],
            signals["mainstream_index"],
        )
        perf.set_meta("hidden_gems", len(payload["hidden_gems"]))
        perf.set_meta("genre_breakdown", len(payload["sound_profile"]["genre_breakdown"]))
        logger.info("[perf] %s", perf.to_log_fields())
        return payload

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Listening insights failed: %s", exc)
        logger.info("[perf] %s", perf.to_log_fields())
        raise HTTPException(status_code=500, detail="Unable to compute listening insights")
