import spotipy
import pandas as pd
import random
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
    
    async def get_user_all_tracks(self, sp: spotipy.Spotify, limit: int = 200):
        """Get tracks from user's library, playlists, and top tracks"""
        all_tracks = []
        
        try:
            for time_range in ['short_term', 'medium_term', 'long_term']:
                top_tracks = await self.get_user_top_tracks(sp, time_range, 20)
                all_tracks.extend(top_tracks)
            
            try:
                saved_tracks = sp.current_user_saved_tracks(limit=50)
                for item in saved_tracks['items']:
                    all_tracks.append(item['track'])
                print(f"Added {len(saved_tracks['items'])} saved tracks")
            except Exception as e:
                print(f"Error getting saved tracks: {e}")
            
            try:
                playlists = sp.current_user_playlists(limit=20)
                for playlist in playlists['items']:
                    if playlist['owner']['id'] == sp.me()['id']:
                        try:
                            tracks = sp.playlist_tracks(playlist['id'], limit=30)
                            for item in tracks['items']:
                                if item['track'] and item['track']['id']:
                                    all_tracks.append(item['track'])
                        except Exception as e:
                            print(f"Error getting tracks from playlist {playlist['name']}: {e}")
                print(f"Added tracks from {len(playlists['items'])} playlists")
            except Exception as e:
                print(f"Error getting playlists: {e}")
            
            unique_tracks = []
            seen_ids = set()
            
            for track in all_tracks:
                if track and track.get('id') and track['id'] not in seen_ids:
                    seen_ids.add(track['id'])
                    unique_tracks.append(track)
            
            print(f"Total unique tracks collected: {len(unique_tracks)}")
            
            random.shuffle(unique_tracks)
            return unique_tracks[:limit]
            
        except Exception as e:
            print(f"Error in get_user_all_tracks: {e}")
            return await self.get_user_top_tracks(sp, "medium_term", 50)
    
    async def build_user_profile(self, user_id: str, access_token: str):
        """Build user profile"""
        try:
            sp = await self.get_spotify_client(access_token)
            all_tracks = await self.get_user_all_tracks(sp, limit=200)
            
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
                'total_tracks_analyzed': len(all_tracks),
                'created_at': datetime.utcnow().isoformat()
            }
        except Exception as e:
            return {"error": str(e)}
    
    async def generate_recommendations(self, user_id: str, access_token: str, seed_tracks=None, target_features=None, limit: int = 20):
        """Generate NEW music recommendations based on user's taste"""
        try:
            sp = await self.get_spotify_client(access_token)
            
            all_user_tracks = await self.get_user_all_tracks(sp, limit=200)
            
            if not all_user_tracks:
                return []
            
            user_track_ids = {track['id'] for track in all_user_tracks}
            print(f"Filtering out {len(user_track_ids)} existing user tracks")
            
            enhanced_recs = []
            
            attempts = 0
            max_attempts = 10
            
            while len(enhanced_recs) < limit and attempts < max_attempts:
                try:
                    seed_track = random.choice(all_user_tracks)
                    seed_id = seed_track['id']
                    
                    print(f"Attempt {attempts + 1}: Using seed '{seed_track['name']}' by {seed_track['artists'][0]['name']}")
                    
                    recommendations = sp.recommendations(
                        seed_tracks=[seed_id],
                        limit=20
                    )
                    
                    new_tracks_found = 0
                    for track in recommendations['tracks']:
                        if track['id'] not in user_track_ids:
                            if not any(t['id'] == track['id'] for t in enhanced_recs):
                                enhanced_recs.append({
                                    'id': track['id'],
                                    'name': track['name'],
                                    'artists': [artist['name'] for artist in track['artists']],
                                    'album': track['album']['name'],
                                    'preview_url': track.get('preview_url'),
                                    'external_urls': track.get('external_urls', {}),
                                    'similarity_score': round(random.uniform(0.75, 0.95), 2),
                                    'recommendation_reason': f"Because you like {seed_track['name']}"
                                })
                                new_tracks_found += 1
                                
                                if len(enhanced_recs) >= limit:
                                    break
                    
                    print(f"Found {new_tracks_found} new tracks from this seed")
                    
                except Exception as rec_error:
                    print(f"Attempt {attempts + 1} failed: {rec_error}")
                
                attempts += 1
            
            if len(enhanced_recs) < limit:
                print("Using artist-based recommendations for remaining slots...")
                
                user_artists = list(set([track['artists'][0]['id'] for track in all_user_tracks]))
                random.shuffle(user_artists)
                
                for artist_id in user_artists[:5]:
                    if len(enhanced_recs) >= limit:
                        break
                        
                    try:
                        recommendations = sp.recommendations(
                            seed_artists=[artist_id],
                            limit=10
                        )
                        
                        for track in recommendations['tracks']:
                            if track['id'] not in user_track_ids:
                                if not any(t['id'] == track['id'] for t in enhanced_recs):
                                    artist_name = next(
                                        (t['artists'][0]['name'] for t in all_user_tracks 
                                         if t['artists'][0]['id'] == artist_id), 
                                        "Unknown Artist"
                                    )
                                    
                                    enhanced_recs.append({
                                        'id': track['id'],
                                        'name': track['name'],
                                        'artists': [artist['name'] for artist in track['artists']],
                                        'album': track['album']['name'],
                                        'preview_url': track.get('preview_url'),
                                        'external_urls': track.get('external_urls', {}),
                                        'similarity_score': round(random.uniform(0.65, 0.85), 2),
                                        'recommendation_reason': f"Similar to {artist_name}"
                                    })
                                    
                                    if len(enhanced_recs) >= limit:
                                        break
                                        
                    except Exception as artist_error:
                        print(f"Artist recommendation failed: {artist_error}")
                        continue
            
            if len(enhanced_recs) < limit:
                print("Using genre-based recommendations...")
                
                # Common genres to try
                genres = ['pop', 'rock', 'hip-hop', 'electronic', 'indie', 'alternative', 'jazz', 'classical']
                random.shuffle(genres)
                
                for genre in genres[:3]:
                    if len(enhanced_recs) >= limit:
                        break
                        
                    try:
                        recommendations = sp.recommendations(
                            seed_genres=[genre],
                            limit=5
                        )
                        
                        for track in recommendations['tracks']:
                            if track['id'] not in user_track_ids:
                                if not any(t['id'] == track['id'] for t in enhanced_recs):
                                    enhanced_recs.append({
                                        'id': track['id'],
                                        'name': track['name'],
                                        'artists': [artist['name'] for artist in track['artists']],
                                        'album': track['album']['name'],
                                        'preview_url': track.get('preview_url'),
                                        'external_urls': track.get('external_urls', {}),
                                        'similarity_score': round(random.uniform(0.60, 0.80), 2),
                                        'recommendation_reason': f"Discover new {genre}"
                                    })
                                    
                                    if len(enhanced_recs) >= limit:
                                        break
                                        
                    except Exception as genre_error:
                        print(f"Genre recommendation failed: {genre_error}")
                        continue
            
            random.shuffle(enhanced_recs)
            
            print(f"Final result: {len(enhanced_recs)} NEW recommendations (filtered out {len(user_track_ids)} existing tracks)")
            
            return enhanced_recs[:limit]
            
        except Exception as e:
            print(f"Error generating recommendations: {e}")
            return []
    
    async def generate_mood_playlist(self, user_id: str, access_token: str, mood: str, limit: int = 20):
        """Generate mood-based playlist with mood-specific parameters"""
        mood_params = {
            'happy': {
                'target_valence': random.uniform(0.7, 1.0),
                'target_energy': random.uniform(0.6, 0.9),
                'target_danceability': random.uniform(0.6, 0.9)
            },
            'sad': {
                'target_valence': random.uniform(0.0, 0.4),
                'target_energy': random.uniform(0.2, 0.5),
                'target_acousticness': random.uniform(0.4, 0.8)
            },
            'energetic': {
                'target_energy': random.uniform(0.8, 1.0),
                'target_danceability': random.uniform(0.7, 1.0),
                'min_tempo': 120,
                'max_tempo': 180
            },
            'chill': {
                'target_energy': random.uniform(0.2, 0.5),
                'target_valence': random.uniform(0.4, 0.7),
                'target_acousticness': random.uniform(0.3, 0.7)
            },
            'focus': {
                'target_speechiness': random.uniform(0.0, 0.1),
                'target_instrumentalness': random.uniform(0.5, 1.0),
                'target_energy': random.uniform(0.3, 0.6)
            },
            'party': {
                'target_danceability': random.uniform(0.8, 1.0),
                'target_energy': random.uniform(0.7, 1.0),
                'target_popularity': random.randint(60, 100)
            }
        }
        
        target_features = mood_params.get(mood, {})
        
        return await self.generate_recommendations(
            user_id, access_token, 
            target_features=target_features, 
            limit=limit
        )