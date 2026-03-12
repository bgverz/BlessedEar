from fastapi import APIRouter, Depends, HTTPException, Request, status, Query
from slowapi import Limiter
from slowapi.util import get_remote_address
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPBearer
from pydantic import BaseModel
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from spotipy.cache_handler import MemoryCacheHandler
from jose import JWTError, ExpiredSignatureError, jwt
import time
import secrets
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
import json
import uuid

from app.core.config import get_settings
from app.core.database import get_db, set_cache, get_cache, delete_cache
from app.models.user import User, UserCreate
from sqlalchemy.orm import Session

router = APIRouter()
settings = get_settings()
oauth2_scheme = HTTPBearer()
logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)


def get_spotify_oauth():
    """
    Return a fresh SpotifyOAuth instance with a per-instance MemoryCacheHandler.

    Using MemoryCacheHandler (instead of the default CacheFileHandler) prevents
    spotipy from writing or reading tokens from the shared .cache file on disk.
    Without this, get_access_token(code) would return a previously cached token
    (e.g. Braden Garcia's) even when a different Spotify account (e.g. _maddiepalm)
    completed the OAuth flow — causing account-switching to silently reuse the wrong
    identity.
    """
    return SpotifyOAuth(
        client_id=settings.spotify_client_id,
        client_secret=settings.spotify_client_secret,
        redirect_uri=settings.spotify_redirect_uri,
        scope=(
            "user-read-private user-read-email "
            "playlist-modify-public playlist-modify-private "
            "user-top-read user-read-recently-played "
            "user-library-read "
            "playlist-read-private playlist-read-collaborative"
        ),
        show_dialog=True,
        cache_handler=MemoryCacheHandler(),
    )


def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


async def get_current_user(credentials: HTTPBearer = Depends(oauth2_scheme)):
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

    except ExpiredSignatureError:
        raise credentials_exception
    except JWTError:
        raise credentials_exception
    except Exception:
        raise credentials_exception

    user_data = await get_cache(f"user:{spotify_id}")

    if user_data is None:
        raise credentials_exception

    try:
        return json.loads(user_data)
    except json.JSONDecodeError:
        raise credentials_exception


async def get_valid_access_token(user_data: dict) -> str:
    """
    Return a valid Spotify access token for user_data.

    If the stored token expires within the next 60 seconds, attempt a
    proactive refresh using the stored refresh_token and persist the new
    tokens back to the in-memory cache so subsequent requests reuse them.

    Logs the token expiry state and whether a refresh occurred.
    """
    tokens = user_data.get("spotify_tokens", {})
    expires_at = tokens.get("expires_at", 0)
    remaining = expires_at - time.time()

    logger.debug(
        "Token for %s: expires_at=%.0f remaining=%.0fs",
        user_data.get("spotify_id"), expires_at, remaining,
    )

    if remaining > 60:
        return tokens["access_token"]

    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        logger.warning(
            "No refresh token available for %s — returning potentially stale access token",
            user_data.get("spotify_id"),
        )
        return tokens["access_token"]

    try:
        sp_oauth = get_spotify_oauth()
        new_tokens = sp_oauth.refresh_access_token(refresh_token)
        user_data["spotify_tokens"] = new_tokens
        await set_cache(f"user:{user_data['spotify_id']}", json.dumps(user_data))
        logger.info(
            "Token refreshed for %s: new expires_at=%.0f",
            user_data["spotify_id"], new_tokens.get("expires_at", 0),
        )
        return new_tokens["access_token"]
    except Exception as exc:
        logger.warning(
            "Token refresh failed for %s: %s — using existing token",
            user_data.get("spotify_id"), exc,
        )
        return tokens["access_token"]


@router.get("/login")
@limiter.limit("20/minute")
async def login(request: Request, force: bool = Query(True, description="Force fresh authentication (always show Spotify dialog)")):
    """Initiate Spotify OAuth flow.

    show_dialog=True is always sent so Spotify shows the account-chooser/consent
    screen on every login, making it possible to switch accounts.
    A random state token is generated per request and cached for 10 minutes for
    CSRF validation in the callback.
    """
    state = secrets.token_urlsafe(16)
    await set_cache(f"oauth_state:{state}", "valid", expire=600)
    sp_oauth = get_spotify_oauth()
    auth_url = sp_oauth.get_authorize_url(state=state)
    logger.debug("OAuth login initiated: state=%s", state)
    return {"auth_url": auth_url}


