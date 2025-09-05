from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict, Any
from pydantic import BaseModel

from app.api.auth import get_current_user

router = APIRouter()

class CreatePlaylistRequest(BaseModel):
    name: str
    description: str = ""
    track_ids: List[str]

@router.post("/create")
async def create_spotify_playlist(
    request: CreatePlaylistRequest,
    current_user: dict = Depends(get_current_user)
):
    """Create a new Spotify playlist"""
    try:
        return {
            "message": "Playlist creation endpoint - coming soon!",
            "playlist_name": request.name,
            "track_count": len(request.track_ids)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating playlist: {str(e)}")

@router.get("/my-playlists")
async def get_user_playlists(current_user: dict = Depends(get_current_user)):
    """Get user's playlists"""
    try:
        return {
            "message": "Get playlists endpoint - coming soon!",
            "user": current_user.get("display_name", "Unknown")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching playlists: {str(e)}")