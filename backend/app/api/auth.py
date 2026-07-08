from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPBearer
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import jwt
import time
from datetime import datetime, timedelta
from typing import Optional

from app.core.config import get_settings
from app.core.database import get_db
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
    
    try:
        encoded_jwt = jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
        return encoded_jwt
    except Exception as e:
        print(f"JWT ENCODE ERROR: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Token creation failed: {str(e)}"
        )

def user_to_dict(user: User) -> dict:
    return {
        "id": user.id,
        "spotify_id": user.spotify_id,
        "email": user.email,
        "display_name": user.display_name,
        "spotify_tokens": user.spotify_tokens,
    }

def refresh_user_spotify_tokens(db: Session, user: User) -> dict:
    """Refresh the user's Spotify access token using their refresh token and persist it"""
    tokens = user.spotify_tokens or {}
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No refresh token available, please re-authenticate",
        )

    sp_oauth = get_spotify_oauth()
    new_tokens = sp_oauth.refresh_access_token(refresh_token)
    # Spotify sometimes omits refresh_token on renewal; keep the old one if so
    new_tokens.setdefault("refresh_token", refresh_token)

    user.spotify_tokens = new_tokens
    db.commit()
    return new_tokens

async def get_current_user(
    credentials: HTTPBearer = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        token = credentials.credentials
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm]
        )
        spotify_id: str = payload.get("sub")
        if spotify_id is None:
            raise credentials_exception
    except (jwt.InvalidTokenError, jwt.ExpiredSignatureError):
        raise credentials_exception

    user = db.query(User).filter(User.spotify_id == spotify_id).first()
    if user is None or not user.spotify_tokens:
        raise credentials_exception

    tokens = user.spotify_tokens
    expires_at = tokens.get("expires_at")
    if expires_at is not None and time.time() >= expires_at - 60:
        try:
            refresh_user_spotify_tokens(db, user)
        except Exception as e:
            print(f"Spotify token refresh failed for {spotify_id}: {e}")
            raise credentials_exception

    return user_to_dict(user)

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
        else:
            user.email = spotify_user.get('email')
            user.display_name = spotify_user.get('display_name')
            user.spotify_tokens = token_info
            user.last_login = datetime.utcnow()

        db.commit()

        access_token = create_access_token(data={"sub": user.spotify_id})

        return RedirectResponse(
            url=f"{settings.frontend_url}/dashboard?token={access_token}&fresh=true",
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
async def logout(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Clear the user's stored Spotify tokens, requiring re-authentication on next login"""
    user = db.query(User).filter(User.spotify_id == current_user['spotify_id']).first()
    if user:
        user.spotify_tokens = None
        db.commit()

    return {"message": "Logged out successfully", "spotify_id": current_user['spotify_id']}

@router.post("/refresh")
async def refresh_spotify_token(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Manually refresh the Spotify access token (also happens automatically when it's near expiry)"""
    user = db.query(User).filter(User.spotify_id == current_user['spotify_id']).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    try:
        refresh_user_spotify_tokens(db, user)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Token refresh failed: {str(e)}")

    return {"message": "Token refreshed successfully"}