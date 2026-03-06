from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
import asyncio
import logging
import time
import spotipy

from app.api.auth import get_current_user, get_valid_access_token
from app.core.config import get_settings
from app.ml.recommender import RecommendationEngine

router = APIRouter()
settings = get_settings()
logger = logging.getLogger(__name__)

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

recommendation_engine = RecommendationEngine()


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
async def generate_recommendations(
    request: RecommendationRequest,
    current_user: dict = Depends(get_current_user)
):
    """Generate personalized recommendations for user"""
    try:
        access_token = await _require_access_token(current_user)

        recommendations = await recommendation_engine.generate_recommendations(
            user_id=current_user["spotify_id"],
            access_token=access_token,
            seed_tracks=request.seed_tracks,
            target_features=request.target_features,
            limit=request.limit
        )

        if not recommendations:
            raise HTTPException(
                status_code=404,
                detail="Could not generate recommendations. Please try again."
            )

        return RecommendationResponse(tracks=recommendations)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating recommendations: {str(e)}")


@router.post("/mood-playlist", response_model=RecommendationResponse)
async def generate_mood_playlist(
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

    try:
        access_token = await _require_access_token(current_user)

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

        return RecommendationResponse(tracks=recommendations)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating mood playlist: {str(e)}")


@router.get("/profile")
async def get_user_profile(current_user: dict = Depends(get_current_user)):
    """Get user's music profile and preferences"""
    try:
        access_token = await _require_access_token(current_user)

        user_profile = await recommendation_engine.build_user_profile(
            user_id=current_user["spotify_id"],
            access_token=access_token
        )

        if "error" in user_profile:
            raise HTTPException(status_code=404, detail=user_profile["error"])

        return user_profile

    except HTTPException:
        raise
    except Exception as e:
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
    try:
        access_token = await _require_access_token(current_user)

        top_tracks = await recommendation_engine.get_user_top_tracks(
            sp=await recommendation_engine.get_spotify_client(access_token),
            time_range=time_range,
            limit=limit
        )

        normalized_tracks = [_normalize_top_track(track) for track in top_tracks]
        return {"top_tracks": normalized_tracks, "time_range": time_range}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting top tracks: {str(e)}")


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
