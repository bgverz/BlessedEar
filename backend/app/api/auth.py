from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPBearer
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import jwt as pyjwt
from datetime import datetime, timedelta
from typing import Optional
import json

from app.core.config import get_settings
from app.core.database import get_db, set_cache, get_cache, delete_cache
from app.models.user import User, UserCreate
from sqlalchemy.orm import Session

router = APIRouter()
settings = get_settings()
oauth2_scheme = HTTPBearer()

def get_spotify_oauth():
    return SpotifyOAuth(
        client_id=settings.spotify_client_id,
        client_secret=settings.spotify_client_secret,
        redirect_uri=settings.spotify_redirect_uri,
        scope="user-read-private user-read-email playlist-modify-public user-top-read user-read-recently-played user-library-read playlist-read-private"
    )

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes)
    to_encode.update({"exp": expire})
    encoded_jwt = pyjwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return encoded_jwt

async def get_current_user(credentials: HTTPBearer = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        token = credentials.credentials
        payload = pyjwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        spotify_id: str = payload.get("sub")
        if spotify_id is None:
            raise credentials_exception
            
        print(f"JWT DECODED SPOTIFY_ID: {spotify_id}")
        
    except pyjwt.PyJWTError as e:
        print(f"JWT DECODE ERROR: {e}")
        raise credentials_exception
    
    user_data = await get_cache(f"user:{spotify_id}")
    print(f"CACHE DATA FOR {spotify_id}: {user_data}")
    
    if user_data is None:
        print(f"NO CACHE DATA FOUND FOR USER: {spotify_id}")
        raise credentials_exception
    
    parsed_data = json.loads(user_data)
    print(f"RETURNING USER DATA: {parsed_data.get('display_name')} ({parsed_data.get('spotify_id')})")
    return parsed_data

@router.get("/login")
async def login(force: bool = Query(False, description="Force fresh authentication")):
    """Initiate Spotify OAuth flow"""
    sp_oauth = get_spotify_oauth()
    
    if force:
        auth_url = sp_oauth.get_authorize_url(show_dialog=True)
    else:
        auth_url = sp_oauth.get_authorize_url()
    
    return {"auth_url": auth_url}

@router.get("/callback")
async def callback(code: str, db: Session = Depends(get_db)):
    """Handle Spotify OAuth callback"""
    try:
        sp_oauth = get_spotify_oauth()
        token_info = sp_oauth.get_access_token(code)
        
        sp = spotipy.Spotify(auth=token_info['access_token'])
        spotify_user = sp.current_user()
        
        print(f"SPOTIFY USER FROM API: {spotify_user['id']} - {spotify_user.get('display_name', 'No Name')}")
        print(f"SPOTIFY EMAIL: {spotify_user.get('email', 'No Email')}")
        
        await delete_cache(f"user:{spotify_user['id']}")
        
        user = db.query(User).filter(User.spotify_id == spotify_user['id']).first()
        if not user:
            user_data = UserCreate(
                spotify_id=spotify_user['id'],
                email=spotify_user.get('email'),
                display_name=spotify_user.get('display_name'),
                spotify_tokens=token_info
            )
            user = User(**user_data.dict())
            db.add(user)
            print(f"CREATED NEW USER: {user.spotify_id}")
        else:
            user.spotify_tokens = token_info
            user.last_login = datetime.utcnow()
            print(f"UPDATED EXISTING USER: {user.spotify_id}")
        
        db.commit()
        
        access_token = create_access_token(data={"sub": user.spotify_id})
        print(f"ACCESS TOKEN BEING CREATED FOR: {user.spotify_id}")
        
        user_cache_data = {
            "id": user.id,
            "spotify_id": user.spotify_id,
            "display_name": user.display_name,
            "spotify_tokens": token_info
        }
        
        await set_cache(f"user:{user.spotify_id}", json.dumps(user_cache_data))
        
        print(f"Successfully authenticated user: {user.display_name} ({user.spotify_id})")
        
        return RedirectResponse(
            url=f"http://localhost:3000/dashboard?token={access_token}&fresh=true",
            status_code=302
        )
        
    except Exception as e:
        print(f"Authentication error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Authentication failed: {str(e)}"
        )

@router.get("/me")
async def get_current_user_info(current_user: dict = Depends(get_current_user)):
    """Get current user information"""
    return current_user

@router.post("/logout")
async def logout(current_user: dict = Depends(get_current_user)):
    """Clear user session and force fresh authentication"""
    try:
        spotify_id = current_user['spotify_id']
        print(f"Logging out user: {current_user.get('display_name')} ({spotify_id})")
        
        await delete_cache(f"user:{spotify_id}")
        
        await delete_cache(f"recommendations:{spotify_id}")
        await delete_cache(f"profile:{spotify_id}")
        
        return {"message": "Logged out successfully", "spotify_id": spotify_id}
        
    except Exception as e:
        print(f"Logout error: {str(e)}")
        return {"message": "Logged out successfully"}

@router.post("/refresh")
async def refresh_spotify_token(current_user: dict = Depends(get_current_user)):
    """Refresh Spotify access token"""
    try:
        sp_oauth = get_spotify_oauth()
        tokens = current_user.get("spotify_tokens")
        
        if not tokens or not tokens.get("refresh_token"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="No refresh token available"
            )
        
        new_tokens = sp_oauth.refresh_access_token(tokens["refresh_token"])
        
        current_user["spotify_tokens"] = new_tokens
        await set_cache(
            f"user:{current_user['spotify_id']}", 
            json.dumps(current_user)
        )
        
        return {"message": "Token refreshed successfully"}
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Token refresh failed: {str(e)}"
        )