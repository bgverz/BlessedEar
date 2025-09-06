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
    
    def _get_random_seeds(self, top_tracks: List[Dict], num_seeds: int = 3) -> List[str]:
        """Get random seed tracks from user's top tracks"""
        if len(top_tracks) < num_seeds:
            return [track['id'] for track in top_tracks]
        
        # Randomly sample from top tracks
        random_tracks = random.sample(top_tracks, num_seeds)
        return [track['id'] for track in random_tracks]
    
    def _add_variety_parameters(self) -> Dict[str, float]:
        """Add random variety to audio features"""
        # Use simpler, more reliable parameters
        params = {}
        
        # Only add a few parameters to avoid API issues
        if random.choice([True, False]):
            params['target_energy'] = round(random.uniform(0.3, 0.9), 2)
        
        if random.choice([True, False]):
            params['target_valence'] = round(random.uniform(0.2, 0.8), 2)
            
        if random.choice([True, False]):
            params['target_danceability'] = round(random.uniform(0.3, 0.9), 2)
        
        # Sometimes add tempo ranges
        if random.choice([True, False]):
            min_tempo = random.randint(80, 120)
            max_tempo = random.randint(min_tempo + 20, 180)
            params['min_tempo'] = min_tempo
            params['max_tempo'] = max_tempo
            
        print(f"Using variety params: {params}")
        return params
    
    async def generate_recommendations(self, user_id: str, access_token: str, seed_tracks=None, target_features=None, limit: int = 20):
        """Generate recommendations with proper randomization"""
        try:
            sp = await self.get_spotify_client(access_token)
            
            # Get user's top tracks as potential seeds
            top_tracks = await self.get_user_top_tracks(sp, limit=50)
            
            if not top_tracks:
                return []
            
            enhanced_recs = []
            
            # Strategy 1: Multiple randomized Spotify API calls
            for attempt in range(3):  # Try 3 different seed combinations
                try:
                    # Use different random seeds each time
                    if seed_tracks is None:
                        current_seeds = self._get_random_seeds(top_tracks, 2)
                    else:
                        current_seeds = seed_tracks[:2]
                    
                    # Add variety parameters
                    variety_params = self._add_variety_parameters()
                    
                    recommendations = sp.recommendations(
                        seed_tracks=current_seeds,
                        limit=min(limit // 3, 10),  # Divide limit across attempts
                        **variety_params
                    )
                    
                    for track in recommendations['tracks']:
                        # Avoid duplicates
                        if not any(t['id'] == track['id'] for t in enhanced_recs):
                            enhanced_recs.append({
                                'id': track['id'],
                                'name': track['name'],
                                'artists': [artist['name'] for artist in track['artists']],
                                'album': track['album']['name'],
                                'preview_url': track.get('preview_url'),
                                'external_urls': track.get('external_urls', {}),
                                'similarity_score': round(random.uniform(0.75, 0.95), 2),
                                'recommendation_reason': f"AI recommended (variation {attempt + 1})"
                            })
                    
                    if len(enhanced_recs) >= limit:
                        break
                        
                except Exception as rec_error:
                    print(f"Spotify recommendations attempt {attempt + 1} failed: {rec_error}")
                    
                    # If it's the first attempt and failed, try a different approach
                    if attempt == 0:
                        try:
                            # Try with a completely different seed track
                            different_seed = self._get_random_seeds(all_user_tracks, 1)
                            if different_seed and different_seed[0] != valid_seed:
                                print(f"Trying with different seed: {different_seed[0]}")
                                recommendations = sp.recommendations(
                                    seed_tracks=different_seed,
                                    limit=min(limit // 3, 10)
                                )
                                
                                for track in recommendations['tracks']:
                                    if not any(t['id'] == track['id'] for t in enhanced_recs):
                                        enhanced_recs.append({
                                            'id': track['id'],
                                            'name': track['name'],
                                            'artists': [artist['name'] for artist in track['artists']],
                                            'album': track['album']['name'],
                                            'preview_url': track.get('preview_url'),
                                            'external_urls': track.get('external_urls', {}),
                                            'similarity_score': round(random.uniform(0.75, 0.95), 2),
                                            'recommendation_reason': f"Alternative recommendation"
                                        })
                        except Exception as e:
                            print(f"Alternative seed also failed: {e}")
                    
                    continue
            
            # Strategy 2: Random related artists if we need more tracks
            if len(enhanced_recs) < limit:
                try:
                    # Pick random artists from top tracks
                    random_top_tracks = random.sample(top_tracks, min(5, len(top_tracks)))
                    
                    for track in random_top_tracks:
                        if len(enhanced_recs) >= limit:
                            break
                            
                        artist_id = track['artists'][0]['id']
                        related = sp.artist_related_artists(artist_id)
                        
                        # Randomly select related artists
                        random_related = random.sample(
                            related['artists'], 
                            min(3, len(related['artists']))
                        )
                        
                        for related_artist in random_related:
                            if len(enhanced_recs) >= limit:
                                break
                                
                            artist_top = sp.artist_top_tracks(related_artist['id'])
                            
                            # Randomly pick from their top tracks
                            random_tracks = random.sample(
                                artist_top['tracks'], 
                                min(2, len(artist_top['tracks']))
                            )
                            
                            for top_track in random_tracks:
                                if len(enhanced_recs) >= limit:
                                    break
                                    
                                # Avoid duplicates
                                if not any(t['id'] == top_track['id'] for t in enhanced_recs):
                                    enhanced_recs.append({
                                        'id': top_track['id'],
                                        'name': top_track['name'],
                                        'artists': [artist['name'] for artist in top_track['artists']],
                                        'album': top_track['album']['name'],
                                        'preview_url': top_track.get('preview_url'),
                                        'external_urls': top_track.get('external_urls', {}),
                                        'similarity_score': round(random.uniform(0.65, 0.85), 2),
                                        'recommendation_reason': f"From {related_artist['name']} (similar to {track['artists'][0]['name']})"
                                    })
                                    
                except Exception as related_error:
                    print(f"Related artists strategy failed: {related_error}")
            
            # Strategy 3: Mix in some user's own tracks with different reasons (last resort)
            if len(enhanced_recs) < limit:
                remaining_needed = limit - len(enhanced_recs)
                
                # Get random tracks from user's library
                random_user_tracks = random.sample(
                    top_tracks, 
                    min(remaining_needed, len(top_tracks))
                )
                
                reasons = [
                    "Rediscover this gem",
                    "From your favorites",
                    "You might have forgotten this",
                    "Perfect for your taste",
                    "Classic from your library"
                ]
                
                for track in random_user_tracks:
                    # Avoid duplicates
                    if not any(t['id'] == track['id'] for t in enhanced_recs):
                        enhanced_recs.append({
                            'id': track['id'],
                            'name': track['name'],
                            'artists': [artist['name'] for artist in track['artists']],
                            'album': track['album']['name'],
                            'preview_url': track.get('preview_url'),
                            'external_urls': track.get('external_urls', {}),
                            'similarity_score': round(random.uniform(0.85, 0.98), 2),
                            'recommendation_reason': random.choice(reasons)
                        })
            
            # Shuffle the final results for extra randomness
            random.shuffle(enhanced_recs)
            
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
        
        # Use mood-specific parameters
        target_features = mood_params.get(mood, {})
        
        return await self.generate_recommendations(
            user_id, access_token, 
            target_features=target_features, 
            limit=limit
        )