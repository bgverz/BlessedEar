from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any, Set, Tuple
from pydantic import BaseModel
import json
import spotipy
import logging
import random
import re

from app.api.auth import get_current_user, get_valid_access_token
from app.core.database import get_db, get_cache, set_cache
from app.core.perf import RoutePerf
from app.models.playlist import Playlist
from app.models.user import User
from app.ml.recommender import RecommendationEngine

router = APIRouter()
recommendation_engine = RecommendationEngine()
logger = logging.getLogger(__name__)

class SavePlaylistRequest(BaseModel):
    name: str
    description: Optional[str] = None
    tracks: List[dict]  # The recommendation tracks
    mood: Optional[str] = None
    generation_type: str = "recommendation"

class CreateSpotifyPlaylistRequest(BaseModel):
    playlist_id: int
    spotify_name: Optional[str] = None
    spotify_description: Optional[str] = None

class PlaylistResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    track_count: int
    mood: Optional[str]
    generation_type: str
    is_exported: bool
    spotify_playlist_id: Optional[str]
    created_at: str


class GeneratePlaylistRequest(BaseModel):
    prompt: str
    limit: int = 30


class ExportGeneratedPlaylistRequest(BaseModel):
    prompt: str
    tracks: List[dict]
    spotify_name: Optional[str] = None


PROMPT_GENRE_KEYWORDS: Dict[str, List[str]] = {
    "reggaeton": ["reggaeton", "urbano", "perreo"],
    "latin pop": ["latin pop", "spanish pop", "latin hits"],
    "corridos": ["corridos", "corridos tumbados"],
    "trap": ["trap", "drill"],
    "hip hop": ["hip hop", "rap", "boom bap"],
    "indie": ["indie", "indie rock", "indie pop"],
    "alternative": ["alternative", "alt"],
    "electronic": ["electronic", "edm", "house", "techno"],
    "r&b": ["r&b", "neo soul", "soul"],
    "afrobeats": ["afrobeat", "afrobeats", "afropop"],
    "pop": ["pop"],
}

PROMPT_MOOD_KEYWORDS: Dict[str, List[str]] = {
    "chill": ["chill", "relax", "calm", "lofi", "easy"],
    "sad": ["sad", "cry", "heartbreak", "melancholy"],
    "workout": ["workout", "gym", "run", "lifting", "hype"],
    "party": ["party", "club", "dance", "festival"],
    "focus": ["focus", "study", "deep work", "coding"],
    "late_night": ["late night", "night drive", "midnight", "nocturnal"],
}

PROMPT_ACTIVITY_KEYWORDS: Dict[str, List[str]] = {
    "drive": ["drive", "road trip", "highway", "cruise"],
    "study": ["study", "focus", "work", "reading"],
    "gym": ["gym", "workout", "lifting", "training"],
    "party": ["party", "pregame", "club"],
}

PROMPT_LANGUAGE_KEYWORDS = {
    "spanish": ["spanish", "espanol", "español", "latin", "latino", "reggaeton", "urbano", "corridos"],
}

PROMPT_REGION_KEYWORDS = {
    "latin": ["latin", "latino", "reggaeton", "urbano", "corridos"],
}

CONCRETE_PROMPT_MARKERS = [
    "hits", "mix", "playlist", "reggaeton", "trap", "indie", "pop", "afrobeat",
    "latin", "spanish", "workout", "party", "2000s", "2010s", "90s",
]

ABSTRACT_PROMPT_MARKERS = [
    "vibes", "songs for", "music for", "feels", "energy", "floating", "sunset",
    "rainy", "2am", "alone", "late night", "night drive", "nocturnal",
]

VIBE_EXPANSION_TERMS: Dict[str, List[str]] = {
    "late_night": ["late night r&b", "night drive", "moody r&b", "atmospheric electronic"],
    "sad": ["sad indie", "melancholic indie", "dream pop", "soft alternative"],
    "chill": ["chill mix", "lofi chill", "ambient pop", "chill r&b"],
    "focus": ["focus music", "instrumental focus", "deep focus", "calm electronic"],
    "workout": ["workout trap", "gym rap", "high energy hip hop", "party cardio"],
    "party": ["party hits", "dance party", "club mix", "hype rap"],
}


def _normalize_prompt_text(prompt: str) -> str:
    return re.sub(r"\s+", " ", (prompt or "").strip().lower())


def _determine_prompt_type(
    text: str,
    genres: Set[str],
    moods: Set[str],
    activities: Set[str],
    language: Optional[str],
    region: Optional[str],
    era: Optional[str],
) -> str:
    has_concrete_marker = any(marker in text for marker in CONCRETE_PROMPT_MARKERS)
    has_abstract_marker = any(marker in text for marker in ABSTRACT_PROMPT_MARKERS)
    explicit_structured = bool(genres or activities or language or region or era)
    pure_vibe = bool(moods) and not explicit_structured

    if (explicit_structured and has_abstract_marker) or (has_concrete_marker and has_abstract_marker):
        return "hybrid"
    if explicit_structured or has_concrete_marker:
        return "concrete"
    if pure_vibe or has_abstract_marker:
        return "abstract"
    return "hybrid"


def _build_search_terms(text: str, genres: Set[str], moods: Set[str], activities: Set[str]) -> List[str]:
    terms: List[str] = [text]
    for genre in sorted(genres):
        terms.append(genre)
        terms.append(f"{genre} mix")
    for mood in sorted(moods):
        if mood in VIBE_EXPANSION_TERMS:
            terms.extend(VIBE_EXPANSION_TERMS[mood][:2])
        else:
            terms.append(mood)
    for activity in sorted(activities):
        terms.append(f"{activity} playlist")

    deduped: List[str] = []
    seen: Set[str] = set()
    for term in terms:
        cleaned = _normalize_prompt_text(term)
        if cleaned and cleaned not in seen:
            deduped.append(cleaned)
            seen.add(cleaned)
    return deduped[:10]


