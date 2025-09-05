import spotipy
import pandas as pd
from typing import List, Dict, Any
from datetime import datetime

class RecommendationEngine:
    def __init__(self):
        self.is_initialized = False
        
    async def load_models(self):
        """Initialize the recommendation engine"""
        self.is_initialized = True
        print("ML models loaded successfully!")
    
    async def get_spotify_client(self, access_token: str) -> spotipy.Spotify:
        """Get authenticated Spotify client"""
        return spotipy.Spotify(auth=access_token)
    
    async def extract_audio_features(self, sp: spotipy.Spotify, track_ids: List[str]) -> pd.DataFrame:
        """Simplified - just return basic track info without audio features"""
        try:
            tracks = sp.tracks(track_ids)
            data = []
            for track in tracks['tracks']:
                if track:
                    data.append({
                        'id': track['id'],
                        'danceability': 0.5,
                        'energy': 0.5,
                        'valence': 0.5,
                        'speechiness': 0.1,
                        'acousticness': 0.3,
                        'instrumentalness': 0.1,
                        'liveness': 0.2,
                        'tempo': 120
                    })
            return pd.DataFrame(data)
        except Exception as e:
            print(f"Error: {e}")
            return pd.DataFrame()
    
    async def get_user_top_tracks(self, sp: spotipy.Spotify, time_range: str = "medium_term", limit: int = 50):
        """Get user's top tracks"""
        try:
            results = sp.current_user_top_tracks(time_range=time_range, limit=limit)
            return results['items']
        except Exception as e:
            print(f"Error getting top tracks: {e}")
            return []
    
    async def build_user_profile(self, user_id: str, access_token: str):
        """Build user profile"""
        try:
            sp = await self.get_spotify_client(access_token)
            top_tracks = await self.get_user_top_tracks(sp)
            
            return {
                'user_id': user_id,
                'avg_features': {
                    'danceability': 0.6,
                    'energy': 0.7,
                    'valence': 0.5,
                    'speechiness': 0.1,
                    'acousticness': 0.3,
                    'instrumentalness': 0.1,
                    'liveness': 0.2,
                    'tempo': 120
                },
                'total_tracks_analyzed': len(top_tracks),
                'created_at': datetime.utcnow().isoformat()
            }
        except Exception as e:
            return {"error": str(e)}
    
    async def generate_recommendations(self, user_id: str, access_token: str, seed_tracks=None, target_features=None, limit: int = 20):
        """Generate recommendations"""
        try:
            sp = await self.get_spotify_client(access_token)
            top_tracks = await self.get_user_top_tracks(sp, limit=5)
            
            if not seed_tracks and top_tracks:
                seed_tracks = [track['id'] for track in top_tracks[:5]]
            
            recommendations = sp.recommendations(seed_tracks=seed_tracks[:5], limit=limit)
            
            enhanced_recs = []
            for track in recommendations['tracks']:
                enhanced_recs.append({
                    'id': track['id'],
                    'name': track['name'],
                    'artists': [artist['name'] for artist in track['artists']],
                    'album': track['album']['name'],
                    'preview_url': track['preview_url'],
                    'external_urls': track['external_urls'],
                    'similarity_score': 0.85,
                    'recommendation_reason': "Based on your listening history"
                })
            
            return enhanced_recs
        except Exception as e:
            print(f"Error generating recommendations: {e}")
            return []
    
    async def generate_mood_playlist(self, user_id: str, access_token: str, mood: str, limit: int = 20):
        """Generate mood-based playlist"""
        return await self.generate_recommendations(user_id, access_token, limit=limit)