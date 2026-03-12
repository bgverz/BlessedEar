from fastapi import APIRouter, Depends, HTTPException, Query, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from typing import List, Optional, Dict, Any, Set, Tuple
from pydantic import BaseModel, Field
import asyncio
import logging
import time
import spotipy
import random
from collections import Counter
import json

from app.api.auth import get_current_user, get_valid_access_token
from app.core.config import get_settings
from app.core.database import get_cache, set_cache
from app.core.perf import RoutePerf
from app.ml.recommender import RecommendationEngine

router = APIRouter()
settings = get_settings()
logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)

class RecommendationRequest(BaseModel):
    seed_tracks: Optional[List[str]] = None
    target_features: Optional[Dict[str, float]] = None
    limit: int = 20

class MoodPlaylistRequest(BaseModel):
    mood: str
    limit: int = 20

class RecommendationResponse(BaseModel):
    tracks: List[Dict[str, Any]]
    user_profile: Optional[Dict[str, Any]] = None
    generation_time: Optional[float] = None


class DiscoverGenreCard(BaseModel):
    genre: str = ""
    description: str = ""
    sample_artists: List[str] = Field(default_factory=list)


class DiscoverArtistCard(BaseModel):
    id: str = ""
    name: str = ""
    genres: List[str] = Field(default_factory=list)
    image_url: Optional[str] = None
    popularity: Optional[int] = 0
    reason: str = ""
    external_urls: Dict[str, Any] = Field(default_factory=dict)


class DiscoverTrackCard(BaseModel):
    id: str = ""
    name: str = ""
    artists: List[str] = Field(default_factory=list)
    album: str = ""
    album_images: List[Dict[str, Any]] = Field(default_factory=list)
    album_image_url: Optional[str] = None
    popularity: Optional[int] = 0
    preview_url: Optional[str] = None
    external_urls: Dict[str, Any] = Field(default_factory=dict)
    recommendation_reason: str = ""


class DiscoverArtistDetailResponse(BaseModel):
    artist: DiscoverArtistCard = Field(default_factory=DiscoverArtistCard)
    top_tracks: List[DiscoverTrackCard] = Field(default_factory=list)
    similar_artists: List[DiscoverArtistCard] = Field(default_factory=list)


class DiscoverExplorerResponse(BaseModel):
    outside_your_bubble: List[DiscoverGenreCard] = Field(default_factory=list)
    artists_you_should_know: List[DiscoverArtistCard] = Field(default_factory=list)
    underground_radar: List[DiscoverTrackCard] = Field(default_factory=list)
    trending_outside_your_taste: List[DiscoverTrackCard] = Field(default_factory=list)

recommendation_engine = RecommendationEngine()

OUTSIDE_BUBBLE_GENRE_BRIDGES: Dict[str, List[str]] = {
    "rap": ["neo soul", "indie rock", "jazz fusion", "dream pop", "afrobeats"],
    "hip hop": ["neo soul", "jazz fusion", "indie pop", "house", "afrobeats"],
    "latin": ["indie rock", "neo soul", "house", "jazz fusion", "alt pop"],
    "reggaeton": ["afrobeats", "indie pop", "neo soul", "house", "jazz fusion"],
    "pop": ["indie rock", "house", "neo soul", "afrobeats", "jazz fusion"],
    "rock": ["alt pop", "neo soul", "house", "afrobeats", "r&b"],
    "indie": ["afrobeats", "neo soul", "house", "latin pop", "jazz fusion"],
    "electronic": ["neo soul", "indie rock", "afrobeats", "latin pop", "jazz fusion"],
    "r&b": ["indie rock", "house", "afrobeats", "alt pop", "jazz fusion"],
}

GENRE_SCENE_BUCKETS: Dict[str, str] = {
    "neo soul": "soulful",
    "dream pop": "atmospheric",
    "indie rock": "guitar",
    "afrobeats": "global-rhythm",
    "jazz fusion": "instrumental",
    "house": "electronic-dance",
    "alt pop": "alt-pop",
    "latin pop": "latin-mainstream",
}

GENRE_DESCRIPTIONS: Dict[str, str] = {
    "neo soul": "Warm grooves, rich vocals, and soulful modern textures.",
    "dream pop": "Atmospheric melodies and hazy, emotional songwriting.",
    "indie rock": "Guitar-forward storytelling with creative, non-mainstream energy.",
    "afrobeats": "Rhythmic, high-feel percussion and melodic global pop crossover.",
    "jazz fusion": "Improvisational jazz blended with modern groove and harmony.",
    "house": "Dance-driven electronic pulse with euphoric and hypnotic layers.",
    "alt pop": "Pop songwriting with left-field production and moodier tone.",
    "latin pop": "Hook-heavy Latin melodies with global crossover momentum.",
}


def _normalize_spotify_track(track: Dict[str, Any], reason: str = "") -> Optional[Dict[str, Any]]:
    if not isinstance(track, dict):
        return None
    track_id = track.get("id")
    if not isinstance(track_id, str) or not track_id:
        return None

    album = track.get("album") if isinstance(track.get("album"), dict) else {}
    album_images = album.get("images") if isinstance(album.get("images"), list) else []
    artists_raw = track.get("artists") if isinstance(track.get("artists"), list) else []
    artists = [a.get("name") for a in artists_raw if isinstance(a, dict) and isinstance(a.get("name"), str)]
    if not artists:
        artists = ["Unknown Artist"]

    return {
        "id": track_id,
        "name": track.get("name") or "Unknown Track",
        "artists": artists,
        "album": album.get("name") if isinstance(album.get("name"), str) else "",
        "album_images": album_images,
        "album_image_url": recommendation_engine._select_album_image_url(album_images),
        "popularity": track.get("popularity", 0) if isinstance(track.get("popularity"), int) else 0,
        "preview_url": track.get("preview_url"),
        "external_urls": track.get("external_urls", {}),
        "recommendation_reason": reason or "Discovery track",
    }


def _normalize_artist(artist: Dict[str, Any], reason: str = "") -> Optional[Dict[str, Any]]:
    if not isinstance(artist, dict):
        return None
    artist_id = artist.get("id")
    name = artist.get("name")
    if not isinstance(artist_id, str) or not artist_id or not isinstance(name, str):
        return None
    images = artist.get("images") if isinstance(artist.get("images"), list) else []
    genres = [g for g in (artist.get("genres") or []) if isinstance(g, str)]
    return {
        "id": artist_id,
        "name": name,
        "genres": genres[:3],
        "image_url": recommendation_engine._select_album_image_url(images),
        "popularity": artist.get("popularity", 0) if isinstance(artist.get("popularity"), int) else 0,
        "reason": reason or "Adjacent to your taste",
        "external_urls": artist.get("external_urls", {}),
    }