def _parse_prompt_profile(prompt: str) -> Dict[str, Any]:
    text = _normalize_prompt_text(prompt)
    genres: Set[str] = set()
    moods: Set[str] = set()
    activities: Set[str] = set()
    language: Optional[str] = None
    region: Optional[str] = None
    popularity_bias = "neutral"
    energy_bias = "medium"
    era: Optional[str] = None

    for genre, keywords in PROMPT_GENRE_KEYWORDS.items():
        if any(k in text for k in keywords):
            genres.add(genre)

    for mood, keywords in PROMPT_MOOD_KEYWORDS.items():
        if any(k in text for k in keywords):
            moods.add(mood)

    for activity, keywords in PROMPT_ACTIVITY_KEYWORDS.items():
        if any(k in text for k in keywords):
            activities.add(activity)

    for lang, keywords in PROMPT_LANGUAGE_KEYWORDS.items():
        if any(k in text for k in keywords):
            language = lang
            break

    for rgn, keywords in PROMPT_REGION_KEYWORDS.items():
        if any(k in text for k in keywords):
            region = rgn
            break

    if any(k in text for k in ["hits", "popular", "mainstream", "top"]):
        popularity_bias = "popular"
    elif any(k in text for k in ["underground", "deep cut", "deep cuts", "obscure"]):
        popularity_bias = "deep_cuts"

    if any(k in text for k in ["gym", "workout", "party", "hype", "energetic", "trap"]):
        energy_bias = "high"
    elif any(k in text for k in ["chill", "sad", "focus", "late night", "study"]):
        energy_bias = "low"

    if "2000" in text or "00s" in text:
        era = "2000s"
    elif "2010" in text or "10s" in text:
        era = "2010s"
    elif "90s" in text or "199" in text:
        era = "90s"

    if not moods:
        moods.add("chill")

    prompt_type = _determine_prompt_type(
        text=text,
        genres=genres,
        moods=moods,
        activities=activities,
        language=language,
        region=region,
        era=era,
    )
    search_terms = _build_search_terms(text=text, genres=genres, moods=moods, activities=activities)

    return {
        "raw_prompt": prompt,
        "prompt_type": prompt_type,
        "genres": sorted(genres),
        "moods": sorted(moods),
        "activities": sorted(activities),
        "language": language,
        "region": region,
        "popularity_bias": popularity_bias,
        "energy_bias": energy_bias,
        "era": era,
        "search_terms": search_terms,
    }


def _prompt_to_primary_mood(profile: Dict[str, Any]) -> str:
    moods = profile.get("moods") or []
    if "workout" in moods:
        return "energetic"
    if "late_night" in moods:
        return "chill"
    if "party" in moods:
        return "party"
    if "focus" in moods:
        return "focus"
    if "sad" in moods:
        return "sad"
    if "chill" in moods:
        return "chill"
    return "chill"


def _parse_track_id(value: Any) -> Optional[str]:
    if not value:
        return None
    if isinstance(value, str):
        if value.startswith("spotify:track:"):
            return value.split(":")[-1] or None
        return value
    return None


def _extract_artists(track: Dict[str, Any]) -> List[str]:
    artists = track.get("artists")
    if isinstance(artists, list):
        names: List[str] = []
        for artist in artists:
            if isinstance(artist, dict):
                name = artist.get("name")
                if isinstance(name, str) and name.strip():
                    names.append(name.strip())
            elif isinstance(artist, str) and artist.strip():
                names.append(artist.strip())
        if names:
            return names

    artist = track.get("artist")
    if isinstance(artist, str) and artist.strip():
        return [artist.strip()]
    return []


def _extract_album_images(track: Dict[str, Any]) -> List[Dict[str, Any]]:
    direct = track.get("album_images")
    if isinstance(direct, list):
        return [img for img in direct if isinstance(img, dict) and img.get("url")]

    album = track.get("album")
    if isinstance(album, dict):
        images = album.get("images")
        if isinstance(images, list):
            return [img for img in images if isinstance(img, dict) and img.get("url")]

    return []


def _extract_album_name(track: Dict[str, Any]) -> str:
    album = track.get("album")
    if isinstance(album, dict):
        name = album.get("name")
        if isinstance(name, str):
            return name
    if isinstance(album, str):
        return album
    album_name = track.get("album_name")
    if isinstance(album_name, str):
        return album_name
    return ""


def _extract_spotify_url(track: Dict[str, Any], track_id: str) -> str:
    external_urls = track.get("external_urls")
    if isinstance(external_urls, dict):
        spotify_url = external_urls.get("spotify")
        if isinstance(spotify_url, str) and spotify_url:
            return spotify_url

    spotify_url = track.get("spotify_url")
    if isinstance(spotify_url, str) and spotify_url:
        return spotify_url

    return f"https://open.spotify.com/track/{track_id}"


