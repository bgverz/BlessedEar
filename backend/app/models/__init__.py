# app/models/__init__.py
from app.core.database import Base

# Import models in the right order
from .user import User
from .playlist import Playlist

# This ensures both models are loaded before relationships are established
__all__ = ["User", "Playlist", "Base"]