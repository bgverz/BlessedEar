from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
import json

from app.api.auth import get_current_user
from app.ml.recommender import RecommendationEngine, AVAILABLE_GENRES
from app.ml.analytics_engine import AnalyticsEngine
from app.core.config import get_settings

router = APIRouter()
settings = get_settings()
analytics_engine = AnalyticsEngine()

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

@router.post("/generate", response_model=RecommendationResponse)
async def generate_recommendations(
    request: RecommendationRequest,
    current_user: dict = Depends(get_current_user)
):
    """Generate personalized recommendations for user"""
    try:
        spotify_tokens = current_user.get("spotify_tokens", {})
        access_token = spotify_tokens.get("access_token")
        
        if not access_token:
            raise HTTPException(
                status_code=401,
                detail="Spotify access token not found. Please re-authenticate."
            )
        
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
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error generating recommendations: {str(e)}"
        )

@router.post("/mood-playlist", response_model=RecommendationResponse)
async def generate_mood_playlist(
    request: MoodPlaylistRequest,
    current_user: dict = Depends(get_current_user)
):
    """Generate playlist based on mood"""
    try:
        valid_moods = ['happy', 'sad', 'energetic', 'chill', 'focus', 'party']
        if request.mood.lower() not in valid_moods:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid mood. Must be one of: {', '.join(valid_moods)}"
            )
        
        spotify_tokens = current_user.get("spotify_tokens", {})
        access_token = spotify_tokens.get("access_token")
        
        if not access_token:
            raise HTTPException(
                status_code=401,
                detail="Spotify access token not found. Please re-authenticate."
            )
        
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
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error generating mood playlist: {str(e)}"
        )

@router.get("/profile")
async def get_user_profile(current_user: dict = Depends(get_current_user)):
    """Get user's real music profile (genre breakdown, popularity taste, diversity)"""
    try:
        spotify_tokens = current_user.get("spotify_tokens", {})
        access_token = spotify_tokens.get("access_token")

        if not access_token:
            raise HTTPException(
                status_code=401,
                detail="Spotify access token not found. Please re-authenticate."
            )

        sp = await recommendation_engine.get_spotify_client(access_token)
        short_term = await recommendation_engine.get_user_top_tracks(sp, "short_term", 50)
        medium_term = await recommendation_engine.get_user_top_tracks(sp, "medium_term", 50)
        long_term = await recommendation_engine.get_user_top_tracks(sp, "long_term", 50)

        user_profile = await analytics_engine.build_profile(sp, short_term, medium_term, long_term)

        if "error" in user_profile:
            raise HTTPException(
                status_code=404,
                detail=user_profile["error"]
            )

        return {"user_id": current_user["spotify_id"], **user_profile}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error getting user profile: {str(e)}"
        )

@router.get("/similar-tracks/{track_id}")
async def get_similar_tracks(
    track_id: str,
    limit: int = Query(10, ge=1, le=50),
    current_user: dict = Depends(get_current_user)
):
    """Get tracks similar to a specific track"""
    try:
        spotify_tokens = current_user.get("spotify_tokens", {})
        access_token = spotify_tokens.get("access_token")
        
        if not access_token:
            raise HTTPException(
                status_code=401,
                detail="Spotify access token not found. Please re-authenticate."
            )
        
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
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error finding similar tracks: {str(e)}"
        )

@router.get("/top-tracks")
async def get_user_top_tracks(
    time_range: str = Query("medium_term", regex="^(short_term|medium_term|long_term)$"),
    limit: int = Query(20, ge=1, le=50),
    current_user: dict = Depends(get_current_user)
):
    """Get user's top tracks from Spotify"""
    try:
        spotify_tokens = current_user.get("spotify_tokens", {})
        access_token = spotify_tokens.get("access_token")
        
        if not access_token:
            raise HTTPException(
                status_code=401,
                detail="Spotify access token not found. Please re-authenticate."
            )
        
        top_tracks = await recommendation_engine.get_user_top_tracks(
            sp=await recommendation_engine.get_spotify_client(access_token),
            time_range=time_range,
            limit=limit
        )
        
        return {"top_tracks": top_tracks, "time_range": time_range}
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error getting top tracks: {str(e)}"
        )
    