def _normalize_generated_track(track: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(track, dict):
        logger.warning("Skipping malformed generated track: expected dict, got %s", type(track).__name__)
        return None

    track_id = (
        _parse_track_id(track.get("track_id"))
        or _parse_track_id(track.get("id"))
        or _parse_track_id(track.get("uri"))
    )
    if not track_id:
        logger.warning("Skipping malformed generated track without ID: keys=%s", list(track.keys()))
        return None

    artists = _extract_artists(track)
    artist_name = ", ".join(artists) if artists else "Unknown Artist"
    album_name = _extract_album_name(track)
    album_images = _extract_album_images(track)

    album_cover_url = recommendation_engine._select_album_image_url(album_images)
    if not album_cover_url:
        direct_cover = track.get("album_cover_url") or track.get("album_image_url")
        if isinstance(direct_cover, str):
            album_cover_url = direct_cover

    spotify_url = _extract_spotify_url(track, track_id)
    name = track.get("name")
    if not isinstance(name, str) or not name.strip():
        name = "Unknown Track"

    return {
        "track_id": track_id,
        "name": name,
        "artist": artist_name,
        "artists": artists,
        "album": album_name,
        "album_cover_url": album_cover_url,
        "album_images": album_images,
        "spotify_url": spotify_url,
    }


def _safe_get_playlist_id(playlist: Any) -> Optional[str]:
    if not isinstance(playlist, dict):
        return None
    playlist_id = playlist.get("id")
    return playlist_id if isinstance(playlist_id, str) and playlist_id.strip() else None


def _safe_iter_playlist_items(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _safe_extract_track(item: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(item, dict):
        return None
    track = item.get("track")
    if not isinstance(track, dict):
        return None
    if not _parse_track_id(track.get("id") or track.get("uri") or track.get("track_id")):
        return None
    return track


def _safe_extract_artist_names(track: Dict[str, Any]) -> List[str]:
    return _extract_artists(track)


def _safe_extract_album_cover(track: Dict[str, Any]) -> Optional[str]:
    album_images = _extract_album_images(track)
    image_url = recommendation_engine._select_album_image_url(album_images)
    if image_url:
        return image_url
    fallback = track.get("album_cover_url") or track.get("album_image_url")
    return fallback if isinstance(fallback, str) and fallback else None


def _normalize_candidate_track(
    track: Any,
    source: str,
    genres: Optional[List[str]] = None,
    seed_artist_id: Optional[str] = None,
    seed_query: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    normalized = _normalize_generated_track(track)
    if not normalized:
        return None

    popularity = 50
    if isinstance(track, dict):
        raw_popularity = track.get("popularity")
        if isinstance(raw_popularity, int):
            popularity = raw_popularity

    valid_genres = [g for g in (genres or []) if isinstance(g, str)]
    normalized["album_cover_url"] = _safe_extract_album_cover(normalized)
    normalized["artists"] = _safe_extract_artist_names(normalized)
    normalized["genres"] = valid_genres
    normalized["popularity"] = popularity
    normalized["source"] = source
    normalized["seed_artist_id"] = seed_artist_id if isinstance(seed_artist_id, str) else None
    normalized["seed_query"] = seed_query if isinstance(seed_query, str) else None
    return normalized


def _serialize_output_track(track: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "track_id": track.get("track_id"),
        "name": track.get("name"),
        "artist": track.get("artist"),
        "artists": track.get("artists") if isinstance(track.get("artists"), list) else [],
        "album": track.get("album"),
        "album_cover_url": track.get("album_cover_url"),
        "album_images": track.get("album_images") if isinstance(track.get("album_images"), list) else [],
        "spotify_url": track.get("spotify_url"),
    }


def _track_genre_text(track: Dict[str, Any]) -> str:
    genres = track.get("genres") or track.get("seed_genres") or []
    return " ".join(g.lower() for g in genres if isinstance(g, str))


def _looks_latin_or_spanish(track: Dict[str, Any]) -> bool:
    text = " ".join([
        (track.get("name") or ""),
        (track.get("artist") or ""),
        _track_genre_text(track),
    ]).lower()
    latin_keywords = [
        "latin", "latino", "reggaeton", "urbano", "corridos", "bachata",
        "salsa", "cumbia", "mexicano", "español", "spanish",
    ]
    return any(k in text for k in latin_keywords)


def _prompt_score_track(track: Dict[str, Any], profile: Dict[str, Any]) -> float:
    score = 0.0
    name_text = (track.get("name") or "").lower()
    artist_text = (track.get("artist") or "").lower()
    genre_text = _track_genre_text(track)
    source_query = (track.get("seed_query") or "").lower()
    joined = f"{name_text} {artist_text} {genre_text} {source_query}"

    for genre in profile.get("genres", []):
        if genre in joined:
            score += 3.0

    mood_aliases = {
        "late_night": ["late night", "night", "midnight", "nocturnal"],
        "workout": ["workout", "gym", "hype", "training"],
        "chill": ["chill", "calm", "ambient", "lofi"],
        "sad": ["sad", "melancholy", "heartbreak", "moody"],
        "party": ["party", "club", "dance", "festival"],
        "focus": ["focus", "study", "instrumental", "deep"],
    }
    for mood in profile.get("moods", []):
        aliases = mood_aliases.get(mood, [mood.replace("_", " ")])
        if any(alias in joined for alias in aliases):
            score += 1.0

    for activity in profile.get("activities", []):
        if any(k in joined for k in [activity, f"{activity} ", f" {activity}"]):
            score += 0.7

    if profile.get("language") == "spanish" or profile.get("region") == "latin":
        if _looks_latin_or_spanish(track):
            score += 3.5
        else:
            score -= 2.0

    popularity = track.get("popularity")
    if isinstance(popularity, int):
        if profile.get("popularity_bias") == "popular":
            score += popularity / 40.0
        elif profile.get("popularity_bias") == "deep_cuts":
            score += max(0.0, (45 - popularity) / 20.0)

    if profile.get("energy_bias") == "high":
        if any(k in joined for k in ["trap", "drill", "club", "dance", "party", "hype"]):
            score += 1.3
    elif profile.get("energy_bias") == "low":
        if any(k in joined for k in ["chill", "ambient", "sad", "night", "dream"]):
            score += 1.3

    return score


def _taste_score_track(track: Dict[str, Any], user_genres: Set[str], favorite_artist_ids: Set[str]) -> float:
    score = 0.0
    seed_genres = {g.lower() for g in (track.get("genres") or track.get("seed_genres") or []) if isinstance(g, str)}
    overlap = len(seed_genres & user_genres)
    score += overlap * 0.7

    seed_artist_id = track.get("seed_artist_id")
    if isinstance(seed_artist_id, str) and seed_artist_id in favorite_artist_ids:
        score += 2.0
    return score


def _profile_lane_key(profile: Optional[Dict[str, Any]]) -> Optional[str]:
    if not profile:
        return None
    lane = {
        "type": profile.get("prompt_type"),
        "genres": profile.get("genres") or [],
        "moods": profile.get("moods") or [],
        "language": profile.get("language"),
        "region": profile.get("region"),
        "era": profile.get("era"),
    }
    encoded = json.dumps(lane, sort_keys=True)
    return re.sub(r"[^a-z0-9]+", "-", encoded.lower()).strip("-")[:120]


async def _load_generator_exclusions(
    spotify_id: str,
    prompt: str,
    profile: Optional[Dict[str, Any]] = None,
) -> Set[str]:
    prompt_key = f"playlistgen:prompt:{spotify_id}:{_normalize_prompt_text(prompt)}"
    recent_key = f"playlistgen:recent:{spotify_id}"
    lane_key = _profile_lane_key(profile)
    excluded: Set[str] = set()

    keys = [prompt_key, recent_key]
    if lane_key:
        keys.append(f"playlistgen:lane:{spotify_id}:{lane_key}")

    for key in keys:
        cached = await get_cache(key)
        if cached:
            try:
                excluded.update(json.loads(cached))
            except Exception:
                pass
    return excluded


async def _save_generator_history(
    spotify_id: str,
    prompt: str,
    track_ids: List[str],
    profile: Optional[Dict[str, Any]] = None,
) -> None:
    prompt_key = f"playlistgen:prompt:{spotify_id}:{_normalize_prompt_text(prompt)}"
    recent_key = f"playlistgen:recent:{spotify_id}"
    lane_key = _profile_lane_key(profile)

    # Keep prompt-specific history tight, recent history broader.
    try:
        prompt_history = await get_cache(prompt_key)
        prompt_ids = json.loads(prompt_history) if prompt_history else []
        combined_prompt = (track_ids + [tid for tid in prompt_ids if tid not in set(track_ids)])[:120]
        await set_cache(prompt_key, json.dumps(combined_prompt), expire=172800)
    except Exception:
        pass

    try:
        recent_history = await get_cache(recent_key)
        recent_ids = json.loads(recent_history) if recent_history else []
        combined_recent = (track_ids + [tid for tid in recent_ids if tid not in set(track_ids)])[:240]
        await set_cache(recent_key, json.dumps(combined_recent), expire=604800)
    except Exception:
        pass

    if lane_key:
        try:
            lane_history = await get_cache(f"playlistgen:lane:{spotify_id}:{lane_key}")
            lane_ids = json.loads(lane_history) if lane_history else []
            combined_lane = (track_ids + [tid for tid in lane_ids if tid not in set(track_ids)])[:180]
            await set_cache(
                f"playlistgen:lane:{spotify_id}:{lane_key}",
                json.dumps(combined_lane),
                expire=259200,
            )
        except Exception:
            pass


async def _search_prompt_tracks(sp: spotipy.Spotify, prompt: str, limit: int = 25) -> List[Dict[str, Any]]:
    cache_key = f"playlist_search:track:{_normalize_prompt_text(prompt)}:{limit}"
    cached = await get_cache(cache_key)
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass
    try:
        result = await recommendation_engine._spotify_call_with_timeout(
            sp.search,
            q=prompt,
            type="track",
            market="US",
            limit=limit,
            timeout_seconds=8.0,
            call_name="playlist_prompt_track_search",
        )
        if not isinstance(result, dict):
            return []
        tracks = result.get("tracks")
        if not isinstance(tracks, dict):
            return []
        items = tracks.get("items")
        if not isinstance(items, list):
            return []
        parsed = [item for item in items if isinstance(item, dict)]
        try:
            await set_cache(cache_key, json.dumps(parsed), expire=3600)
        except Exception:
            pass
        return parsed
    except Exception as exc:
        logger.warning("Prompt track search failed for '%s': %s", prompt, exc)
        return []


async def _search_prompt_artists(sp: spotipy.Spotify, prompt: str, limit: int = 20) -> List[Dict[str, Any]]:
    cache_key = f"playlist_search:artist:{_normalize_prompt_text(prompt)}:{limit}"
    cached = await get_cache(cache_key)
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass
    try:
        result = await recommendation_engine._spotify_call_with_timeout(
            sp.search,
            q=prompt,
            type="artist",
            market="US",
            limit=limit,
            timeout_seconds=8.0,
            call_name="playlist_prompt_artist_search",
        )
        if not isinstance(result, dict):
            return []
        artists = result.get("artists")
        if not isinstance(artists, dict):
            return []
        items = artists.get("items")
        if not isinstance(items, list):
            return []
        parsed = [item for item in items if isinstance(item, dict)]
        try:
            await set_cache(cache_key, json.dumps(parsed), expire=3600)
        except Exception:
            pass
        return parsed
    except Exception as exc:
        logger.warning("Prompt artist search failed for '%s': %s", prompt, exc)
        return []


async def _search_public_playlists(sp: spotipy.Spotify, query: str, limit: int = 6) -> List[Dict[str, Any]]:
    cache_key = f"playlist_search:playlist:{_normalize_prompt_text(query)}:{limit}"
    cached = await get_cache(cache_key)
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass
    try:
        result = await recommendation_engine._spotify_call_with_timeout(
            sp.search,
            q=query,
            type="playlist",
            market="US",
            limit=limit,
            timeout_seconds=8.0,
            call_name="playlist_prompt_playlist_search",
        )
        if not isinstance(result, dict):
            return []
        playlists = result.get("playlists")
        if not isinstance(playlists, dict):
            return []
        items = playlists.get("items")
        if not isinstance(items, list):
            return []
        parsed = [item for item in items if isinstance(item, dict)]
        try:
            await set_cache(cache_key, json.dumps(parsed), expire=3600)
        except Exception:
            pass
        return parsed
    except Exception as exc:
        logger.warning("Playlist search failed for '%s': %s", query, exc)
        return []


async def _get_playlist_tracks(sp: spotipy.Spotify, playlist_id: str, limit: int = 30) -> List[Dict[str, Any]]:
    cache_key = f"playlist_items:{playlist_id}:{limit}"
    cached = await get_cache(cache_key)
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass
    try:
        result = await recommendation_engine._spotify_call_with_timeout(
            sp.playlist_items,
            playlist_id=playlist_id,
            fields="items(track(id,name,artists,album,external_urls,popularity)),total",
            limit=limit,
            market="US",
            timeout_seconds=8.0,
            call_name="playlist_prompt_playlist_items",
        )
        if not isinstance(result, dict):
            return []
        tracks: List[Dict[str, Any]] = []
        skipped_items = 0
        for item in _safe_iter_playlist_items(result.get("items")):
            track = _safe_extract_track(item)
            if not track:
                skipped_items += 1
                continue
            tracks.append(track)
        if skipped_items:
            logger.info(
                "Playlist tracks parsing skipped %d malformed items for playlist '%s'",
                skipped_items,
                playlist_id,
            )
        try:
            await set_cache(cache_key, json.dumps(tracks), expire=21600)
        except Exception:
            pass
        return tracks
    except Exception as exc:
        logger.warning("Playlist tracks fetch failed for '%s': %s", playlist_id, exc)
        return []


async def _collect_playlist_search_candidates(
    sp: spotipy.Spotify,
    profile: Dict[str, Any],
    source_counts: Dict[str, int],
) -> List[Dict[str, Any]]:
    raw_candidates: List[Dict[str, Any]] = []
    seen_playlist_ids: Set[str] = set()
    terms = profile.get("search_terms") or [profile.get("raw_prompt", "")]
    skipped_playlists = 0
    skipped_tracks = 0

    for term in terms[:4]:
        playlists = await _search_public_playlists(sp, term, limit=5)
        for playlist in playlists:
            playlist_id = _safe_get_playlist_id(playlist)
            if not playlist_id or playlist_id in seen_playlist_ids:
                skipped_playlists += 1
                continue

            tracks_meta = playlist.get("tracks") if isinstance(playlist, dict) else None
            track_count = tracks_meta.get("total", 0) if isinstance(tracks_meta, dict) else 0
            if track_count and track_count < 12:
                continue

            seen_playlist_ids.add(playlist_id)
            for track in await _get_playlist_tracks(sp, playlist_id, limit=35):
                candidate = _normalize_candidate_track(
                    track,
                    source="playlist_search",
                    genres=[],
                    seed_artist_id=None,
                    seed_query=term,
                )
                if not candidate:
                    skipped_tracks += 1
                    continue
                raw_candidates.append(candidate)
                source_counts["playlist_search"] = source_counts.get("playlist_search", 0) + 1

            if len(seen_playlist_ids) >= 12:
                break
        if len(seen_playlist_ids) >= 12:
            break
    if skipped_playlists:
        logger.info("Playlist search skipped %d malformed playlist rows", skipped_playlists)
    if skipped_tracks:
        logger.info("Playlist search skipped %d malformed playlist tracks", skipped_tracks)

    return raw_candidates


async def _build_prompt_first_candidates(
    sp: spotipy.Spotify,
    spotify_id: str,
    access_token: str,
    prompt: str,
    profile: Dict[str, Any],
    limit: int,
) -> Tuple[List[Dict[str, Any]], Dict[str, int], Set[str], Set[str]]:
    source_counts = {
        "playlist_search": 0,
        "prompt_search_tracks": 0,
        "prompt_artist_top_tracks": 0,
        "prompt_artist_catalog": 0,
        "mood_fallback": 0,
    }

    user_top_artists = await recommendation_engine._get_user_top_artists(sp)
    user_genres: Set[str] = set()
    favorite_artist_ids: Set[str] = set()
    for artist in user_top_artists:
        aid = artist.get("id")
        if aid:
            favorite_artist_ids.add(aid)
        for genre in artist.get("genres", []):
            if isinstance(genre, str):
                user_genres.add(genre.lower())

    prompt_type = profile.get("prompt_type", "hybrid")
    search_terms = profile.get("search_terms") or [prompt]
    excluded_ids = await _load_generator_exclusions(spotify_id, prompt, profile=profile)
    raw_candidates: List[Dict[str, Any]] = []

    if prompt_type in {"concrete", "hybrid"}:
        try:
            raw_candidates.extend(await _collect_playlist_search_candidates(sp, profile, source_counts))
        except Exception as exc:
            logger.warning("Playlist search candidate source failed for prompt '%s': %s", prompt, exc)

    prompt_tracks: List[Dict[str, Any]] = []
    for term in search_terms[:5]:
        prompt_tracks.extend(await _search_prompt_tracks(sp, term, limit=20))

    for track in prompt_tracks:
        candidate = _normalize_candidate_track(
            track,
            source="prompt_search_tracks",
            genres=[],
            seed_artist_id=None,
            seed_query=None,
        )
        if not candidate:
            continue
        raw_candidates.append(candidate)
        source_counts["prompt_search_tracks"] += 1

    artist_search_terms = list(search_terms[:4])
    if prompt_type == "abstract":
        for mood in profile.get("moods", []):
            artist_search_terms.extend(VIBE_EXPANSION_TERMS.get(mood, [])[:2])

    prompt_artist_hits: List[Dict[str, Any]] = []
    for term in artist_search_terms[:6]:
        prompt_artist_hits.extend(await _search_prompt_artists(sp, term, limit=12))

    seed_artist_pool: List[Dict[str, Any]] = []
    seen_seed_ids: Set[str] = set()
    for artist in prompt_artist_hits + user_top_artists:
        if not isinstance(artist, dict):
            continue
        aid = artist.get("id")
        if aid and aid not in seen_seed_ids:
            seen_seed_ids.add(aid)
            seed_artist_pool.append(artist)

    def artist_prompt_score(artist: Dict[str, Any]) -> float:
        text = " ".join((artist.get("genres") or [])).lower()
        score = 0.0
        for genre in profile.get("genres", []):
            if genre in text:
                score += 2.0
        if profile.get("language") == "spanish" or profile.get("region") == "latin":
            if any(k in text for k in ["latin", "reggaeton", "urbano", "corridos"]):
                score += 3.0
        if profile.get("prompt_type") == "abstract" and any(
            k in text for k in ["ambient", "dream", "chill", "indie", "r&b", "alternative"]
        ):
            score += 1.2
        return score

    seed_artist_pool.sort(key=artist_prompt_score, reverse=True)
    seed_artist_pool = seed_artist_pool[:20]

    for artist in seed_artist_pool:
        artist_id = artist.get("id")
        artist_genres = artist.get("genres") if isinstance(artist.get("genres"), list) else []
        if not artist_id:
            continue

        top_tracks = await recommendation_engine._get_artist_top_tracks_cached(sp, artist_id)
        random.shuffle(top_tracks)
        for track in top_tracks[:6]:
            candidate = _normalize_candidate_track(
                track,
                source="prompt_artist_top_tracks",
                genres=artist_genres,
                seed_artist_id=artist_id,
                seed_query=None,
            )
            if not candidate:
                continue
            raw_candidates.append(candidate)
            source_counts["prompt_artist_top_tracks"] += 1

        catalog_tracks = await recommendation_engine._get_artist_catalog_tracks(
            sp, artist_id, exclude_ids=excluded_ids, limit=8
        )
        for track in catalog_tracks:
            candidate = _normalize_candidate_track(
                track,
                source="prompt_artist_catalog",
                genres=artist_genres,
                seed_artist_id=artist_id,
                seed_query=None,
            )
            if not candidate:
                continue
            raw_candidates.append(candidate)
            source_counts["prompt_artist_catalog"] += 1

    # Mood fallback remains secondary, with extra weight for abstract prompts.
    mood = _prompt_to_primary_mood(profile)
    mood_limit = min(24, limit + (8 if prompt_type == "abstract" else 0))
    mood_tracks = await recommendation_engine.generate_mood_playlist(
        user_id=spotify_id,
        access_token=access_token,
        mood=mood,
        limit=mood_limit,
    )
    for track in mood_tracks:
        candidate = _normalize_candidate_track(
            track,
            source="mood_fallback",
            genres=[],
            seed_artist_id=None,
            seed_query=None,
        )
        if not candidate:
            continue
        raw_candidates.append(candidate)
        source_counts["mood_fallback"] += 1

    return raw_candidates, source_counts, user_genres, favorite_artist_ids


@router.post("/generate")
async def generate_playlist_from_prompt(
    request: GeneratePlaylistRequest,
    current_user: dict = Depends(get_current_user),
):
    """Generate an AI playlist from a vibe/prompt."""
    perf = RoutePerf("playlists_generate", current_user.get("spotify_id"))
    prompt = (request.prompt or "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt is required")

    limit = max(20, min(request.limit, 40))
    with perf.step("auth"):
        access_token = await get_valid_access_token(current_user)
    with perf.step("spotify_client"):
        sp = await recommendation_engine.get_spotify_client(access_token)
    prompt_profile = _parse_prompt_profile(prompt)
    spotify_id = current_user["spotify_id"]

    with perf.step("build_candidates"):
        raw_candidates, source_counts, user_genres, favorite_artist_ids = await _build_prompt_first_candidates(
            sp=sp,
            spotify_id=spotify_id,
            access_token=access_token,
            prompt=prompt,
            profile=prompt_profile,
            limit=limit,
        )

    with perf.step("load_exclusions"):
        excluded_ids = await _load_generator_exclusions(spotify_id, prompt, profile=prompt_profile)
    scored_tracks: List[Tuple[float, float, float, Dict[str, Any]]] = []
    prompt_survivors = 0
    prompt_type = prompt_profile.get("prompt_type", "hybrid")
    if prompt_type == "concrete":
        prompt_weight, taste_weight = 0.84, 0.16
    elif prompt_type == "abstract":
        prompt_weight, taste_weight = 0.74, 0.26
    else:
        prompt_weight, taste_weight = 0.8, 0.2

    with perf.step("score_rerank"):
        for idx, candidate in enumerate(raw_candidates):
            if not isinstance(candidate, dict):
                logger.warning("Skipping malformed track at generated index=%d", idx)
                continue
            normalized = dict(candidate)
            tid = normalized.get("track_id")
            if not isinstance(tid, str) or not tid:
                logger.warning("Skipping candidate without track_id at generated index=%d", idx)
                continue
            if tid in excluded_ids:
                continue

            p_score = _prompt_score_track(normalized, prompt_profile)
            t_score = _taste_score_track(normalized, user_genres, favorite_artist_ids)
            total = (p_score * prompt_weight) + (t_score * taste_weight)

            source = normalized.get("source", "unknown")
            if source == "playlist_search" and prompt_type in {"concrete", "hybrid"}:
                total += 0.8
            if source == "mood_fallback" and prompt_type == "abstract":
                total += 0.45

            # Strong prompt constraints for explicit language/region prompts.
            if prompt_profile.get("language") == "spanish" and not _looks_latin_or_spanish(normalized):
                total -= 3.0

            if p_score > 0:
                prompt_survivors += 1
            scored_tracks.append((total, p_score, t_score, normalized))

    # If prompt profile is too restrictive, fallback to recommendation engine with prompt mood.
    if len(scored_tracks) < max(8, limit // 3):
        mood = _prompt_to_primary_mood(prompt_profile)
        with perf.step("fallback_recommendations"):
            fallback = await recommendation_engine.generate_recommendations(
                user_id=spotify_id,
                access_token=access_token,
                limit=limit * 2,
            )
        for raw_track in fallback:
            normalized = _normalize_candidate_track(
                raw_track,
                source="fallback_recommendations",
                genres=[],
                seed_artist_id=None,
                seed_query=None,
            )
            if not normalized or normalized.get("track_id") in excluded_ids:
                continue
            p_score = _prompt_score_track(normalized, prompt_profile)
            t_score = _taste_score_track(normalized, user_genres, favorite_artist_ids)
            total = (p_score * prompt_weight) + (t_score * taste_weight)
            if mood == "energetic":
                total += 0.4
            scored_tracks.append((total, p_score, t_score, normalized))
        source_counts["fallback_recommendations"] = len(fallback)

    scored_tracks.sort(key=lambda item: item[0], reverse=True)

    # Prompt-specific diversity and dedupe.
    normalized_tracks = []
    seen_ids = set()
    seen_artists = {}
    strong_prompt_matches = sum(1 for _, p_score, _, _ in scored_tracks if p_score >= 1.5)
    strict_prompt_mode = (
        bool(prompt_profile.get("genres"))
        or bool(prompt_profile.get("language"))
        or bool(prompt_profile.get("region"))
        or prompt_profile.get("popularity_bias") != "neutral"
    )

    for score, p_score, t_score, normalized in scored_tracks:
        if strict_prompt_mode and strong_prompt_matches >= max(8, limit // 2) and p_score < 0.8:
            continue
        tid = normalized["track_id"]
        if tid not in seen_ids:
            primary_artist = (normalized.get("artists") or [normalized.get("artist", "unknown")])[0]
            seen_count = seen_artists.get(primary_artist, 0)
            if seen_count >= 2:
                continue
            seen_ids.add(tid)
            normalized_tracks.append(normalized)
            seen_artists[primary_artist] = seen_count + 1
        if len(normalized_tracks) >= limit:
            break

    playlist_title = f"{prompt.title()} — curated by BlessedEar"
    with perf.step("save_history"):
        await _save_generator_history(
            spotify_id,
            prompt,
            [t["track_id"] for t in normalized_tracks],
            profile=prompt_profile,
        )

    top_genres_repr = {}
    for track in normalized_tracks:
        for genre in track.get("genres", [])[:3]:
            if isinstance(genre, str):
                key = genre.lower()
                top_genres_repr[key] = top_genres_repr.get(key, 0) + 1
    top_genres = sorted(top_genres_repr.items(), key=lambda x: x[1], reverse=True)[:5]
    latin_count = sum(1 for track in normalized_tracks if _looks_latin_or_spanish(track))
    language_distribution = {
        "latin_or_spanish_ratio": round((latin_count / len(normalized_tracks)), 3) if normalized_tracks else 0.0,
        "other_ratio": round((1 - (latin_count / len(normalized_tracks))), 3) if normalized_tracks else 0.0,
    }

    logger.info("Playlist generation prompt='%s' profile=%s", prompt, prompt_profile)
    logger.info(
        "Playlist generation router prompt='%s' strategy=%s weights={prompt: %.2f, taste: %.2f}",
        prompt,
        prompt_type,
        prompt_weight,
        taste_weight,
    )
    logger.info("Playlist generation source breakdown prompt='%s' sources=%s", prompt, source_counts)
    logger.info(
        "Playlist generation filtered prompt='%s' raw=%d scored=%d prompt_survivors=%d final=%d",
        prompt, len(raw_candidates), len(scored_tracks), prompt_survivors, len(normalized_tracks),
    )
    logger.info(
        "Playlist generation final prompt='%s' top_genres=%s language_mix=%s",
        prompt,
        top_genres,
        language_distribution,
    )
    perf.set_meta("raw_candidates", len(raw_candidates))
    perf.set_meta("scored_candidates", len(scored_tracks))
    perf.set_meta("final_tracks", len(normalized_tracks))
    perf.set_meta("sources", source_counts)
    logger.info("[perf] %s", perf.to_log_fields())

    return {
        "playlist_title": playlist_title,
        "prompt": prompt,
        "mood": _prompt_to_primary_mood(prompt_profile),
        "prompt_profile": prompt_profile,
        "tracks": [_serialize_output_track(track) for track in normalized_tracks],
        "track_count": len(normalized_tracks),
    }


@router.post("/export")
async def export_generated_playlist(
    request: ExportGeneratedPlaylistRequest,
    current_user: dict = Depends(get_current_user),
):
    """Create a Spotify playlist from generated tracks and add items."""
    prompt = (request.prompt or "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt is required")
    if not request.tracks:
        raise HTTPException(status_code=400, detail="No tracks provided")

    access_token = await get_valid_access_token(current_user)
    sp = spotipy.Spotify(auth=access_token)

    playlist_name = request.spotify_name or f"{prompt.title()} — curated by BlessedEar"
    playlist_description = "Generated by BlessedEar based on your listening taste."

    spotify_playlist = sp.user_playlist_create(
        user=current_user["spotify_id"],
        name=playlist_name,
        description=playlist_description,
        public=False,
    )

    track_uris = []
    seen_ids = set()
    for raw_track in request.tracks:
        normalized = _normalize_generated_track(raw_track)
        if not normalized:
            continue
        tid = normalized["track_id"]
        if tid and tid not in seen_ids:
            seen_ids.add(tid)
            track_uris.append(f"spotify:track:{tid}")

    if not track_uris:
        raise HTTPException(status_code=400, detail="No valid track IDs provided")

    chunk_size = 100
    for i in range(0, len(track_uris), chunk_size):
        sp.playlist_add_items(spotify_playlist["id"], track_uris[i:i + chunk_size])

    return {
        "message": "Playlist exported to Spotify successfully",
        "spotify_playlist_id": spotify_playlist["id"],
        "spotify_url": spotify_playlist["external_urls"]["spotify"],
        "playlist_name": playlist_name,
        "track_count": len(track_uris),
    }

@router.post("/save", response_model=dict)
async def save_playlist(
    request: SavePlaylistRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Save a generated playlist to the database"""
    try:
        # Convert tracks to JSON string
        track_data = json.dumps(request.tracks)
        
        # Create new playlist
        playlist = Playlist(
            name=request.name,
            description=request.description,
            user_id=current_user["id"],
            track_data=track_data,
            mood=request.mood,
            generation_type=request.generation_type
        )
        
        db.add(playlist)
        db.commit()
        db.refresh(playlist)
        
        return {
            "message": "Playlist saved successfully",
            "playlist_id": playlist.id,
            "name": playlist.name
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error saving playlist: {str(e)}"
        )

@router.get("/my-playlists", response_model=List[PlaylistResponse])
async def get_user_playlists(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all playlists for the current user"""
    try:
        playlists = db.query(Playlist).filter(
            Playlist.user_id == current_user["id"]
        ).order_by(Playlist.created_at.desc()).all()
        
        playlist_responses = []
        for playlist in playlists:
            # Parse track data to get count
            try:
                tracks = json.loads(playlist.track_data)
                track_count = len(tracks)
            except:
                track_count = 0
            
            playlist_responses.append(PlaylistResponse(
                id=playlist.id,
                name=playlist.name,
                description=playlist.description,
                track_count=track_count,
                mood=playlist.mood,
                generation_type=playlist.generation_type,
                is_exported=playlist.is_exported,
                spotify_playlist_id=playlist.spotify_playlist_id,
                created_at=playlist.created_at.isoformat()
            ))
        
        return playlist_responses
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error getting playlists: {str(e)}"
        )

@router.get("/{playlist_id}")
async def get_playlist_details(
    playlist_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get detailed playlist information including tracks"""
    try:
        playlist = db.query(Playlist).filter(
            Playlist.id == playlist_id,
            Playlist.user_id == current_user["id"]
        ).first()
        
        if not playlist:
            raise HTTPException(
                status_code=404,
                detail="Playlist not found"
            )
        
        # Parse track data
        tracks = json.loads(playlist.track_data)
        
        return {
            "id": playlist.id,
            "name": playlist.name,
            "description": playlist.description,
            "tracks": tracks,
            "mood": playlist.mood,
            "generation_type": playlist.generation_type,
            "is_exported": playlist.is_exported,
            "spotify_playlist_id": playlist.spotify_playlist_id,
            "created_at": playlist.created_at.isoformat()
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error getting playlist: {str(e)}"
        )

@router.post("/{playlist_id}/export-to-spotify")
async def export_to_spotify(
    playlist_id: int,
    request: CreateSpotifyPlaylistRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Export a saved playlist to Spotify"""
    try:
        # Get the playlist
        playlist = db.query(Playlist).filter(
            Playlist.id == playlist_id,
            Playlist.user_id == current_user["id"]
        ).first()
        
        if not playlist:
            raise HTTPException(
                status_code=404,
                detail="Playlist not found"
            )
        
        # Get Spotify access token
        spotify_tokens = current_user.get("spotify_tokens", {})
        access_token = spotify_tokens.get("access_token")
        
        if not access_token:
            raise HTTPException(
                status_code=401,
                detail="Spotify access token not found"
            )
        
        # Create Spotify client
        sp = spotipy.Spotify(auth=access_token)
        
        # Parse track data
        tracks = json.loads(playlist.track_data)
        track_uris = []
        seen_ids = set()
        for track in tracks:
            normalized = _normalize_generated_track(track)
            if not normalized:
                continue
            tid = normalized["track_id"]
            if tid not in seen_ids:
                seen_ids.add(tid)
                track_uris.append(f"spotify:track:{tid}")
        
        if not track_uris:
            raise HTTPException(
                status_code=400,
                detail="No valid tracks found in playlist"
            )
        
        # Create Spotify playlist
        spotify_name = request.spotify_name or playlist.name
        spotify_description = request.spotify_description or playlist.description or f"Generated by BlessedEar"
        
        spotify_playlist = sp.user_playlist_create(
            user=current_user["spotify_id"],
            name=spotify_name,
            description=spotify_description,
            public=False
        )
        
        # Add tracks to playlist (Spotify limits to 100 tracks per request)
        chunk_size = 100
        for i in range(0, len(track_uris), chunk_size):
            chunk = track_uris[i:i + chunk_size]
            sp.playlist_add_items(spotify_playlist['id'], chunk)
        
        # Update our database record
        playlist.spotify_playlist_id = spotify_playlist['id']
        playlist.is_exported = True
        db.commit()
        
        return {
            "message": "Playlist exported to Spotify successfully",
            "spotify_playlist_id": spotify_playlist['id'],
            "spotify_url": spotify_playlist['external_urls']['spotify'],
            "track_count": len(track_uris)
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error exporting to Spotify: {str(e)}"
        )

@router.delete("/{playlist_id}")
async def delete_playlist(
    playlist_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a saved playlist"""
    try:
        playlist = db.query(Playlist).filter(
            Playlist.id == playlist_id,
            Playlist.user_id == current_user["id"]
        ).first()
        
        if not playlist:
            raise HTTPException(
                status_code=404,
                detail="Playlist not found"
            )
        
        db.delete(playlist)
        db.commit()
        
        return {"message": "Playlist deleted successfully"}
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error deleting playlist: {str(e)}"
        )
