from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
import json
import spotipy

from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.playlist import Playlist
from app.models.user import User

router = APIRouter()

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
        track_uris = [f"spotify:track:{track['id']}" for track in tracks if track.get('id')]
        
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