@router.get("/callback")
@limiter.limit("20/minute")
async def callback(request: Request,
    code: str,
    state: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Handle Spotify OAuth callback.

    Validates the CSRF state token generated in /login, then exchanges the
    Spotify code for tokens.  The resulting JWT is stored under a one-time
    code so it is never exposed in the redirect URL.
    """
    if not state:
        logger.warning("OAuth callback rejected: missing state parameter")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing OAuth state parameter. Please start the login flow again.",
        )
    cached = await get_cache(f"oauth_state:{state}")
    if not cached:
        logger.warning("OAuth callback: invalid or expired state=%s — rejecting", state)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OAuth state. Please start the login flow again.",
        )
    await delete_cache(f"oauth_state:{state}")
    logger.debug("OAuth callback: state=%s validated and consumed", state)

    try:
        sp_oauth = get_spotify_oauth()
        token_info = sp_oauth.get_access_token(code, check_cache=False)

        sp = spotipy.Spotify(auth=token_info['access_token'])
        spotify_user = sp.current_user()
        spotify_id = spotify_user['id']
        display_name = spotify_user.get('display_name', spotify_id)

        logger.info(
            "OAuth callback: Spotify identity from new token — spotify_id=%s display_name=%r",
            spotify_id, display_name,
        )

        await delete_cache(f"user:{spotify_id}")
        await delete_cache(f"recommendations:{spotify_id}")
        await delete_cache(f"profile:{spotify_id}")
        await delete_cache(f"dna:{spotify_id}")
        await delete_cache(f"library:{spotify_id}")
        logger.debug("OAuth callback: cleared all caches for spotify_id=%s", spotify_id)

        user = db.query(User).filter(User.spotify_id == spotify_id).first()
        if not user:
            user_data = UserCreate(
                spotify_id=spotify_id,
                email=spotify_user.get('email'),
                display_name=display_name,
                spotify_tokens=token_info,
            )
            user = User(**user_data.model_dump())
            db.add(user)
            logger.info(
                "OAuth callback: new user row created — spotify_id=%s display_name=%r",
                spotify_id, display_name,
            )
        else:
            user.spotify_tokens = token_info
            user.last_login = datetime.now(timezone.utc)
            logger.info(
                "OAuth callback: existing user row updated — spotify_id=%s display_name=%r",
                spotify_id, display_name,
            )

        db.commit()

        access_token = create_access_token(data={"sub": user.spotify_id})

        user_cache_data = {
            "id": user.id,
            "spotify_id": user.spotify_id,
            "display_name": user.display_name,
            "spotify_tokens": token_info,
        }
        await set_cache(f"user:{user.spotify_id}", json.dumps(user_cache_data))

        auth_code = str(uuid.uuid4())
        await set_cache(f"auth_code:{auth_code}", access_token, expire=60)

        return RedirectResponse(
            url=f"{settings.frontend_url}/dashboard?code={auth_code}&fresh=true",
            status_code=302,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("OAuth callback error: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Authentication failed. Please try again.",
        )


class ExchangeRequest(BaseModel):
    code: str


@router.post("/exchange")
@limiter.limit("20/minute")
async def exchange_code(request: Request, body: ExchangeRequest):
    """Exchange a one-time auth code for a JWT access token.

    The code is sent in the JSON request body (not a query parameter) so it
    never appears in server access logs, browser history, or Referer headers.
    """
    access_token = await get_cache(f"auth_code:{body.code}")
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired auth code"
        )
    await delete_cache(f"auth_code:{body.code}")
    return {"access_token": access_token}


@router.get("/me")
async def get_current_user_info(current_user: dict = Depends(get_current_user)):
    """Get current user information"""
    return current_user


@router.post("/logout")
async def logout(current_user: dict = Depends(get_current_user)):
    """Clear server-side session for this user.

    Deletes the cached user/token mapping so the next login must complete a
    fresh Spotify OAuth round-trip.  The client should also discard its JWT.
    """
    spotify_id = current_user['spotify_id']
    await delete_cache(f"user:{spotify_id}")
    await delete_cache(f"recommendations:{spotify_id}")
    await delete_cache(f"profile:{spotify_id}")
    await delete_cache(f"dna:{spotify_id}")
    await delete_cache(f"library:{spotify_id}")
    logger.info("User %s logged out: server cache cleared", spotify_id)
    return {"message": "Logged out successfully"}


@router.post("/refresh")
async def refresh_spotify_token(current_user: dict = Depends(get_current_user)):
    """Refresh Spotify access token"""
    new_access_token = await get_valid_access_token(current_user)
    return {"message": "Token refreshed successfully", "access_token": new_access_token}


@router.post("/switch")
async def switch_account(current_user: dict = Depends(get_current_user)):
    """
    Prepare a clean account-switch.

    Clears every server-side cache entry tied to the current session so
    the next OAuth flow starts with a blank slate.  The client must:
    1. Discard its stored JWT after calling this endpoint.
    2. Navigate to /api/auth/login to begin a fresh Spotify OAuth flow.

    Returns the Spotify auth URL so the client can redirect in one round-trip.
    """
    spotify_id = current_user['spotify_id']
    await delete_cache(f"user:{spotify_id}")
    await delete_cache(f"recommendations:{spotify_id}")
    await delete_cache(f"profile:{spotify_id}")
    await delete_cache(f"dna:{spotify_id}")
    await delete_cache(f"library:{spotify_id}")
    logger.info("Account switch initiated for %s: all server caches cleared", spotify_id)

    state = secrets.token_urlsafe(16)
    await set_cache(f"oauth_state:{state}", "valid", expire=600)
    sp_oauth = get_spotify_oauth()
    auth_url = sp_oauth.get_authorize_url(state=state)

    return {"message": "Session cleared", "auth_url": auth_url}