@router.get("/discover/{discover_type}")
async def discover_music(
    discover_type: str,
    limit: int = Query(12, ge=1, le=50),
    current_user: dict = Depends(get_current_user)
):
    """Discover music by type: similar, new-genres, trending, deep-cuts"""
    try:
        spotify_tokens = current_user.get("spotify_tokens", {})
        access_token = spotify_tokens.get("access_token")
        
        if not access_token:
            raise HTTPException(status_code=401, detail="Spotify access token not found")
        
        if discover_type == 'similar':
            recommendations = await recommendation_engine.generate_recommendations(
                user_id=current_user["spotify_id"],
                access_token=access_token,
                limit=limit
            )
        elif discover_type == 'new-genres':
            recommendations = await recommendation_engine.generate_genre_discovery(
                user_id=current_user["spotify_id"],
                access_token=access_token,
                limit=limit
            )
        else:
            # Map remaining discover types to the closest mood strategy
            mood_mapping = {
                'trending': 'party',
                'deep-cuts': 'chill'
            }
            mood = mood_mapping.get(discover_type, 'chill')
            recommendations = await recommendation_engine.generate_mood_playlist(
                user_id=current_user["spotify_id"],
                access_token=access_token,
                mood=mood,
                limit=limit
            )

        return {"tracks": recommendations, "discover_type": discover_type}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error discovering music: {str(e)}")

@router.get("/genres")
async def get_available_genres(current_user: dict = Depends(get_current_user)):
    """Get available genre seeds used for genre discovery"""
    try:
        return {"genres": AVAILABLE_GENRES}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting genres: {str(e)}")
    
def require_debug():
    """Guard that 404s debug routes unless the app is running in debug mode"""
    if not settings.debug:
        raise HTTPException(status_code=404, detail="Not found")

@router.get("/debug/user-cache", dependencies=[Depends(require_debug)])
async def debug_user_cache(current_user: dict = Depends(get_current_user)):
    """Debug endpoint to check user cache"""
    return {
        "user_data": current_user,
        "cache_check": "Cache is working if you see this"
    }

@router.get("/debug/spotify-test", dependencies=[Depends(require_debug)])
async def test_spotify_api(current_user: dict = Depends(get_current_user)):
    """Test what Spotify API calls actually work"""
    try:
        spotify_tokens = current_user.get("spotify_tokens", {})
        access_token = spotify_tokens.get("access_token")
        
        if not access_token:
            return {"error": "No access token"}
        
        sp = spotipy.Spotify(auth=access_token)
        
        tests = {}
        
        # Test 1: Basic user info
        try:
            user = sp.me()
            tests["user_info"] = f"✅ User: {user['display_name']}"
        except Exception as e:
            tests["user_info"] = f"❌ User info failed: {e}"
        
        # Test 2: Genre seeds
        try:
            genres = sp.recommendation_genre_seeds()
            tests["genre_seeds"] = f"✅ Found {len(genres['genres'])} genres"
        except Exception as e:
            tests["genre_seeds"] = f"❌ Genre seeds failed: {e}"
        
        # Test 3: Simple recommendation
        try:
            recs = sp.recommendations(seed_genres=['pop'], limit=1)
            tests["simple_rec"] = f"✅ Simple rec: {recs['tracks'][0]['name']}"
        except Exception as e:
            tests["simple_rec"] = f"❌ Simple rec failed: {e}"
        
        # Test 4: Recommendation with market
        try:
            recs = sp.recommendations(seed_genres=['pop'], limit=1, market='US')
            tests["market_rec"] = f"✅ Market rec: {recs['tracks'][0]['name']}"
        except Exception as e:
            tests["market_rec"] = f"❌ Market rec failed: {e}"
        
        # Test 5: Top tracks
        try:
            top = sp.current_user_top_tracks(limit=1)
            tests["top_tracks"] = f"✅ Top track: {top['items'][0]['name']}"
        except Exception as e:
            tests["top_tracks"] = f"❌ Top tracks failed: {e}"
        
        return tests
        
    except Exception as e:
        return {"error": f"General test failed: {e}"}
