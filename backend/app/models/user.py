from sqlalchemy import Column, Integer, String, DateTime, JSON, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from pydantic import BaseModel
from typing import Optional, Dict, Any
from app.core.database import Base

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    spotify_id = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True)
    display_name = Column(String)
    
    spotify_tokens = Column(JSON)
    
    preferences = Column(JSON, default={})
    
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, default=datetime.utcnow)
    
    playlists = relationship("Playlist", back_populates="user")

class UserCreate(BaseModel):
    spotify_id: str
    email: Optional[str] = None
    display_name: Optional[str] = None
    spotify_tokens: Dict[str, Any]

class UserResponse(BaseModel):
    id: int
    spotify_id: str
    email: Optional[str]
    display_name: Optional[str]
    created_at: datetime
    last_login: Optional[datetime]
    
    class Config:
        from_attributes = True

class UserPreferences(BaseModel):
    energy_preference: Optional[float] = None
    valence_preference: Optional[float] = None
    danceability_preference: Optional[float] = None
    preferred_genres: Optional[list] = []
    discovery_mode: Optional[str] = "balanced"