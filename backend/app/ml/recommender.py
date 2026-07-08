import spotipy
import random
from typing import List, Dict, Any
from collections import defaultdict

from app.ml.analytics_engine import AnalyticsEngine

# Spotify's genre seeds, used as a curated pool for genre-discovery search
AVAILABLE_GENRES = [
    'acoustic', 'afrobeat', 'alt-rock', 'alternative', 'ambient',
    'blues', 'bossanova', 'brazil', 'breakbeat', 'british',
    'chill', 'classical', 'club', 'country', 'dance',
    'electronic', 'folk', 'funk', 'garage', 'gospel',
    'hip-hop', 'house', 'indie', 'jazz', 'latin',
    'pop', 'punk', 'reggae', 'rock', 'soul'
]

def score_from_strength(strength: float, floor: float = 0.55, spread: float = 0.4) -> float:
    """Turn a real 0-1 signal (e.g. normalized artist frequency) into a similarity score"""
    strength = max(0.0, min(1.0, strength))
    return round(floor + spread * strength, 2)

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

    async def get_user_top_tracks(self, sp: spotipy.Spotify, time_range: str = "medium_term", limit: int = 50):
        """Get user's top tracks"""
        try:
            results = sp.current_user_top_tracks(time_range=time_range, limit=limit)
            return results['items']
        except Exception as e:
            print(f"Error getting top tracks: {e}")
            return []
    
    async def get_user_all_tracks(self, sp: spotipy.Spotify, limit: int = 2000):
        """Get tracks from user's library, playlists, and top tracks with pagination"""
        all_tracks = []
        
        try:
            print("Fetching top tracks...")
            for time_range in ['short_term', 'medium_term', 'long_term']:
                top_tracks = await self.get_user_top_tracks(sp, time_range, 50)
                all_tracks.extend(top_tracks)
                print(f"Added {len(top_tracks)} {time_range} top tracks")
            
            print("Fetching saved tracks...")
            offset = 0
            while len(all_tracks) < limit:
                try:
                    saved_batch = sp.current_user_saved_tracks(limit=50, offset=offset)
                    if not saved_batch['items']:
                        break
                        
                    for item in saved_batch['items']:
                        if item['track'] and item['track']['id']:
                            all_tracks.append(item['track'])
                    
                    print(f"Added {len(saved_batch['items'])} saved tracks (offset: {offset})")
                    
                    if len(saved_batch['items']) < 50:
                        break
                        
                    offset += 50
                    
                except Exception as e:
                    print(f"Error getting saved tracks at offset {offset}: {e}")
                    break
            
            print("Fetching playlist tracks...")
            user_id = sp.me()['id']
            
            playlist_offset = 0
            all_playlists = []
            
            while True:
                try:
                    playlist_batch = sp.current_user_playlists(limit=50, offset=playlist_offset)
                    if not playlist_batch['items']:
                        break
                        
                    all_playlists.extend(playlist_batch['items'])
                    
                    if len(playlist_batch['items']) < 50:
                        break
                        
                    playlist_offset += 50
                    
                except Exception as e:
                    print(f"Error getting playlists at offset {playlist_offset}: {e}")
                    break
            
            print(f"Found {len(all_playlists)} total playlists")
            
            for i, playlist in enumerate(all_playlists):
                if len(all_tracks) >= limit:
                    break
                    
                if playlist['owner']['id'] != user_id:
                    continue
                    
                print(f"Processing playlist {i+1}/{len(all_playlists)}: {playlist['name']}")
                
                track_offset = 0
                playlist_track_count = 0
                
                while len(all_tracks) < limit:
                    try:
                        track_batch = sp.playlist_tracks(
                            playlist['id'], 
                            limit=100,
                            offset=track_offset
                        )
                        
                        if not track_batch['items']:
                            break
                        
                        for item in track_batch['items']:
                            if item['track'] and item['track']['id']:
                                all_tracks.append(item['track'])
                                playlist_track_count += 1
                        
                        if len(track_batch['items']) < 100:
                            break
                            
                        track_offset += 100
                        
                    except Exception as e:
                        print(f"Error getting tracks from playlist {playlist['name']}: {e}")
                        break
                
                print(f"Added {playlist_track_count} tracks from '{playlist['name']}'")
            
            print("Fetching recently played tracks...")
            try:
                recent_tracks = sp.current_user_recently_played(limit=50)
                for item in recent_tracks['items']:
                    if item['track'] and item['track']['id']:
                        all_tracks.append(item['track'])
                print(f"Added {len(recent_tracks['items'])} recently played tracks")
            except Exception as e:
                print(f"Error getting recently played tracks: {e}")
            
            print("Removing duplicates...")
            unique_tracks = []
            seen_ids = set()
            
            for track in all_tracks:
                if track and track.get('id') and track['id'] not in seen_ids:
                    seen_ids.add(track['id'])
                    unique_tracks.append(track)
            
            print(f"Total tracks before deduplication: {len(all_tracks)}")
            print(f"Total unique tracks collected: {len(unique_tracks)}")
            
            random.shuffle(unique_tracks)
            return unique_tracks[:limit]
            
        except Exception as e:
            print(f"Error in get_user_all_tracks: {e}")
            return await self.get_user_top_tracks(sp, "medium_term", 50)
    
    
    async def get_artist_similar_tracks(self, sp: spotipy.Spotify, artist_id: str, limit: int = 10, strength: float = 0.75):
        """Get other tracks by the same artist. `strength` (0-1) should reflect how strongly
        this artist features in the user's listening (e.g. normalized play frequency)."""
        try:
            albums = sp.artist_albums(artist_id, album_type='album,single', limit=10)
            similar_tracks = []

            for album in albums['items']:
                try:
                    tracks = sp.album_tracks(album['id'], limit=10)
                    for track in tracks['items']:
                        similar_tracks.append({
                            'id': track['id'],
                            'name': track['name'],
                            'artists': [artist['name'] for artist in track['artists']],
                            'album': album['name'],
                            'album_images': track.get('album', {}).get('images', []),
                            'preview_url': track.get('preview_url'),
                            'external_urls': track.get('external_urls', {}),
                            'similarity_score': score_from_strength(strength, floor=0.6, spread=0.35),
                            'recommendation_reason': f"More from {track['artists'][0]['name']}"
                        })
                        
                        if len(similar_tracks) >= limit:
                            break
                            
                    if len(similar_tracks) >= limit:
                        break
                        
                except Exception as album_error:
                    print(f"Error getting tracks from album {album['name']}: {album_error}")
                    continue
                    
            return similar_tracks[:limit]
            
        except Exception as e:
            print(f"Error getting artist similar tracks: {e}")
            return []
    
    async def get_album_deep_cuts(self, sp: spotipy.Spotify, album_id: str, exclude_track_ids: set, limit: int = 5, strength: float = 0.6):
        """Get other tracks from the same album. `strength` (0-1) should reflect how strongly
        this album features in the user's listening (e.g. normalized play frequency)."""
        try:
            tracks = sp.album_tracks(album_id, limit=50)
            deep_cuts = []

            for track in tracks['items']:
                if track['id'] not in exclude_track_ids:
                    album_info = sp.album(album_id)
                    deep_cuts.append({
                        'id': track['id'],
                        'name': track['name'],
                        'artists': [artist['name'] for artist in track['artists']],
                        'album': album_info['name'],
                        'album_images': track.get('album', {}).get('images', []),
                        'preview_url': track.get('preview_url'),
                        'external_urls': track.get('external_urls', {}),
                        'similarity_score': score_from_strength(strength, floor=0.5, spread=0.35),
                        'recommendation_reason': f"From {album_info['name']}"
                    })
                    
                    if len(deep_cuts) >= limit:
                        break
            
            return deep_cuts
            
        except Exception as e:
            print(f"Error getting album deep cuts: {e}")
            return []
    
    async def get_artist_top_tracks_discovery(self, sp: spotipy.Spotify, artist_id: str, exclude_track_ids: set, limit: int = 3, strength: float = 0.65):
        """Get top tracks from an artist (excluding already known tracks). `strength` (0-1) should
        reflect how strongly this artist features in the user's listening."""
        try:
            top_tracks = sp.artist_top_tracks(artist_id)
            discoveries = []

            for track in top_tracks['tracks']:
                if track['id'] not in exclude_track_ids:
                    discoveries.append({
                        'id': track['id'],
                        'name': track['name'],
                        'artists': [artist['name'] for artist in track['artists']],
                        'album': track['album']['name'],
                        'preview_url': track.get('preview_url'),
                        'external_urls': track.get('external_urls', {}),
                        'similarity_score': score_from_strength(strength, floor=0.55, spread=0.3),
                        'recommendation_reason': f"Popular track by {track['artists'][0]['name']}"
                    })
                    
                    if len(discoveries) >= limit:
                        break
            
            return discoveries
            
        except Exception as e:
            print(f"Error getting artist top tracks: {e}")
            return []
    
    async def generate_recommendations(self, user_id: str, access_token: str, seed_tracks=None, target_features=None, limit: int = 20):
        """Generate recommendations using only working APIs - POLISHED VERSION"""
        try:
            sp = await self.get_spotify_client(access_token)
            
            print(f"Starting recommendation generation for user: {user_id}")
            
            all_user_tracks = await self.get_user_all_tracks(sp, limit=150)
            
            if not all_user_tracks:
                print("No user tracks found, cannot generate recommendations")
                return []
            
            user_track_ids = {track['id'] for track in all_user_tracks}
            enhanced_recs = []
            
            artist_frequency = defaultdict(int)
            album_frequency = defaultdict(int)
            
            for track in all_user_tracks:
                for artist in track.get('artists', []):
                    artist_frequency[artist['id']] += 1
                if track.get('album', {}).get('id'):
                    album_frequency[track['album']['id']] += 1
            
            favorite_artists = sorted(artist_frequency.items(), key=lambda x: x[1], reverse=True)
            favorite_albums = sorted(album_frequency.items(), key=lambda x: x[1], reverse=True)

            max_artist_freq = favorite_artists[0][1] if favorite_artists else 1
            max_album_freq = favorite_albums[0][1] if favorite_albums else 1

            print(f"Found {len(favorite_artists)} favorite artists")

            print("Getting deep cuts from favorite artists...")
            for artist_id, frequency in favorite_artists[:15]:
                if len(enhanced_recs) >= limit:
                    break

                strength = frequency / max_artist_freq
                artist_tracks = await self.get_artist_similar_tracks(sp, artist_id, 8, strength=strength)

                new_tracks = [t for t in artist_tracks if t['id'] not in user_track_ids]

                selected_tracks = new_tracks[:3] if frequency > 3 else new_tracks[:2]
                enhanced_recs.extend(selected_tracks)

                for track in selected_tracks:
                    user_track_ids.add(track['id'])

            print(f"Found {len(enhanced_recs)} tracks from artist deep dives")

            if len(enhanced_recs) < limit:
                print("Getting deep cuts from favorite albums...")
                for album_id, frequency in favorite_albums[:10]:
                    if len(enhanced_recs) >= limit:
                        break

                    strength = frequency / max_album_freq
                    album_tracks = await self.get_album_deep_cuts(sp, album_id, user_track_ids, 3, strength=strength)

                    for track in album_tracks:
                        if len(enhanced_recs) >= limit:
                            break
                        if track['id'] not in user_track_ids:
                            enhanced_recs.append(track)
                            user_track_ids.add(track['id'])

            print(f"Found {len(enhanced_recs)} total tracks after album deep cuts")

            if len(enhanced_recs) < limit:
                print("Getting popular tracks from known artists...")
                for artist_id, frequency in favorite_artists[:20]:
                    if len(enhanced_recs) >= limit:
                        break

                    strength = frequency / max_artist_freq
                    popular_tracks = await self.get_artist_top_tracks_discovery(sp, artist_id, user_track_ids, 2, strength=strength)

                    for track in popular_tracks:
                        if len(enhanced_recs) >= limit:
                            break
                        if track['id'] not in user_track_ids:
                            enhanced_recs.append(track)
                            user_track_ids.add(track['id'])
            
            print(f"Found {len(enhanced_recs)} total tracks after popular track discovery")
            
            if len(enhanced_recs) < limit:
                print("Using collaborative discovery...")
                
                sample_tracks = random.sample(all_user_tracks, min(10, len(all_user_tracks)))
                
                for track in sample_tracks:
                    if len(enhanced_recs) >= limit:
                        break
                        
                    album_id = track.get('album', {}).get('id')
                    if album_id:
                        try:
                            album_info = sp.album(album_id)
                            if album_info.get('album_type') == 'compilation':
                                compilation_tracks = await self.get_album_deep_cuts(sp, album_id, user_track_ids, 4)
                                
                                for comp_track in compilation_tracks:
                                    if len(enhanced_recs) >= limit:
                                        break
                                    if comp_track['id'] not in user_track_ids:
                                        comp_track['recommendation_reason'] = f"From compilation: {album_info['name']}"
                                        enhanced_recs.append(comp_track)
                                        user_track_ids.add(comp_track['id'])
                                        
                        except Exception as e:
                            continue
            
            random.shuffle(enhanced_recs)
            
            final_recs = []
            reason_counts = defaultdict(int)
            
            for track in enhanced_recs:
                reason_type = track['recommendation_reason'].split(' ')[0]
                if reason_counts[reason_type] < limit // 3:
                    final_recs.append(track)
                    reason_counts[reason_type] += 1
                    
                if len(final_recs) >= limit:
                    break
            
            remaining_spots = limit - len(final_recs)
            if remaining_spots > 0:
                remaining_tracks = [t for t in enhanced_recs if t not in final_recs]
                final_recs.extend(remaining_tracks[:remaining_spots])
            
            print(f"Final result: {len(final_recs)} real track recommendations generated")
            return final_recs[:limit]
            
        except Exception as e:
            print(f"Error generating recommendations: {e}")
            return []
    
    async def generate_mood_playlist(self, user_id: str, access_token: str, mood: str, limit: int = 20):
        """Generate mood-based playlist using user's existing tracks"""
        try:
            sp = await self.get_spotify_client(access_token)
            all_user_tracks = await self.get_user_all_tracks(sp, limit=100)
            
            if not all_user_tracks:
                return []
            
            mood_keywords = {
                'happy': ['love', 'happy', 'good', 'feel', 'dance', 'party', 'sun', 'bright', 'joy', 'smile', 'fun'],
                'sad': ['sad', 'cry', 'alone', 'broken', 'hurt', 'miss', 'lost', 'tear', 'rain', 'blue', 'lonely'],
                'energetic': ['run', 'fire', 'energy', 'power', 'rock', 'electric', 'pump', 'wild', 'intense', 'drive'],
                'chill': ['chill', 'calm', 'slow', 'smooth', 'relax', 'soft', 'dream', 'float', 'easy', 'mellow'],
                'focus': ['focus', 'ambient', 'instrumental', 'study', 'concentrate', 'mind', 'think', 'clear'],
                'party': ['party', 'dance', 'club', 'beat', 'bass', 'pump', 'turn', 'up', 'wild', 'night']
            }
            
            keywords = mood_keywords.get(mood, ['music'])
            mood_tracks = []
            
            for track in all_user_tracks:
                track_name = track['name'].lower()
                artists = ' '.join([a['name'].lower() for a in track.get('artists', [])])
                album_name = track.get('album', {}).get('name', '').lower()
                
                text_to_search = f"{track_name} {artists} {album_name}"
                
                score = sum(1 for keyword in keywords if keyword in text_to_search)
                
                if score > 0:
                    mood_tracks.append((track, score))
            
            mood_tracks.sort(key=lambda x: x[1], reverse=True)
            max_keyword_score = len(keywords) or 1

            if mood_tracks:
                selected_tracks = [track for track, score in mood_tracks[:limit]]
                keyword_scores = {track['id']: score for track, score in mood_tracks[:limit]}
            else:
                selected_tracks = random.sample(all_user_tracks, min(limit, len(all_user_tracks)))
                keyword_scores = {}

            enhanced_recs = []
            for track in selected_tracks:
                keyword_score = keyword_scores.get(track['id'])
                if keyword_score:
                    similarity_score = score_from_strength(keyword_score / max_keyword_score, floor=0.6, spread=0.35)
                    reason = f'Perfect for {mood} mood'
                else:
                    similarity_score = 0.5
                    reason = 'From your library'
                enhanced_recs.append({
                    'id': track['id'],
                    'name': track['name'],
                    'artists': [artist['name'] for artist in track['artists']],
                    'album': track['album']['name'],
                    'preview_url': track.get('preview_url'),
                    'external_urls': track.get('external_urls', {}),
                    'similarity_score': similarity_score,
                    'recommendation_reason': reason
                })

            if len(enhanced_recs) < limit:
                user_track_ids = {track['id'] for track in selected_tracks}
                remaining_needed = limit - len(enhanced_recs)

                for track in selected_tracks[:5]:
                    if len(enhanced_recs) >= limit:
                        break

                    for artist in track.get('artists', []):
                        artist_id = artist.get('id')
                        if artist_id:
                            additional_tracks = await self.get_artist_similar_tracks(sp, artist_id, 3, strength=0.5)
                            
                            for add_track in additional_tracks:
                                if len(enhanced_recs) >= limit:
                                    break
                                if add_track['id'] not in user_track_ids:
                                    add_track['recommendation_reason'] = f'More {mood} vibes from {artist["name"]}'
                                    enhanced_recs.append(add_track)
                                    user_track_ids.add(add_track['id'])
            
            random.shuffle(enhanced_recs)
            print(f"Generated {len(enhanced_recs)} tracks for {mood} mood")
            return enhanced_recs[:limit]

        except Exception as e:
            print(f"Error generating mood playlist: {e}")
            return []

    async def get_genre_discovery_tracks(self, sp: spotipy.Spotify, exclude_genres: set, user_track_ids: set, limit: int = 12):
        """Surface tracks from genres the user doesn't already listen to, via Spotify search
        (the old seed-genre recommendations endpoint is deprecated, but search still works)"""
        candidate_genres = [g for g in AVAILABLE_GENRES if g not in exclude_genres]
        random.shuffle(candidate_genres)

        discoveries = []
        for genre in candidate_genres:
            if len(discoveries) >= limit:
                break
            try:
                results = sp.search(q=f'genre:"{genre}"', type='track', limit=10, market='US')
                tracks = results.get('tracks', {}).get('items', [])
                tracks.sort(key=lambda t: t.get('popularity', 0), reverse=True)

                added_for_genre = 0
                for track in tracks:
                    if added_for_genre >= 2 or len(discoveries) >= limit:
                        break
                    if track['id'] in user_track_ids:
                        continue

                    discoveries.append({
                        'id': track['id'],
                        'name': track['name'],
                        'artists': [artist['name'] for artist in track['artists']],
                        'album': track['album']['name'],
                        'album_images': track.get('album', {}).get('images', []),
                        'preview_url': track.get('preview_url'),
                        'external_urls': track.get('external_urls', {}),
                        'similarity_score': round(min(track.get('popularity', 50) / 100, 0.95), 2),
                        'recommendation_reason': f"New genre for you: {genre}"
                    })
                    user_track_ids.add(track['id'])
                    added_for_genre += 1

            except Exception as e:
                print(f"Error searching genre {genre}: {e}")
                continue

        return discoveries[:limit]

    async def generate_genre_discovery(self, user_id: str, access_token: str, limit: int = 12):
        """Generate a playlist of tracks from genres outside the user's current listening"""
        try:
            sp = await self.get_spotify_client(access_token)
            all_user_tracks = await self.get_user_all_tracks(sp, limit=150)

            if not all_user_tracks:
                return []

            user_track_ids = {t['id'] for t in all_user_tracks if t.get('id')}

            analytics = AnalyticsEngine()
            artist_ids = analytics._artist_ids_from_tracks(all_user_tracks)
            artists_by_id = analytics._fetch_artists(sp, artist_ids)
            genre_breakdown = analytics._genre_breakdown(all_user_tracks, artists_by_id)
            known_genres = {g['genre'] for g in genre_breakdown}

            return await self.get_genre_discovery_tracks(sp, known_genres, user_track_ids, limit)

        except Exception as e:
            print(f"Error generating genre discovery: {e}")
            return []