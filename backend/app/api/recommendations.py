from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
import spotipy

from app.api.auth import get_current_user, get_valid_access_token
from app.core.config import get_settings
from app.ml.recommender import RecommendationEngine

router = APIRouter()
settings = get_settings()

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

        return {"top_tracks": top_tracks, "time_range": time_range}

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