def _genre_overlap_score(artist_genres: List[str], user_genres: Set[str]) -> float:
    if not artist_genres or not user_genres:
        return 0.0
    normalized_artist = {g.lower() for g in artist_genres}
    return float(len(normalized_artist & user_genres))


async def _build_discover_context(
    current_user: dict,
    access_token: str,
    perf: Optional[RoutePerf] = None,
) -> Dict[str, Any]:
    sp = await recommendation_engine.get_spotify_client(access_token)
    spotify_id = current_user.get("spotify_id", "unknown")

    top_artists_cache_key = f"top_artists:{spotify_id}:all:20"
    top_tracks_cache_key = f"top_tracks:{spotify_id}:medium_term:50"

    top_artists: List[Dict[str, Any]] = []
    top_tracks: List[Dict[str, Any]] = []

    cached_artists = await get_cache(top_artists_cache_key)
    if cached_artists:
        try:
            top_artists = json.loads(cached_artists)
            if perf:
                perf.add_count("cache_hit")
        except Exception:
            top_artists = []
    if not top_artists:
        top_artists = await recommendation_engine._get_user_top_artists(sp)
        if perf:
            perf.add_count("spotify_calls", 3)
            perf.add_count("cache_miss")
        try:
            await set_cache(top_artists_cache_key, json.dumps(top_artists), expire=21600)
        except Exception:
            pass

    cached_tracks = await get_cache(top_tracks_cache_key)
    if cached_tracks:
        try:
            top_tracks = json.loads(cached_tracks)
            if perf:
                perf.add_count("cache_hit")
        except Exception:
            top_tracks = []
    if not top_tracks:
        top_tracks = await recommendation_engine.get_user_top_tracks(sp=sp, time_range="medium_term", limit=50)
        if perf:
            perf.add_count("spotify_calls")
            perf.add_count("cache_miss")
        try:
            await set_cache(top_tracks_cache_key, json.dumps(top_tracks), expire=21600)
        except Exception:
            pass

    genre_counts: Counter = Counter()
    top_artist_ids: Set[str] = set()
    for artist in top_artists:
        if not isinstance(artist, dict):
            continue
        aid = artist.get("id")
        if isinstance(aid, str):
            top_artist_ids.add(aid)
        for genre in artist.get("genres") or []:
            if isinstance(genre, str):
                genre_counts[genre.lower()] += 1

    user_track_ids = {
        t.get("id")
        for t in top_tracks
        if isinstance(t, dict) and isinstance(t.get("id"), str)
    }

    return {
        "sp": sp,
        "top_artists": [a for a in top_artists if isinstance(a, dict)],
        "top_tracks": [t for t in top_tracks if isinstance(t, dict)],
        "top_artist_ids": top_artist_ids,
        "top_genres": [g for g, _ in genre_counts.most_common(8)],
        "user_genres_set": set(genre_counts.keys()),
        "user_track_ids": user_track_ids,
    }


def _pick_outside_genres(top_genres: List[str]) -> List[str]:
    bridge_scores: Counter = Counter()
    for user_genre in top_genres:
        for key, candidates in OUTSIDE_BUBBLE_GENRE_BRIDGES.items():
            if key in user_genre:
                for genre in candidates:
                    bridge_scores[genre] += 2
    if not bridge_scores:
        bridge_scores.update({"neo soul": 2, "dream pop": 2, "afrobeats": 2, "house": 2, "jazz fusion": 2})

    user_blob = " ".join(top_genres)
    picked: List[str] = []
    seen_scenes: Set[str] = set()
    ranked = bridge_scores.most_common(12)
    for genre, _ in ranked:
        if genre.lower() in user_blob:
            continue
        scene = GENRE_SCENE_BUCKETS.get(genre.lower(), genre.lower())
        if scene in seen_scenes:
            continue
        picked.append(genre)
        seen_scenes.add(scene)
        if len(picked) >= 6:
            break
    if len(picked) < 6:
        for genre, _ in ranked:
            if genre.lower() in user_blob or genre in picked:
                continue
            picked.append(genre)
            if len(picked) >= 6:
                break
    return picked


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _normalize_cache_key_fragment(value: str) -> str:
    cleaned = " ".join((value or "").strip().lower().split())
    return cleaned.replace(":", "_")[:180]


def _first_artist(track: Dict[str, Any]) -> str:
    artists = track.get("artists")
    if isinstance(artists, list) and artists:
        first = artists[0]
        if isinstance(first, str):
            return first.strip().lower()
        if isinstance(first, dict) and isinstance(first.get("name"), str):
            return first["name"].strip().lower()
    return "unknown-artist"


def _album_key(track: Dict[str, Any]) -> str:
    album = track.get("album")
    if isinstance(album, str) and album.strip():
        return album.strip().lower()
    if isinstance(album, dict) and isinstance(album.get("name"), str):
        return album["name"].strip().lower()
    return ""


def _popularity_band(popularity: int) -> str:
    if popularity >= 75:
        return "high"
    if popularity >= 45:
        return "mid"
    return "low"


def _dedupe_track_candidates(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    best: Dict[str, Dict[str, Any]] = {}
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        tid = candidate.get("id")
        if not isinstance(tid, str) or not tid:
            continue
        score = float(candidate.get("_score", 0.0))
        if tid not in best or score > float(best[tid].get("_score", 0.0)):
            best[tid] = candidate
    return list(best.values())


def _diversify_track_candidates(
    candidates: List[Dict[str, Any]],
    limit: int,
    *,
    max_per_artist: int = 1,
    max_per_album: int = 1,
    max_per_source: int = 4,
    enforce_pop_band_mix: bool = True,
) -> List[Dict[str, Any]]:
    pool = _dedupe_track_candidates(candidates)
    random.shuffle(pool)
    pool.sort(key=lambda x: float(x.get("_score", 0.0)), reverse=True)

    selected: List[Dict[str, Any]] = []
    artist_counts: Counter = Counter()
    album_counts: Counter = Counter()
    source_counts: Counter = Counter()
    band_counts: Counter = Counter()
    band_cap = max(2, (limit + 1) // 2)

    def can_take(track: Dict[str, Any], relaxed: bool = False) -> bool:
        artist = _first_artist(track)
        album = _album_key(track)
        source = str(track.get("_source", "unknown"))
        band = _popularity_band(int(track.get("popularity", 0) or 0))

        if artist_counts[artist] >= (max_per_artist if not relaxed else max_per_artist + 1):
            return False
        if album and album_counts[album] >= (max_per_album if not relaxed else max_per_album + 1):
            return False
        if max_per_source > 0 and source_counts[source] >= (max_per_source if not relaxed else max_per_source + 1):
            return False
        if enforce_pop_band_mix and band_counts[band] >= (band_cap if not relaxed else band_cap + 1):
            return False
        return True

    for track in pool:
        if len(selected) >= limit:
            break
        if not can_take(track, relaxed=False):
            continue
        selected.append(track)
        artist_counts[_first_artist(track)] += 1
        album_key = _album_key(track)
        if album_key:
            album_counts[album_key] += 1
        source_counts[str(track.get("_source", "unknown"))] += 1
        band_counts[_popularity_band(int(track.get("popularity", 0) or 0))] += 1

    if len(selected) < limit:
        for track in pool:
            if len(selected) >= limit:
                break
            tid = track.get("id")
            if tid in {t.get("id") for t in selected}:
                continue
            if not can_take(track, relaxed=True):
                continue
            selected.append(track)
            artist_counts[_first_artist(track)] += 1
            album_key = _album_key(track)
            if album_key:
                album_counts[album_key] += 1
            source_counts[str(track.get("_source", "unknown"))] += 1
            band_counts[_popularity_band(int(track.get("popularity", 0) or 0))] += 1

    return selected[:limit]


def _diversify_artist_candidates(
    candidates: List[Tuple[float, Dict[str, Any]]],
    limit: int,
    *,
    max_per_scene: int = 2,
) -> List[Dict[str, Any]]:
    deduped: Dict[str, Tuple[float, Dict[str, Any]]] = {}
    for score, artist in candidates:
        if not isinstance(artist, dict):
            continue
        aid = artist.get("id")
        if not isinstance(aid, str) or not aid:
            continue
        if aid not in deduped or score > deduped[aid][0]:
            deduped[aid] = (score, artist)

    ranked = list(deduped.values())
    random.shuffle(ranked)
    ranked.sort(key=lambda x: x[0], reverse=True)

    scene_counts: Counter = Counter()
    selected: List[Dict[str, Any]] = []
    for _, artist in ranked:
        scene = str(artist.get("_scene", "misc"))
        if scene_counts[scene] >= max_per_scene:
            continue
        selected.append(artist)
        scene_counts[scene] += 1
        if len(selected) >= limit:
            break

    if len(selected) < limit:
        for _, artist in ranked:
            aid = artist.get("id")
            if aid in {a.get("id") for a in selected}:
                continue
            selected.append(artist)
            if len(selected) >= limit:
                break
    return selected[:limit]


async def _safe_spotify_search(
    sp: spotipy.Spotify,
    query: str,
    search_type: str,
    limit: int,
    call_name: str,
    perf: Optional[RoutePerf] = None,
    sem: Optional[asyncio.Semaphore] = None,
) -> List[Dict[str, Any]]:
    cache_key = f"search:{search_type}:{_normalize_cache_key_fragment(query)}:{limit}"
    cached = await get_cache(cache_key)
    if cached:
        try:
            if perf:
                perf.add_count("cache_hit")
            return json.loads(cached)
        except Exception:
            pass
    try:
        if sem:
            async with sem:
                result = await recommendation_engine._spotify_call_with_timeout(
                    sp.search,
                    q=query,
                    type=search_type,
                    market="US",
                    limit=limit,
                    timeout_seconds=8.0,
                    call_name=call_name,
                )
        else:
            result = await recommendation_engine._spotify_call_with_timeout(
                sp.search,
                q=query,
                type=search_type,
                market="US",
                limit=limit,
                timeout_seconds=8.0,
                call_name=call_name,
            )
        if perf:
            perf.add_count("spotify_calls")
            perf.add_count("cache_miss")
        if not isinstance(result, dict):
            return []
        container = result.get(f"{search_type}s")
        if not isinstance(container, dict):
            return []
        items = [item for item in _safe_list(container.get("items")) if isinstance(item, dict)]
        try:
            await set_cache(cache_key, json.dumps(items), expire=7200)
        except Exception:
            pass
        return items
    except Exception as exc:
        logger.warning("Spotify search failed query='%s' type=%s: %s", query, search_type, exc)
        return []


async def _safe_playlist_tracks(
    sp: spotipy.Spotify,
    playlist_id: str,
    limit: int = 30,
    perf: Optional[RoutePerf] = None,
    sem: Optional[asyncio.Semaphore] = None,
) -> List[Dict[str, Any]]:
    if not isinstance(playlist_id, str) or not playlist_id:
        return []
    cache_key = f"playlist_items:{playlist_id}:{limit}"
    cached = await get_cache(cache_key)
    if cached:
        try:
            if perf:
                perf.add_count("cache_hit")
            return json.loads(cached)
        except Exception:
            pass
    try:
        if sem:
            async with sem:
                result = await recommendation_engine._spotify_call_with_timeout(
                    sp.playlist_items,
                    playlist_id=playlist_id,
                    fields="items(track(id,name,artists,album,external_urls,popularity))",
                    limit=limit,
                    market="US",
                    timeout_seconds=8.0,
                    call_name=f"discover_playlist_items[{playlist_id}]",
                )
        else:
            result = await recommendation_engine._spotify_call_with_timeout(
                sp.playlist_items,
                playlist_id=playlist_id,
                fields="items(track(id,name,artists,album,external_urls,popularity))",
                limit=limit,
                market="US",
                timeout_seconds=8.0,
                call_name=f"discover_playlist_items[{playlist_id}]",
            )
        if perf:
            perf.add_count("spotify_calls")
            perf.add_count("cache_miss")
        if not isinstance(result, dict):
            return []
        tracks: List[Dict[str, Any]] = []
        for item in _safe_list(result.get("items")):
            if not isinstance(item, dict):
                continue
            track = item.get("track")
            if isinstance(track, dict):
                tracks.append(track)
        try:
            await set_cache(cache_key, json.dumps(tracks), expire=21600)
        except Exception:
            pass
        return tracks
    except Exception as exc:
        logger.warning("Playlist items fetch failed playlist_id=%s: %s", playlist_id, exc)
        return []


async def _module_outside_bubble(
    context: Dict[str, Any],
    limit: int,
    perf: Optional[RoutePerf] = None,
    sem: Optional[asyncio.Semaphore] = None,
) -> List[Dict[str, Any]]:
    sp = context["sp"]
    outside_genres = _pick_outside_genres(context["top_genres"])[:limit]
    cards: List[Dict[str, Any]] = []
    for genre in outside_genres:
        artists = await _safe_spotify_search(
            sp,
            query=f'genre:"{genre}"',
            search_type="artist",
            limit=6,
            call_name=f"outside_bubble_artist_search[{genre}]",
            perf=perf,
            sem=sem,
        )
        sample_artist_names = [
            a.get("name")
            for a in artists
            if isinstance(a.get("name"), str)
        ][:3]
        cards.append({
            "genre": genre,
            "description": GENRE_DESCRIPTIONS.get(genre, "A fresh lane adjacent to your taste profile."),
            "sample_artists": sample_artist_names,
        })
    random.shuffle(cards)
    return cards[:limit]


async def _module_artists_you_should_know(
    context: Dict[str, Any],
    outside_genres: List[str],
    limit: int,
    perf: Optional[RoutePerf] = None,
    sem: Optional[asyncio.Semaphore] = None,
) -> List[Dict[str, Any]]:
    sp = context["sp"]
    user_genres_set: Set[str] = context["user_genres_set"]
    top_artist_ids: Set[str] = context["top_artist_ids"]
    candidates: List[Tuple[float, Dict[str, Any]]] = []
    seen_ids: Set[str] = set()

    for genre in outside_genres[:6]:
        scene = GENRE_SCENE_BUCKETS.get(genre.lower(), genre.lower())
        genre_artists = await _safe_spotify_search(
            sp,
            query=f'genre:"{genre}"',
            search_type="artist",
            limit=12,
            call_name=f"artists_should_know_search[{genre}]",
            perf=perf,
            sem=sem,
        )
        for artist in genre_artists:
            normalized = _normalize_artist(artist, reason="Popular in your adjacent genres")
            if not normalized:
                continue
            aid = normalized["id"]
            if aid in seen_ids or aid in top_artist_ids:
                continue
            seen_ids.add(aid)
            overlap = _genre_overlap_score(normalized["genres"], user_genres_set)
            score = overlap * 1.6 + ((normalized.get("popularity") or 0) / 45.0)
            if overlap == 0:
                normalized["reason"] = "A new scene just outside your usual taste"
            elif (normalized.get("popularity") or 0) < 45:
                normalized["reason"] = "A deeper cut for your taste profile"
            normalized["_scene"] = scene
            normalized["_source"] = "genre-search"
            candidates.append((score, normalized))

        playlists = await _safe_spotify_search(
            sp,
            query=f"{genre} mix",
            search_type="playlist",
            limit=3,
            call_name=f"artists_should_know_playlist_search[{genre}]",
            perf=perf,
            sem=sem,
        )
        for playlist in playlists:
            pid = playlist.get("id")
            if not isinstance(pid, str):
                continue
            for track in await _safe_playlist_tracks(sp, pid, limit=20, perf=perf, sem=sem):
                for raw_artist in _safe_list(track.get("artists")):
                    if not isinstance(raw_artist, dict):
                        continue
                    aid = raw_artist.get("id")
                    aname = raw_artist.get("name")
                    if not isinstance(aid, str) or not isinstance(aname, str):
                        continue
                    if aid in seen_ids or aid in top_artist_ids:
                        continue
                    seen_ids.add(aid)
                    candidates.append((1.2, {
                        "id": aid,
                        "name": aname,
                        "genres": [],
                        "image_url": None,
                        "popularity": 0,
                        "reason": f"Spotted across {genre} playlist lanes",
                        "external_urls": {},
                        "_scene": scene,
                        "_source": "playlist-artist",
                    }))

    diversified = _diversify_artist_candidates(candidates, limit=limit, max_per_scene=2)
    return diversified


async def _module_underground_radar(
    context: Dict[str, Any],
    outside_genres: List[str],
    limit: int,
    max_popularity: int,
    perf: Optional[RoutePerf] = None,
    sem: Optional[asyncio.Semaphore] = None,
) -> List[Dict[str, Any]]:
    sp = context["sp"]
    user_track_ids: Set[str] = set(context["user_track_ids"])
    seen_ids: Set[str] = set()
    gems: List[Dict[str, Any]] = []
    queries = [f"{genre} underground" for genre in outside_genres[:4]] + [f"{genre} deep cuts" for genre in context["top_genres"][:2]]

    for query in queries:
        tracks = await _safe_spotify_search(
            sp,
            query=query,
            search_type="track",
            limit=24,
            call_name=f"underground_search[{query}]",
            perf=perf,
            sem=sem,
        )
        for track in tracks:
            normalized = _normalize_spotify_track(track, reason="Hidden gem in an adjacent scene")
            if not normalized:
                continue
            tid = normalized["id"]
            if tid in seen_ids or tid in user_track_ids:
                continue
            if normalized.get("popularity", 0) > max_popularity:
                continue
            normalized["_source"] = query
            normalized["_scene"] = query.split(" ")[0]
            normalized["_score"] = float(max_popularity - normalized.get("popularity", max_popularity)) + random.uniform(0, 0.2)
            seen_ids.add(tid)
            gems.append(normalized)
            if len(gems) >= limit * 2:
                break
        if len(gems) >= limit * 2:
            break

    diversified = _diversify_track_candidates(
        gems,
        limit=limit,
        max_per_artist=1,
        max_per_album=1,
        max_per_source=max(2, limit // 3),
        enforce_pop_band_mix=True,
    )
    return diversified


async def _module_trending_outside(
    context: Dict[str, Any],
    outside_genres: List[str],
    limit: int,
    perf: Optional[RoutePerf] = None,
    sem: Optional[asyncio.Semaphore] = None,
) -> List[Dict[str, Any]]:
    sp = context["sp"]
    user_track_ids: Set[str] = set(context["user_track_ids"])
    seen_ids: Set[str] = set()
    trending: List[Dict[str, Any]] = []
    for genre in outside_genres[:5]:
        tracks = await _safe_spotify_search(
            sp,
            query=f"{genre} hits",
            search_type="track",
            limit=20,
            call_name=f"trending_outside_search[{genre}]",
            perf=perf,
            sem=sem,
        )
        for track in tracks:
            normalized = _normalize_spotify_track(track, reason=f"Trending now in {genre}")
            if not normalized:
                continue
            tid = normalized["id"]
            if tid in seen_ids or tid in user_track_ids:
                continue
            if normalized.get("popularity", 0) < 60:
                continue
            normalized["_source"] = f"{genre}:hits"
            normalized["_scene"] = genre
            band_bonus = {"high": 0.2, "mid": 0.5, "low": 0.4}[_popularity_band(int(normalized.get("popularity", 0)))]
            normalized["_score"] = float(normalized.get("popularity", 0)) / 20.0 + band_bonus + random.uniform(0, 0.2)
            seen_ids.add(tid)
            trending.append(normalized)
    diversified = _diversify_track_candidates(
        trending,
        limit=limit,
        max_per_artist=1,
        max_per_album=1,
        max_per_source=max(2, limit // 3),
        enforce_pop_band_mix=True,
    )
    return diversified


def _normalize_top_track(track: Dict[str, Any]) -> Dict[str, Any]:
    album = track.get("album") or {}
    album_images = album.get("images") or []
    album_image_url = recommendation_engine._select_album_image_url(album_images)
    return {
        "id": track.get("id"),
        "name": track.get("name"),
        "artists": track.get("artists", []),
        "album": album,
        "album_images": album_images,
        "album_image_url": album_image_url,
        "popularity": track.get("popularity", 0),
        "preview_url": track.get("preview_url"),
        "external_urls": track.get("external_urls", {}),
    }


async def _require_access_token(current_user: dict) -> str:
    """
    Return a valid (auto-refreshed) Spotify access token or raise 401.
    Centralises the token-extraction logic so each endpoint stays lean.
    """
    tokens = current_user.get("spotify_tokens", {})
    if not tokens.get("access_token"):
        raise HTTPException(
            status_code=401,
            detail="Spotify access token not found. Please re-authenticate.",
        )
    return await get_valid_access_token(current_user)


@router.post("/generate", response_model=RecommendationResponse)
@limiter.limit("10/minute")
async def generate_recommendations(request: Request,
    body: RecommendationRequest,
    current_user: dict = Depends(get_current_user)
):
    """Generate personalized recommendations for user"""
    perf = RoutePerf("recommendations_generate", current_user.get("spotify_id"))
    try:
        with perf.step("auth"):
            access_token = await _require_access_token(current_user)
        with perf.step("ml_generate"):
            recommendations = await recommendation_engine.generate_recommendations(
                user_id=current_user["spotify_id"],
                access_token=access_token,
                seed_tracks=body.seed_tracks,
                target_features=body.target_features,
                limit=body.limit
            )

        if not recommendations:
            raise HTTPException(
                status_code=404,
                detail="Could not generate recommendations. Please try again."
            )

        perf.set_meta("tracks", len(recommendations))
        logger.info("[perf] %s", perf.to_log_fields())
        return RecommendationResponse(tracks=recommendations)

    except HTTPException:
        raise
    except Exception as e:
        logger.info("[perf] %s", perf.to_log_fields())
        raise HTTPException(status_code=500, detail=f"Error generating recommendations: {str(e)}")


@router.post("/mood-playlist", response_model=RecommendationResponse)
@limiter.limit("10/minute")
async def generate_mood_playlist(
    http_request: Request,
    request: MoodPlaylistRequest,
    current_user: dict = Depends(get_current_user)
):
    """Generate playlist based on mood"""
    valid_moods = ['happy', 'sad', 'energetic', 'chill', 'focus', 'party']
    if request.mood.lower() not in valid_moods:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid mood. Must be one of: {', '.join(valid_moods)}"
        )

    perf = RoutePerf("recommendations_mood_playlist", current_user.get("spotify_id"))
    try:
        with perf.step("auth"):
            access_token = await _require_access_token(current_user)
        with perf.step("mood_generate"):
            recommendations = await recommendation_engine.generate_mood_playlist(
                user_id=current_user["spotify_id"],
                access_token=access_token,
                mood=request.mood.lower(),
                limit=request.limit
            )

        if not recommendations:
            raise HTTPException(
                status_code=404,
                detail=f"Could not generate {request.mood} playlist. Please try again."
            )

        perf.set_meta("tracks", len(recommendations))
        logger.info("[perf] %s", perf.to_log_fields())
        return RecommendationResponse(tracks=recommendations)

    except HTTPException:
        raise
    except Exception as e:
        logger.info("[perf] %s", perf.to_log_fields())
        raise HTTPException(status_code=500, detail=f"Error generating mood playlist: {str(e)}")


@router.get("/profile")
async def get_user_profile(current_user: dict = Depends(get_current_user)):
    """Get user's music profile and preferences"""
    perf = RoutePerf("recommendations_profile", current_user.get("spotify_id"))
    try:
        with perf.step("auth"):
            access_token = await _require_access_token(current_user)
        with perf.step("build_profile"):
            user_profile = await recommendation_engine.build_user_profile(
                user_id=current_user["spotify_id"],
                access_token=access_token
            )

        if "error" in user_profile:
            raise HTTPException(status_code=404, detail=user_profile["error"])

        perf.set_meta("tracks_analyzed", user_profile.get("total_tracks_analyzed"))
        logger.info("[perf] %s", perf.to_log_fields())
        return user_profile

    except HTTPException:
        raise
    except Exception as e:
        logger.info("[perf] %s", perf.to_log_fields())
        raise HTTPException(status_code=500, detail=f"Error getting user profile: {str(e)}")


@router.get("/similar-tracks/{track_id}")
async def get_similar_tracks(
    track_id: str,
    limit: int = Query(10, ge=1, le=50),
    current_user: dict = Depends(get_current_user)
):
    """Get tracks similar to a specific track"""
    try:
        access_token = await _require_access_token(current_user)

        recommendations = await recommendation_engine.generate_recommendations(
            user_id=current_user["spotify_id"],
            access_token=access_token,
            seed_tracks=[track_id],
            limit=limit
        )

        if not recommendations:
            raise HTTPException(
                status_code=404,
                detail=f"Could not find similar tracks for track ID: {track_id}"
            )

        return {"similar_tracks": recommendations}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error finding similar tracks: {str(e)}")


@router.get("/top-tracks")
async def get_user_top_tracks(
    time_range: str = Query("medium_term", regex="^(short_term|medium_term|long_term)$"),
    limit: int = Query(20, ge=1, le=50),
    current_user: dict = Depends(get_current_user)
):
    """Get user's top tracks from Spotify"""
    perf = RoutePerf("recommendations_top_tracks", current_user.get("spotify_id"))
    try:
        with perf.step("auth"):
            access_token = await _require_access_token(current_user)
        with perf.step("spotify_client"):
            sp = await recommendation_engine.get_spotify_client(access_token)
        with perf.step("fetch_top_tracks"):
            top_tracks = await recommendation_engine.get_user_top_tracks(
                sp=sp,
                time_range=time_range,
                limit=limit
            )
        with perf.step("normalize"):
            normalized_tracks = [_normalize_top_track(track) for track in top_tracks]
        perf.add_count("spotify_calls")
        perf.set_meta("tracks", len(normalized_tracks))
        logger.info("[perf] %s", perf.to_log_fields())
        return {"top_tracks": normalized_tracks, "time_range": time_range}

    except HTTPException:
        raise
    except Exception as e:
        logger.info("[perf] %s", perf.to_log_fields())
        raise HTTPException(status_code=500, detail=f"Error getting top tracks: {str(e)}")


@router.get("/discover/outside-bubble")
async def discover_outside_bubble(
    limit: int = Query(6, ge=3, le=10),
    current_user: dict = Depends(get_current_user),
):
    perf = RoutePerf("discover_outside_bubble", current_user.get("spotify_id"))
    try:
        with perf.step("auth"):
            access_token = await _require_access_token(current_user)
        with perf.step("discover_context"):
            context = await _build_discover_context(current_user, access_token, perf=perf)
        with perf.step("outside_module"):
            cards = await _module_outside_bubble(context, limit=limit, perf=perf)

        logger.info(
            "Discover outside-bubble spotify_id=%s top_genres=%s suggested=%d",
            current_user.get("spotify_id"),
            context["top_genres"][:5],
            len(cards),
        )
        perf.set_meta("cards", len(cards))
        logger.info("[perf] %s", perf.to_log_fields())
        return {"outside_your_bubble": [DiscoverGenreCard.model_validate(card).model_dump() for card in cards]}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Outside bubble discover failed for spotify_id=%s", current_user.get("spotify_id"))
        logger.info("[perf] %s", perf.to_log_fields())
        return {"outside_your_bubble": []}


@router.get("/discover/artists-you-should-know")
async def discover_artists_you_should_know(
    limit: int = Query(12, ge=6, le=20),
    current_user: dict = Depends(get_current_user),
):
    perf = RoutePerf("discover_artists_you_should_know", current_user.get("spotify_id"))
    try:
        with perf.step("auth"):
            access_token = await _require_access_token(current_user)
        with perf.step("discover_context"):
            context = await _build_discover_context(current_user, access_token, perf=perf)
        outside_genres = _pick_outside_genres(context["top_genres"])
        with perf.step("artists_module"):
            artists = await _module_artists_you_should_know(
                context,
                outside_genres=outside_genres,
                limit=limit,
                perf=perf,
            )
        logger.info(
            "Discover artists-you-should-know spotify_id=%s candidates=%d returned=%d",
            current_user.get("spotify_id"),
            len(artists),
            min(len(artists), limit),
        )
        perf.set_meta("artists", len(artists))
        logger.info("[perf] %s", perf.to_log_fields())
        return {"artists_you_should_know": [DiscoverArtistCard.model_validate(a).model_dump() for a in artists]}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Artists-you-should-know failed for spotify_id=%s", current_user.get("spotify_id"))
        logger.info("[perf] %s", perf.to_log_fields())
        return {"artists_you_should_know": []}


@router.get("/discover/underground-radar")
async def discover_underground_radar(
    limit: int = Query(12, ge=6, le=25),
    max_popularity: int = Query(30, ge=5, le=40),
    current_user: dict = Depends(get_current_user),
):
    perf = RoutePerf("discover_underground_radar", current_user.get("spotify_id"))
    try:
        with perf.step("auth"):
            access_token = await _require_access_token(current_user)
        with perf.step("discover_context"):
            context = await _build_discover_context(current_user, access_token, perf=perf)
        outside_genres = _pick_outside_genres(context["top_genres"])
        with perf.step("underground_module"):
            gem_candidates = await _module_underground_radar(
                context=context,
                outside_genres=outside_genres,
                limit=limit,
                max_popularity=max_popularity,
                perf=perf,
            )
        logger.info(
            "Discover underground-radar spotify_id=%s gems=%d threshold=%d",
            current_user.get("spotify_id"),
            len(gem_candidates),
            max_popularity,
        )
        perf.set_meta("tracks", len(gem_candidates))
        logger.info("[perf] %s", perf.to_log_fields())
        return {"underground_radar": [DiscoverTrackCard.model_validate(t).model_dump() for t in gem_candidates]}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Underground radar failed for spotify_id=%s", current_user.get("spotify_id"))
        logger.info("[perf] %s", perf.to_log_fields())
        return {"underground_radar": []}


@router.get("/discover/trending-outside")
async def discover_trending_outside(
    limit: int = Query(12, ge=6, le=25),
    current_user: dict = Depends(get_current_user),
):
    perf = RoutePerf("discover_trending_outside", current_user.get("spotify_id"))
    try:
        with perf.step("auth"):
            access_token = await _require_access_token(current_user)
        with perf.step("discover_context"):
            context = await _build_discover_context(current_user, access_token, perf=perf)
        outside_genres = _pick_outside_genres(context["top_genres"])
        with perf.step("trending_module"):
            picks = await _module_trending_outside(context, outside_genres=outside_genres, limit=limit, perf=perf)
        logger.info(
            "Discover trending-outside spotify_id=%s genres=%s returned=%d",
            current_user.get("spotify_id"),
            outside_genres[:5],
            min(len(picks), limit),
        )
        perf.set_meta("tracks", len(picks))
        logger.info("[perf] %s", perf.to_log_fields())
        return {"trending_outside_your_taste": [DiscoverTrackCard.model_validate(t).model_dump() for t in picks]}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Trending-outside failed for spotify_id=%s", current_user.get("spotify_id"))
        logger.info("[perf] %s", perf.to_log_fields())
        return {"trending_outside_your_taste": []}


@router.get("/discover/genre/{genre_name}")
async def discover_by_genre(
    genre_name: str,
    limit: int = Query(12, ge=6, le=30),
    current_user: dict = Depends(get_current_user),
):
    perf = RoutePerf("discover_by_genre", current_user.get("spotify_id"))
    try:
        with perf.step("auth"):
            access_token = await _require_access_token(current_user)
        with perf.step("spotify_client"):
            sp = await recommendation_engine.get_spotify_client(access_token)
        sem = asyncio.Semaphore(6)
        candidate_tracks: List[Dict[str, Any]] = []
        search_queries = [
            f"{genre_name} playlist",
            f"{genre_name} mix",
            f"{genre_name} essentials",
            f"{genre_name} rising",
        ]
        for query in search_queries:
            tracks = await _safe_spotify_search(
                sp,
                query=query,
                search_type="track",
                limit=20,
                call_name=f"discover_genre_search[{query}]",
                perf=perf,
                sem=sem,
            )
            for track in tracks:
                normalized = _normalize_spotify_track(track, reason=f"Exploring {genre_name}")
                if not normalized:
                    continue
                normalized["_source"] = f"search:{query}"
                normalized["_scene"] = query
                normalized["_score"] = float(normalized.get("popularity", 0)) / 25.0 + random.uniform(0, 0.4)
                candidate_tracks.append(normalized)

        playlist_results = await _safe_spotify_search(
            sp,
            query=f"{genre_name} playlist",
            search_type="playlist",
            limit=5,
            call_name=f"discover_genre_playlist_search[{genre_name}]",
            perf=perf,
            sem=sem,
        )
        for playlist in playlist_results:
            pid = playlist.get("id")
            pname = playlist.get("name") if isinstance(playlist.get("name"), str) else genre_name
            if not isinstance(pid, str):
                continue
            playlist_tracks = await _safe_playlist_tracks(sp, pid, limit=25, perf=perf, sem=sem)
            for track in playlist_tracks:
                normalized = _normalize_spotify_track(track, reason=f"Exploring {genre_name}")
                if not normalized:
                    continue
                normalized["_source"] = f"playlist:{pid}"
                normalized["_scene"] = pname
                normalized["_score"] = float(normalized.get("popularity", 0)) / 30.0 + 0.5 + random.uniform(0, 0.3)
                candidate_tracks.append(normalized)

        with perf.step("rerank_diversify"):
            normalized_tracks = _diversify_track_candidates(
            candidate_tracks,
            limit=limit,
            max_per_artist=1,
            max_per_album=1,
            max_per_source=max(2, limit // 3),
            enforce_pop_band_mix=True,
            )
        logger.info(
            "Discover genre-feed spotify_id=%s genre=%s returned=%d",
            current_user.get("spotify_id"),
            genre_name,
            len(normalized_tracks),
        )
        perf.set_meta("candidates_raw", len(candidate_tracks))
        perf.set_meta("candidates_final", len(normalized_tracks))
        logger.info("[perf] %s", perf.to_log_fields())

        return {"genre": genre_name, "tracks": [DiscoverTrackCard.model_validate(t).model_dump() for t in normalized_tracks]}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Genre discover failed for spotify_id=%s genre=%s", current_user.get("spotify_id"), genre_name)
        logger.info("[perf] %s", perf.to_log_fields())
        return {"genre": genre_name, "tracks": []}


@router.get("/discover/artist/{artist_id}")
async def discover_artist_detail(
    artist_id: str,
    current_user: dict = Depends(get_current_user),
):
    perf = RoutePerf("discover_artist_detail", current_user.get("spotify_id"))
    try:
        with perf.step("auth"):
            access_token = await _require_access_token(current_user)
        with perf.step("discover_context"):
            context = await _build_discover_context(current_user, access_token, perf=perf)
        sp = context["sp"]
        sem = asyncio.Semaphore(6)
        artist_raw = await recommendation_engine._spotify_call_with_timeout(
            sp.artist,
            artist_id,
            timeout_seconds=8.0,
            call_name=f"discover_artist[{artist_id}]",
        )
        perf.add_count("spotify_calls")
        artist = _normalize_artist(artist_raw, reason="Artist profile")
        if not artist:
            raise HTTPException(status_code=404, detail="Artist not found")

        top_tracks_raw = await recommendation_engine._get_artist_top_tracks_cached(sp, artist_id)
        top_track_candidates: List[Dict[str, Any]] = []
        for track in top_tracks_raw:
            normalized = _normalize_spotify_track(track, reason=f"Top track by {artist['name']}")
            if not normalized:
                continue
            normalized["_source"] = "artist-top-tracks"
            normalized["_scene"] = artist["name"]
            normalized["_score"] = float(normalized.get("popularity", 0)) / 20.0 + random.uniform(0, 0.2)
            top_track_candidates.append(normalized)
        top_tracks = _diversify_track_candidates(
            top_track_candidates,
            limit=8,
            max_per_artist=8,
            max_per_album=1,
            max_per_source=8,
            enforce_pop_band_mix=False,
        )

        related_candidates: List[Tuple[float, Dict[str, Any]]] = []
        seen_related_ids: Set[str] = set()
        for genre in artist.get("genres", [])[:3] or context["top_genres"][:3]:
            scene = GENRE_SCENE_BUCKETS.get(str(genre).lower(), str(genre).lower())
            artists = await _safe_spotify_search(
                sp,
                query=f'genre:"{genre}"',
                search_type="artist",
                limit=6,
                call_name=f"artist_detail_adjacent_search[{genre}]",
                perf=perf,
                sem=sem,
            )
            for a in artists:
                normalized = _normalize_artist(a, reason="Similar artist")
                if not normalized or normalized["id"] == artist_id:
                    continue
                if normalized["id"] in seen_related_ids:
                    continue
                seen_related_ids.add(normalized["id"])
                normalized["_scene"] = scene
                normalized["_source"] = f"artist-search:{genre}"
                overlap = _genre_overlap_score(normalized.get("genres", []), set(g.lower() for g in artist.get("genres", [])))
                score = overlap * 1.4 + float(normalized.get("popularity", 0)) / 50.0 + random.uniform(0, 0.3)
                related_candidates.append((score, normalized))

        related = _diversify_artist_candidates(related_candidates, limit=8, max_per_scene=2)
        logger.info(
            "Discover artist-detail spotify_id=%s artist_id=%s tracks=%d related=%d",
            current_user.get("spotify_id"),
            artist_id,
            len(top_tracks),
            len(related),
        )
        perf.set_meta("tracks", len(top_tracks))
        perf.set_meta("similar_artists", len(related))
        logger.info("[perf] %s", perf.to_log_fields())

        payload = DiscoverArtistDetailResponse(
            artist=DiscoverArtistCard.model_validate(artist),
            top_tracks=[DiscoverTrackCard.model_validate(t) for t in top_tracks],
            similar_artists=[DiscoverArtistCard.model_validate(a) for a in related],
        )
        return payload.model_dump()
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Artist detail discover failed for artist_id=%s", artist_id)
        logger.info("[perf] %s", perf.to_log_fields())
        return DiscoverArtistDetailResponse().model_dump()


@router.get("/discover/explorer", response_model=DiscoverExplorerResponse)
async def discover_explorer(
    current_user: dict = Depends(get_current_user),
):
    perf = RoutePerf("discover_explorer", current_user.get("spotify_id"))
    try:
        with perf.step("auth"):
            access_token = await _require_access_token(current_user)
        with perf.step("discover_context"):
            context = await _build_discover_context(current_user, access_token, perf=perf)
        sem = asyncio.Semaphore(6)
        outside: List[Dict[str, Any]] = []
        artists: List[Dict[str, Any]] = []
        underground: List[Dict[str, Any]] = []
        trending: List[Dict[str, Any]] = []

        try:
            with perf.step("outside_module"):
                outside = await _module_outside_bubble(context, limit=6, perf=perf, sem=sem)
        except Exception as exc:
            logger.warning("Discover module failed: outside_your_bubble err=%s", exc)

        outside_genres = [card.get("genre", "") for card in outside if isinstance(card, dict)]

        async def _safe_call(coro, module_name: str):
            try:
                return await coro
            except Exception as exc:
                logger.warning("Discover module failed: %s err=%s", module_name, exc)
                return []

        with perf.step("parallel_modules"):
            artists, underground, trending = await asyncio.gather(
                _safe_call(
                    _module_artists_you_should_know(context, outside_genres=outside_genres, limit=10, perf=perf, sem=sem),
                    "artists_you_should_know",
                ),
                _safe_call(
                    _module_underground_radar(
                        context=context,
                        outside_genres=outside_genres,
                        limit=10,
                        max_popularity=30,
                        perf=perf,
                        sem=sem,
                    ),
                    "underground_radar",
                ),
                _safe_call(
                    _module_trending_outside(context, outside_genres=outside_genres, limit=10, perf=perf, sem=sem),
                    "trending_outside_your_taste",
                ),
            )

        response = DiscoverExplorerResponse(
            outside_your_bubble=[DiscoverGenreCard.model_validate(card) for card in outside],
            artists_you_should_know=[DiscoverArtistCard.model_validate(artist) for artist in artists],
            underground_radar=[DiscoverTrackCard.model_validate(track) for track in underground],
            trending_outside_your_taste=[DiscoverTrackCard.model_validate(track) for track in trending],
        )
        logger.info(
            "Discover explorer spotify_id=%s modules={outside:%d artists:%d underground:%d trending:%d}",
            current_user.get("spotify_id"),
            len(response.outside_your_bubble),
            len(response.artists_you_should_know),
            len(response.underground_radar),
            len(response.trending_outside_your_taste),
        )
        perf.set_meta("outside", len(response.outside_your_bubble))
        perf.set_meta("artists", len(response.artists_you_should_know))
        perf.set_meta("underground", len(response.underground_radar))
        perf.set_meta("trending", len(response.trending_outside_your_taste))
        logger.info("[perf] %s", perf.to_log_fields())
        return response.model_dump()
    except Exception as exc:
        logger.exception("Discover explorer failed for spotify_id=%s", current_user.get("spotify_id"))
        logger.info("[perf] %s", perf.to_log_fields())
        return DiscoverExplorerResponse().model_dump()


@router.get("/discover/{discover_type}")
async def discover_music(
    discover_type: str,
    limit: int = Query(12, ge=1, le=50),
    current_user: dict = Depends(get_current_user)
):
    """Discover music by type: similar, new-genres, trending, deep-cuts"""
    valid_types = {'similar', 'new-genres', 'trending', 'deep-cuts'}
    if discover_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid discover type. Must be one of: {', '.join(valid_types)}"
        )

    try:
        access_token = await _require_access_token(current_user)

        discover_mapping = {
            'new-genres': 'focus',
            'trending': 'party',
            'deep-cuts': 'chill',
        }

        if discover_type == 'similar':
            recommendations = await recommendation_engine.generate_recommendations(
                user_id=current_user["spotify_id"],
                access_token=access_token,
                limit=limit
            )
        else:
            mood = discover_mapping[discover_type]
            recommendations = await recommendation_engine.generate_mood_playlist(
                user_id=current_user["spotify_id"],
                access_token=access_token,
                mood=mood,
                limit=limit
            )

        return {"tracks": recommendations, "discover_type": discover_type}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error discovering music: {str(e)}")


@router.get("/dna")
async def get_music_dna(current_user: dict = Depends(get_current_user)):
    """
    Return the current user's Music DNA: six normalized dimensions (0–1) derived
    from their top artists' genre tags, track popularity, and release era.

    Does NOT use the restricted /v1/audio-features endpoint.
    Result is cached per Spotify user ID for 20 minutes.
    """
    spotify_id = current_user.get("spotify_id", "unknown")
    cache_key = f"dna:{spotify_id}"
    request_started = time.perf_counter()
    logger.info("Music DNA request started for spotify_id=%s cache_key=%s", spotify_id, cache_key)
    try:
        access_token = await _require_access_token(current_user)
        dna = await asyncio.wait_for(
            recommendation_engine.build_music_dna(
                spotify_id=spotify_id,
                access_token=access_token,
            ),
            timeout=28.0,
        )
        if dna.get("status") in {"degraded", "fallback"}:
            logger.warning(
                "Music DNA fallback response for spotify_id=%s status=%s reasons=%s",
                spotify_id,
                dna.get("status"),
                dna.get("metadata", {}).get("fallback_reasons", []),
            )
        logger.info(
            "Music DNA payload spotify_id=%s status=%s dimensions=%s",
            spotify_id,
            dna.get("status"),
            dna.get("dimensions"),
        )
        return dna
    except asyncio.TimeoutError:
        logger.warning("Music DNA request timed out for spotify_id=%s", spotify_id)
        return {
            "spotify_id": spotify_id,
            "status": "timeout",
            "dimensions": {
                "energy": 0.5,
                "valence": 0.5,
                "danceability": 0.5,
                "acousticness": 0.5,
                "speechiness": 0.5,
                "diversity": 0.0,
            },
            "metadata": {
                "total_artists_analyzed": 0,
                "total_tracks_analyzed": 0,
                "unique_genres": [],
                "avg_popularity": 0.5,
                "avg_era": 0.5,
                "source": "timeout-fallback",
                "fallback_reasons": ["endpoint_timeout"],
            },
            "source": "timeout-fallback",
            "error": "Music DNA timed out",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Music DNA request failed for spotify_id=%s", spotify_id)
        return {
            "spotify_id": spotify_id,
            "status": "error",
            "dimensions": {
                "energy": 0.5,
                "valence": 0.5,
                "danceability": 0.5,
                "acousticness": 0.5,
                "speechiness": 0.5,
                "diversity": 0.0,
            },
            "metadata": {
                "total_artists_analyzed": 0,
                "total_tracks_analyzed": 0,
                "unique_genres": [],
                "avg_popularity": 0.5,
                "avg_era": 0.5,
                "source": "error-fallback",
                "fallback_reasons": [str(type(e).__name__)],
            },
            "source": "error-fallback",
            "error": "Error computing Music DNA",
        }
    finally:
        elapsed_ms = round((time.perf_counter() - request_started) * 1000, 1)
        logger.info("Music DNA request completed for spotify_id=%s duration_ms=%s", spotify_id, elapsed_ms)


@router.get("/genres")
async def get_available_genres(current_user: dict = Depends(get_current_user)):
    """Get available genre seeds from Spotify"""
    genres = [
        'acoustic', 'afrobeat', 'alt-rock', 'alternative', 'ambient',
        'blues', 'bossanova', 'brazil', 'breakbeat', 'british',
        'chill', 'classical', 'club', 'country', 'dance',
        'electronic', 'folk', 'funk', 'garage', 'gospel',
        'hip-hop', 'house', 'indie', 'jazz', 'latin',
        'pop', 'punk', 'reggae', 'rock', 'soul'
    ]
    return {"genres": genres}
