import asyncio
import json
import spotipy
import pandas as pd
import random
import logging
from typing import List, Dict, Any, Set, Optional
from datetime import datetime, timezone
from collections import defaultdict

from app.core.database import get_cache, set_cache

logger = logging.getLogger(__name__)

MOOD_TARGETS: Dict[str, Dict[str, float]] = {
    'happy':     {'target_valence': 0.80, 'target_energy': 0.70, 'min_valence': 0.55},
    'sad':       {'target_valence': 0.20, 'target_energy': 0.30, 'max_valence': 0.45},
    'energetic': {'target_energy': 0.85, 'target_danceability': 0.80, 'min_energy': 0.65},
    'chill':     {'target_energy': 0.30, 'target_acousticness': 0.60, 'max_energy': 0.55},
    'focus':     {'target_instrumentalness': 0.50, 'target_energy': 0.45, 'max_speechiness': 0.15},
    'party':     {'target_danceability': 0.85, 'target_energy': 0.85, 'min_danceability': 0.70},
}

_AUDIO_FEATURE_COLS = [
    'danceability', 'energy', 'valence', 'speechiness',
    'acousticness', 'instrumentalness', 'liveness', 'tempo',
]

_REC_HISTORY_MAX = 500
_REC_HISTORY_TTL = 604800
_LIBRARY_CACHE_TTL = 1800


class RecommendationEngine:
    def __init__(self):
        self.is_initialized = False

    async def load_models(self):
        """Initialize the recommendation engine."""
        self.is_initialized = True
        logger.info("Recommendation engine initialized")

    async def get_spotify_client(self, access_token: str) -> spotipy.Spotify:
        """Return an authenticated Spotify client."""
        return spotipy.Spotify(auth=access_token)

    async def _spotify_call_with_timeout(
        self,
        func,
        *args,
        timeout_seconds: float = 6.0,
        call_name: str = "spotify_call",
        **kwargs,
    ):
        """
        Run a blocking Spotipy call in a worker thread with a hard timeout.
        """
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(func, *args, **kwargs),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "Spotify call timed out after %.1fs: %s",
                timeout_seconds,
                call_name,
            )
            raise

    @staticmethod
    def _select_album_image_url(album_images: Optional[List[Dict[str, Any]]]) -> Optional[str]:
        """
        Pick a stable album thumbnail URL, preferring ~300px then ~64px.
        """
        if not album_images:
            return None

        valid_images = [img for img in album_images if isinstance(img, dict) and img.get("url")]
        if not valid_images:
            return None

        by_300 = sorted(valid_images, key=lambda img: abs((img.get("width") or 300) - 300))
        if by_300:
            return by_300[0].get("url")

        return valid_images[0].get("url")


    async def extract_audio_features(self, sp: spotipy.Spotify, track_ids: List[str]) -> pd.DataFrame:
        """
        Fetch real audio features from Spotify in batches of 100.

        Error handling per batch:
          401 → raised immediately (caller should refresh token and retry)
          403 → Spotify has restricted this API for the app; abort all batches
          429 → respect Retry-After header, retry the batch once
          other → log and skip the batch (do not crash the full run)

        Logs: total IDs requested, batch count, per-batch success/failure.
        """
        if not track_ids:
            return pd.DataFrame()

        valid_ids = [tid for tid in track_ids if tid]
        total = len(valid_ids)
        batch_count = (total + 99) // 100
        logger.info(
            "Audio features: requesting %d track IDs in %d batch(es)",
            total, batch_count,
        )

        all_features: List[Dict] = []
        success_batches = 0
        fail_batches = 0

        for i in range(0, total, 100):
            batch = valid_ids[i:i + 100]
            batch_num = i // 100

            try:
                features = sp.audio_features(batch)
                if features:
                    all_features.extend(f for f in features if f is not None)
                success_batches += 1

            except spotipy.SpotifyException as exc:
                if exc.http_status == 401:
                    logger.warning(
                        "Audio features batch %d: 401 Unauthorized — raising for token refresh",
                        batch_num,
                    )
                    raise

                elif exc.http_status == 403:
                    logger.warning(
                        "Audio features batch %d: 403 Forbidden — "
                        "Spotify has restricted the audio-features API for this app "
                        "(deprecated for apps created after 2024). "
                        "First 3 IDs: %s",
                        batch_num, batch[:3],
                    )
                    fail_batches += 1
                    break

                elif exc.http_status == 429:
                    retry_after = 2
                    if exc.headers:
                        try:
                            retry_after = int(exc.headers.get("Retry-After", 2))
                        except (ValueError, TypeError):
                            pass
                    logger.warning(
                        "Audio features batch %d: 429 rate-limited, waiting %ds",
                        batch_num, retry_after,
                    )
                    await asyncio.sleep(retry_after)
                    try:
                        features = sp.audio_features(batch)
                        if features:
                            all_features.extend(f for f in features if f is not None)
                        success_batches += 1
                    except Exception as retry_exc:
                        logger.warning(
                            "Audio features batch %d: retry failed: %s", batch_num, retry_exc
                        )
                        fail_batches += 1

                else:
                    logger.warning(
                        "Audio features batch %d: HTTP %d — first 3 IDs: %s",
                        batch_num, exc.http_status, batch[:3],
                    )
                    fail_batches += 1

            except Exception as exc:
                logger.warning(
                    "Audio features batch %d: unexpected error (size=%d, first 3 IDs: %s): %s",
                    batch_num, len(batch), batch[:3], exc,
                )
                fail_batches += 1

        logger.info(
            "Audio features done: %d successful batches, %d failed, %d features fetched",
            success_batches, fail_batches, len(all_features),
        )

        if not all_features:
            return pd.DataFrame()

        return pd.DataFrame(all_features)

    async def get_user_top_tracks(self, sp: spotipy.Spotify, time_range: str = "medium_term", limit: int = 50):
        """Get user's top tracks for a given time range."""
        try:
            results = await self._spotify_call_with_timeout(
                sp.current_user_top_tracks,
                time_range=time_range,
                limit=min(limit, 50),
                timeout_seconds=10.0,
                call_name=f"current_user_top_tracks[{time_range}]",
            )
            return results['items']
        except asyncio.TimeoutError:
            logger.warning("Timeout getting top tracks (%s)", time_range)
            return []
        except Exception as e:
            logger.warning(f"Error getting top tracks ({time_range}): {e}")
            return []

    async def _fetch_all_top_tracks(self, sp: spotipy.Spotify) -> List[Dict]:
        """Collect top tracks across all three Spotify time ranges."""
        tracks: List[Dict] = []
        for time_range in ('short_term', 'medium_term', 'long_term'):
            batch = await self.get_user_top_tracks(sp, time_range, 50)
            tracks.extend(batch)
            logger.debug(f"Top tracks ({time_range}): {len(batch)}")
        return tracks

    async def _fetch_all_saved_tracks(self, sp: spotipy.Spotify, max_tracks: int = 2000) -> List[Dict]:
        """Paginate through ALL liked/saved tracks in the user's library."""
        tracks: List[Dict] = []
        offset = 0
        while len(tracks) < max_tracks:
            try:
                batch = sp.current_user_saved_tracks(limit=50, offset=offset)
                items = batch.get('items', [])
                if not items:
                    break
                for item in items:
                    if item.get('track') and item['track'].get('id'):
                        tracks.append(item['track'])
                        if len(tracks) >= max_tracks:
                            break
                logger.debug(f"Saved tracks: +{len(items)} at offset {offset}, total={len(tracks)}")
                if len(items) < 50 or not batch.get('next'):
                    break
                offset += 50
            except Exception as e:
                logger.warning(f"Error fetching saved tracks at offset {offset}: {e}")
                break
        logger.info(f"Fetched {len(tracks)} saved tracks")
        return tracks

    async def _fetch_all_playlist_tracks(self, sp: spotipy.Spotify, max_tracks: int = 2000) -> List[Dict]:
        """Paginate through user-owned playlists and collect all their tracks."""
        user_id = sp.me()['id']

        all_playlists: List[Dict] = []
        offset = 0
        while True:
            try:
                batch = sp.current_user_playlists(limit=50, offset=offset)
                items = batch.get('items', [])
                if not items:
                    break
                all_playlists.extend(items)
                if len(items) < 50 or not batch.get('next'):
                    break
                offset += 50
            except Exception as e:
                logger.warning(f"Error fetching playlists at offset {offset}: {e}")
                break

        logger.info(f"Found {len(all_playlists)} playlists")

        tracks: List[Dict] = []
        for playlist in all_playlists:
            if len(tracks) >= max_tracks:
                break
            if playlist.get('owner', {}).get('id') != user_id:
                continue

            track_offset = 0
            playlist_count = 0
            while len(tracks) < max_tracks:
                try:
                    batch = sp.playlist_tracks(playlist['id'], limit=100, offset=track_offset)
                    items = batch.get('items', [])
                    if not items:
                        break
                    for item in items:
                        if item.get('track') and item['track'].get('id'):
                            tracks.append(item['track'])
                            playlist_count += 1
                    if len(items) < 100 or not batch.get('next'):
                        break
                    track_offset += 100
                except Exception as e:
                    logger.warning(f"Error fetching tracks from '{playlist['name']}': {e}")
                    break

            logger.debug(f"Playlist '{playlist['name']}': {playlist_count} tracks")

        logger.info(f"Fetched {len(tracks)} playlist tracks")
        return tracks

    async def _fetch_recently_played(self, sp: spotipy.Spotify) -> List[Dict]:
        """Get up to 50 recently played tracks (Spotify's hard limit)."""
        try:
            result = sp.current_user_recently_played(limit=50)
            tracks = [
                item['track']
                for item in result.get('items', [])
                if item.get('track') and item['track'].get('id')
            ]
            logger.debug(f"Recently played: {len(tracks)}")
            return tracks
        except Exception as e:
            logger.warning(f"Error fetching recently played: {e}")
            return []

    async def get_user_all_tracks(self, sp: spotipy.Spotify, limit: int = 2000) -> List[Dict]:
        """
        Collect the user's complete Spotify library from all sources:
        top tracks, saved/liked songs, owned playlists, recently played.
        Returns up to `limit` deduplicated tracks (shuffled).
        """
        candidates: List[Dict] = []
        candidates.extend(await self._fetch_all_top_tracks(sp))
        candidates.extend(await self._fetch_all_saved_tracks(sp, max_tracks=limit))
        candidates.extend(await self._fetch_all_playlist_tracks(sp, max_tracks=limit))
        candidates.extend(await self._fetch_recently_played(sp))

        seen: Set[str] = set()
        unique: List[Dict] = []
        for track in candidates:
            tid = track.get('id')
            if tid and tid not in seen:
                seen.add(tid)
                unique.append(track)

        logger.info(
            f"Library: {len(candidates)} raw → {len(unique)} unique tracks "
            f"(capped at {limit})"
        )
        random.shuffle(unique)
        return unique[:limit]

    async def get_artist_similar_tracks(self, sp: spotipy.Spotify, artist_id: str, limit: int = 10) -> List[Dict]:
        """Sample tracks from the artist's recent albums and singles."""
        try:
            albums = sp.artist_albums(artist_id, album_type='album,single', limit=10)
            similar_tracks: List[Dict] = []
            for album in albums['items']:
                if len(similar_tracks) >= limit:
                    break
                try:
                    tracks = sp.album_tracks(album['id'], limit=10)
                    for track in tracks['items']:
                        similar_tracks.append({
                            'id': track['id'],
                            'name': track['name'],
                            'artists': [a['name'] for a in track['artists']],
                            'album': album['name'],
                            'album_images': album.get('images', []),
                            'album_image_url': self._select_album_image_url(album.get('images', [])),
                            'preview_url': track.get('preview_url'),
                            'external_urls': track.get('external_urls', {}),
                            'similarity_score': round(random.uniform(0.85, 0.95), 2),
                            'recommendation_reason': f"More from {track['artists'][0]['name']}",
                        })
                        if len(similar_tracks) >= limit:
                            break
                except Exception:
                    continue
            return similar_tracks[:limit]
        except Exception as e:
            logger.warning(f"Error getting artist tracks for {artist_id}: {e}")
            return []

    async def get_album_deep_cuts(
        self, sp: spotipy.Spotify, album_id: str, exclude_track_ids: Set[str], limit: int = 5
    ) -> List[Dict]:
        """Return non-excluded tracks from an album (album info fetched once)."""
        try:
            album_info = sp.album(album_id)
            tracks = sp.album_tracks(album_id, limit=50)
            deep_cuts: List[Dict] = []
            for track in tracks['items']:
                if track['id'] not in exclude_track_ids:
                    deep_cuts.append({
                        'id': track['id'],
                        'name': track['name'],
                        'artists': [a['name'] for a in track['artists']],
                        'album': album_info['name'],
                        'album_images': album_info.get('images', []),
                        'album_image_url': self._select_album_image_url(album_info.get('images', [])),
                        'preview_url': track.get('preview_url'),
                        'external_urls': track.get('external_urls', {}),
                        'similarity_score': round(random.uniform(0.80, 0.90), 2),
                        'recommendation_reason': f"From {album_info['name']}",
                    })
                    if len(deep_cuts) >= limit:
                        break
            return deep_cuts
        except Exception as e:
            logger.warning(f"Error getting album deep cuts for {album_id}: {e}")
            return []

    async def get_artist_top_tracks_discovery(
        self, sp: spotipy.Spotify, artist_id: str, exclude_track_ids: Set[str], limit: int = 3
    ) -> List[Dict]:
        """Get popular tracks from an artist, skipping already-known ones."""
        try:
            result = sp.artist_top_tracks(artist_id)
            discoveries: List[Dict] = []
            for track in result['tracks']:
                if track['id'] not in exclude_track_ids:
                    discoveries.append({
                        'id': track['id'],
                        'name': track['name'],
                        'artists': [a['name'] for a in track['artists']],
                        'album': track['album']['name'],
                        'preview_url': track.get('preview_url'),
                        'external_urls': track.get('external_urls', {}),
                        'similarity_score': round(random.uniform(0.80, 0.92), 2),
                        'recommendation_reason': f"Popular track by {track['artists'][0]['name']}",
                    })
                    if len(discoveries) >= limit:
                        break
            return discoveries
        except Exception as e:
            logger.warning(f"Error getting artist top tracks for {artist_id}: {e}")
            return []

    async def get_related_artists_recommendations(
        self, sp: spotipy.Spotify, artist_id: str, user_track_ids: Set[str], limit: int = 5
    ) -> List[Dict]:
        """Get top tracks from artists related to the given artist."""
        try:
            related = sp.artist_related_artists(artist_id)
            recommendations: List[Dict] = []
            for related_artist in related['artists'][:5]:
                top_tracks = sp.artist_top_tracks(related_artist['id'])
                for track in top_tracks['tracks'][:3]:
                    if track['id'] not in user_track_ids:
                        recommendations.append({
                            'id': track['id'],
                            'name': track['name'],
                            'artists': [a['name'] for a in track['artists']],
                            'album': track['album']['name'],
                            'similarity_score': round(random.uniform(0.75, 0.90), 2),
                            'recommendation_reason': 'Similar artist to your favorites',
                        })
                        if len(recommendations) >= limit:
                            return recommendations
            return recommendations
        except Exception as e:
            logger.warning(f"Error getting related artists for {artist_id}: {e}")
            return []

    async def get_genre_recommendations(
        self, sp: spotipy.Spotify, genres: list, user_track_ids: Set[str], limit: int = 10
    ) -> List[Dict]:
        """Get recommendations from Spotify's recommendation API seeded with genres."""
        try:
            recs = sp.recommendations(seed_genres=genres[:5], limit=limit * 2, market='US')
            recommendations: List[Dict] = []
            for track in recs['tracks']:
                if track['id'] not in user_track_ids:
                    recommendations.append({
                        'id': track['id'],
                        'name': track['name'],
                        'artists': [a['name'] for a in track['artists']],
                        'album': track['album']['name'],
                        'similarity_score': round(random.uniform(0.70, 0.85), 2),
                        'recommendation_reason': f"Genre discovery: {', '.join(genres[:2])}",
                    })
                    if len(recommendations) >= limit:
                        break
            return recommendations
        except Exception as e:
            logger.warning(f"Error with genre recommendations: {e}")
            return []

    async def _spotify_recommendations(
        self,
        sp: spotipy.Spotify,
        seed_artists: Optional[List[str]] = None,
        seed_tracks: Optional[List[str]] = None,
        user_track_ids: Optional[Set[str]] = None,
        limit: int = 20,
        **audio_target_kwargs,
    ) -> List[Dict]:
        """
        Thin wrapper around sp.recommendations() that:
        - Enforces the 1–5 seed limit
        - Filters out tracks already in the user's library
        - Normalises output to the standard recommendation dict shape
        - Accepts audio feature targets/bounds as keyword arguments
          (e.g. target_valence=0.8, min_energy=0.6)
        """
        seed_artists = (seed_artists or [])[:5]
        remaining_slots = max(0, 5 - len(seed_artists))
        seed_tracks = (seed_tracks or [])[:remaining_slots]

        total_seeds = len(seed_artists) + len(seed_tracks)
        if total_seeds == 0:
            return []

        params = {
            'seed_artists': seed_artists,
            'seed_tracks': seed_tracks,
            'limit': min(limit * 2, 100),
            'market': 'US',
        }
        params.update(audio_target_kwargs)

        try:
            result = sp.recommendations(**params)
            recs: List[Dict] = []
            for track in result.get('tracks', []):
                if user_track_ids and track['id'] in user_track_ids:
                    continue
                recs.append({
                    'id': track['id'],
                    'name': track['name'],
                    'artists': [a['name'] for a in track['artists']],
                    'album': track['album']['name'],
                    'album_images': track['album'].get('images', []),
                    'album_image_url': self._select_album_image_url(track['album'].get('images', [])),
                    'preview_url': track.get('preview_url'),
                    'external_urls': track.get('external_urls', {}),
                    'similarity_score': round(random.uniform(0.78, 0.95), 2),
                    'recommendation_reason': 'Recommended based on your taste',
                })
                if len(recs) >= limit:
                    break
            logger.info("Spotify recommendations API: %d tracks returned", len(recs))
            return recs

        except spotipy.SpotifyException as exc:
            if exc.http_status == 404:
                logger.warning(
                    "Spotify /v1/recommendations returned 404 — "
                    "this endpoint is deprecated for apps created after Nov 2024. "
                    "Falling back to artist-based discovery."
                )
            elif exc.http_status == 403:
                logger.warning(
                    "Spotify /v1/recommendations returned 403 Forbidden. "
                    "Params: seed_artists=%s seed_tracks=%s",
                    params.get("seed_artists"), params.get("seed_tracks"),
                )
            elif exc.http_status == 429:
                retry_after = 2
                if exc.headers:
                    try:
                        retry_after = int(exc.headers.get("Retry-After", 2))
                    except (ValueError, TypeError):
                        pass
                logger.warning(
                    "Spotify recommendations rate-limited (429), Retry-After=%ds", retry_after
                )
            elif exc.http_status == 401:
                logger.warning("Spotify recommendations: 401 Unauthorized — token may be stale")
            else:
                logger.warning(
                    "Spotify recommendations API error: HTTP %d — "
                    "seed_artists=%s seed_tracks=%s",
                    exc.http_status,
                    params.get("seed_artists"),
                    params.get("seed_tracks"),
                )
            return []

        except Exception as exc:
            logger.warning("Spotify recommendations API unexpected error: %s", exc)
            return []

    async def build_user_profile(self, user_id: str, access_token: str):
        """Build a user profile using real Spotify audio features (not random)."""
        try:
            sp = await self.get_spotify_client(access_token)
            all_tracks = await self.get_user_all_tracks(sp, limit=500)

            if not all_tracks:
                return {"error": "No tracks found for user profile"}

            track_ids = [t['id'] for t in all_tracks]
            logger.info(f"Fetching audio features for {len(track_ids)} tracks")
            features_df = await self.extract_audio_features(sp, track_ids)

            if features_df.empty or not any(c in features_df.columns for c in _AUDIO_FEATURE_COLS):
                avg_features = {col: 0.5 for col in _AUDIO_FEATURE_COLS}
                avg_features['tempo'] = 120.0
            else:
                avg_features = {
                    col: round(float(features_df[col].mean()), 3)
                    for col in _AUDIO_FEATURE_COLS
                    if col in features_df.columns
                }

            logger.info(f"Profile built: {len(all_tracks)} tracks analysed for user {user_id}")
            return {
                'user_id': user_id,
                'avg_features': avg_features,
                'total_tracks_analyzed': len(all_tracks),
                'created_at': datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            logger.error(f"Error building user profile: {e}")
            return {"error": str(e)}

    async def build_music_dna(self, spotify_id: str, access_token: str) -> Dict:
        """
        Build a Music DNA payload WITHOUT using the restricted /v1/audio-features endpoint.

        Data sources (all confirmed working):
        - current_user_top_artists  → genre tags, artist popularity
        - current_user_top_tracks   → track popularity, release year, explicit flag

        Six dimensions (each normalized 0.0–1.0):
          energy        — high for rock/metal/edm; low for classical/ambient/folk
          valence       — high for pop/happy/summer; low for sad/emo/dark
          danceability  — high for dance/hip-hop/funk; low for classical/folk
          acousticness  — high for acoustic/folk/classical; low for electronic/edm
          speechiness   — high for hip-hop/rap/drill; low for instrumental/classical
          diversity     — unique genre count normalised (max ~30 genres → 1.0)

        Result cached per-user for 20 min (key: dna:{spotify_id}).
        """
        cache_key = f"dna:{spotify_id}"
        logger.info("Music DNA cache lookup spotify_id=%s cache_key=%s", spotify_id, cache_key)
        cached = await get_cache(cache_key)
        if cached:
            try:
                cached_payload = json.loads(cached)
                if isinstance(cached_payload, dict) and "status" not in cached_payload:
                    cached_payload["status"] = "ok"
                logger.info(
                    "Music DNA cache hit spotify_id=%s cache_key=%s status=%s dimensions=%s",
                    spotify_id,
                    cache_key,
                    cached_payload.get("status"),
                    cached_payload.get("dimensions"),
                )
                return cached_payload
            except Exception:
                pass

        try:
            sp = await self.get_spotify_client(access_token)
            fallback_conditions: List[str] = []

            artists: List[Dict] = []
            seen_artist_ids: Set[str] = set()
            for time_range in ('short_term', 'medium_term', 'long_term'):
                try:
                    result = await self._spotify_call_with_timeout(
                        sp.current_user_top_artists,
                        time_range=time_range,
                        limit=20,
                        timeout_seconds=10.0,
                        call_name=f"current_user_top_artists[{time_range}]",
                    )
                    for a in result.get('items', []):
                        aid = a.get('id')
                        if aid and aid not in seen_artist_ids:
                            artists.append(a)
                            seen_artist_ids.add(aid)
                except asyncio.TimeoutError:
                    fallback_conditions.append(f"top_artists_timeout:{time_range}")
                    logger.warning("Top artists (%s) timed out for user %s", time_range, spotify_id)
                except Exception as exc:
                    fallback_conditions.append(f"top_artists_error:{time_range}")
                    logger.debug("Top artists (%s) skipped: %s", time_range, exc)

            tracks: List[Dict] = []
            seen_track_ids: Set[str] = set()
            for time_range in ('short_term', 'medium_term', 'long_term'):
                try:
                    result = await self._spotify_call_with_timeout(
                        sp.current_user_top_tracks,
                        time_range=time_range,
                        limit=50,
                        timeout_seconds=10.0,
                        call_name=f"current_user_top_tracks[{time_range}]",
                    )
                    for t in result.get('items', []):
                        tid = t.get('id')
                        if tid and tid not in seen_track_ids:
                            tracks.append(t)
                            seen_track_ids.add(tid)
                except asyncio.TimeoutError:
                    fallback_conditions.append(f"top_tracks_timeout:{time_range}")
                    logger.warning("Top tracks (%s) timed out for user %s", time_range, spotify_id)
                except Exception as exc:
                    fallback_conditions.append(f"top_tracks_error:{time_range}")
                    logger.debug("Top tracks (%s) skipped: %s", time_range, exc)

            if not artists and not tracks:
                logger.warning(
                    "Music DNA fallback: no Spotify data available for %s (conditions=%s)",
                    spotify_id,
                    fallback_conditions,
                )
                return {
                    "spotify_id": spotify_id,
                    "status": "fallback",
                    "dimensions": {
                        "energy": 0.5,
                        "valence": 0.5,
                        "danceability": 0.5,
                        "acousticness": 0.5,
                        "speechiness": 0.5,
                        "diversity": 0.0,
                    },
                    "metadata": {
                        "total_artists_analyzed": 0,
                        "total_tracks_analyzed": 0,
                        "unique_genres": [],
                        "avg_popularity": 0.5,
                        "avg_era": 0.5,
                        "source": "fallback",
                        "fallback_reasons": fallback_conditions,
                    },
                    "source": "fallback",
                    "error": "No Spotify data available — connect Spotify and try again",
                }

            all_genres: List[str] = []
            for artist in artists:
                all_genres.extend(artist.get('genres', []))

            unique_genres: Set[str] = set(all_genres)
            genre_text: str = ' '.join(all_genres).lower()
            genre_count: int = len(all_genres) or 1

            def _dim(pos_kws: List[str], neg_kws: List[str]) -> float:
                """Score a dimension 0.1–0.9 based on genre keyword balance."""
                pos = sum(genre_text.count(kw) for kw in pos_kws)
                neg = sum(genre_text.count(kw) for kw in neg_kws)
                ratio = (pos - neg) / genre_count
                return round(max(0.1, min(0.9, 0.5 + ratio * 0.4)), 3)

            energy = _dim(
                ['rock', 'metal', 'punk', 'edm', 'dance', 'electronic', 'hip hop',
                 'trap', 'dubstep', 'drum', 'industrial', 'hardcore'],
                ['ambient', 'classical', 'acoustic', 'folk', 'sleep', 'calm',
                 'meditation', 'new age', 'chamber'],
            )
            valence = _dim(
                ['pop', 'happy', 'dance', 'summer', 'party', 'tropical', 'indie pop',
                 'sunshine', 'feel good', 'bubblegum'],
                ['sad', 'emo', 'depression', 'dark', 'doom', 'funeral', 'melanchol',
                 'post-punk', 'gothic', 'black metal'],
            )
            danceability = _dim(
                ['dance', 'disco', 'funk', 'edm', 'club', 'house', 'techno',
                 'hip hop', 'r&b', 'reggaeton', 'trap', 'afrobeats', 'dancehall'],
                ['classical', 'ambient', 'folk', 'acoustic', 'singer-songwriter',
                 'bluegrass', 'chamber', 'post-rock'],
            )
            acousticness = _dim(
                ['acoustic', 'folk', 'classical', 'country', 'singer-songwriter',
                 'bluegrass', 'chamber', 'unplugged', 'neofolk', 'bossa nova'],
                ['electronic', 'edm', 'synthpop', 'industrial', 'drum and bass',
                 'techno', 'electro', 'dubstep'],
            )
            speechiness = _dim(
                ['hip hop', 'rap', 'spoken word', 'comedy', 'trap', 'drill',
                 'grime', 'conscious hip hop', 'east coast hip hop'],
                ['classical', 'ambient', 'instrumental', 'post-rock', 'chamber',
                 'new age', 'sleep'],
            )

            diversity = round(min(1.0, len(unique_genres) / 30.0), 3)

            avg_popularity = 0.5
            if tracks:
                avg_popularity = round(
                    sum(t.get('popularity', 50) for t in tracks) / (len(tracks) * 100), 3
                )

            years: List[int] = []
            for t in tracks:
                rd = t.get('album', {}).get('release_date', '')
                if rd and len(rd) >= 4:
                    try:
                        years.append(int(rd[:4]))
                    except ValueError:
                        pass
            avg_era = round(
                max(0.0, min(1.0, (sum(years) / len(years) - 1970) / 55.0)) if years else 0.5, 3
            )

            dna: Dict = {
                "spotify_id": spotify_id,
                "status": "degraded" if fallback_conditions else "ok",
                "dimensions": {
                    "energy": energy,
                    "valence": valence,
                    "danceability": danceability,
                    "acousticness": acousticness,
                    "speechiness": speechiness,
                    "diversity": diversity,
                },
                "metadata": {
                    "total_artists_analyzed": len(artists),
                    "total_tracks_analyzed": len(tracks),
                    "unique_genres": sorted(unique_genres)[:20],
                    "avg_popularity": avg_popularity,
                    "avg_era": avg_era,
                    "source": "genres+popularity+era",
                    "fallback_reasons": fallback_conditions,
                },
                "source": "genres+popularity+era",
            }

            logger.info(
                "Music DNA built for %s: %d artists, %d genres, %d tracks (status=%s dimensions=%s)",
                spotify_id, len(artists), len(unique_genres), len(tracks), dna["status"], dna["dimensions"],
            )
            if fallback_conditions:
                logger.warning(
                    "Music DNA degraded for %s due to: %s",
                    spotify_id,
                    fallback_conditions,
                )

            try:
                await set_cache(cache_key, json.dumps(dna), expire=1200)
                logger.info("Music DNA cache set spotify_id=%s cache_key=%s ttl_seconds=1200", spotify_id, cache_key)
            except Exception:
                pass
            return dna

        except Exception as exc:
            logger.error("Error building music DNA for %s: %s", spotify_id, exc)
            return {"error": str(exc)}


    async def _get_related_artists_cached(self, sp: spotipy.Spotify, artist_id: str) -> List[Dict]:
        """Fetch related artists, caching results for 24 h."""
        cache_key = f"artist_related:{artist_id}"
        cached = await get_cache(cache_key)
        if cached:
            try:
                return json.loads(cached)
            except Exception:
                pass
        try:
            result = sp.artist_related_artists(artist_id)
            artists = result.get('artists', [])
            await set_cache(cache_key, json.dumps(artists), expire=86400)
            return artists
        except Exception as exc:
            logger.warning("Related artists fetch failed for %s: %s", artist_id, exc)
            return []

    async def _get_artist_top_tracks_cached(self, sp: spotipy.Spotify, artist_id: str) -> List[Dict]:
        """Fetch artist top tracks, caching results for 24 h."""
        cache_key = f"artist_top_tracks:{artist_id}"
        cached = await get_cache(cache_key)
        if cached:
            try:
                return json.loads(cached)
            except Exception:
                pass
        try:
            result = sp.artist_top_tracks(artist_id)
            tracks = result.get('tracks', [])
            await set_cache(cache_key, json.dumps(tracks), expire=86400)
            return tracks
        except Exception as exc:
            logger.warning("Top tracks fetch failed for artist %s: %s", artist_id, exc)
            return []

    async def _get_user_top_artists(self, sp: spotipy.Spotify) -> List[Dict]:
        """
        Collect top artists from all three Spotify time ranges.
        Uses current_user_top_artists — always available.
        """
        artists: List[Dict] = []
        seen: Set[str] = set()
        for time_range in ('short_term', 'medium_term', 'long_term'):
            try:
                result = sp.current_user_top_artists(time_range=time_range, limit=20)
                for artist in result.get('items', []):
                    aid = artist.get('id')
                    if aid and aid not in seen:
                        artists.append(artist)
                        seen.add(aid)
            except Exception as exc:
                logger.warning("Top artists (%s) fetch failed: %s", time_range, exc)
        logger.info("Top artists from Spotify: %d unique across all time ranges", len(artists))
        return artists

    async def _get_artist_catalog_tracks(
        self,
        sp: spotipy.Spotify,
        artist_id: str,
        exclude_ids: Set[str],
        limit: int = 15,
    ) -> List[Dict]:
        """
        Sample tracks from an artist's albums and singles.
        Uses artist_albums + album_tracks — both always available.
        Results cached for 24 h (keyed by artist_id).
        Only tracks whose IDs are not in exclude_ids are returned.
        """
        cache_key = f"artist_catalog:{artist_id}"
        cached = await get_cache(cache_key)
        if cached:
            try:
                all_tracks = json.loads(cached)
                random.shuffle(all_tracks)
                return [t for t in all_tracks if t['id'] not in exclude_ids][:limit]
            except Exception:
                pass

        try:
            albums_result = sp.artist_albums(artist_id, album_type='album,single', limit=10)
            all_tracks: List[Dict] = []
            album_items = list(albums_result.get('items', []))
            random.shuffle(album_items)
            for album in album_items[:5]:
                try:
                    tracks_result = sp.album_tracks(album['id'], limit=10)
                    for track in tracks_result.get('items', []):
                        tid = track.get('id')
                        if tid:
                            all_tracks.append({
                                'id': tid,
                                'name': track['name'],
                                'artists': [a['name'] for a in track.get('artists', [])],
                                'artist_ids': [
                                    a['id'] for a in track.get('artists', []) if a.get('id')
                                ],
                                'album': album['name'],
                                'album_images': album.get('images', []),
                                'album_image_url': self._select_album_image_url(album.get('images', [])),
                                'preview_url': track.get('preview_url'),
                                'external_urls': track.get('external_urls', {}),
                            })
                except Exception:
                    continue
            await set_cache(cache_key, json.dumps(all_tracks), expire=86400)
            shuffled = list(all_tracks)
            random.shuffle(shuffled)
            return [t for t in shuffled if t['id'] not in exclude_ids][:limit]
        except Exception as exc:
            logger.warning("Catalog fetch failed for artist %s: %s", artist_id, exc)
            return []

    async def _get_user_library_cached(self, user_id: str, sp: spotipy.Spotify) -> List[Dict]:
        """Fetch user's full library, cached for 30 min to avoid repeated heavy API calls."""
        from app.core.database import get_cache, set_cache
        cache_key = f"library:{user_id}"
        cached = await get_cache(cache_key)
        if cached:
            try:
                logger.debug("Library cache hit for user %s", user_id)
                return json.loads(cached)
            except Exception:
                pass
        tracks = await self.get_user_all_tracks(sp, limit=500)
        if tracks:
            try:
                await set_cache(cache_key, json.dumps(tracks), expire=_LIBRARY_CACHE_TTL)
            except Exception:
                pass
        return tracks

    async def _load_rec_history(self, user_id: str) -> Set[str]:
        """Load set of recently recommended track IDs for a user."""
        from app.core.database import get_cache
        cached = await get_cache(f"rec_history:{user_id}")
        if cached:
            try:
                return set(json.loads(cached))
            except Exception:
                pass
        return set()

    async def _save_rec_history(self, user_id: str, new_track_ids: List[str]) -> None:
        """Append new track IDs to history, keeping the most recent _REC_HISTORY_MAX entries."""
        from app.core.database import get_cache, set_cache
        existing = await get_cache(f"rec_history:{user_id}")
        history: List[str] = []
        if existing:
            try:
                history = json.loads(existing)
            except Exception:
                pass
        new_set = set(new_track_ids)
        combined = list(new_track_ids) + [tid for tid in history if tid not in new_set]
        trimmed = combined[:_REC_HISTORY_MAX]
        try:
            await set_cache(f"rec_history:{user_id}", json.dumps(trimmed), expire=_REC_HISTORY_TTL)
        except Exception:
            pass


    async def generate_recommendations(
        self,
        user_id: str,
        access_token: str,
        seed_tracks=None,
        target_features=None,
        limit: int = 20,
    ) -> List[Dict]:
        """
        Generate personalised recommendations using only working Spotify endpoints.

        Restricted endpoints intentionally NOT used:
        - audio_features  → 403 (deprecated for apps created after Nov 2024)
        - recommendations → 404 (deprecated for apps created after Nov 2024)
        - artist_related_artists → 404 (deprecated)

        Algorithm (all endpoints confirmed working):
        1. Fetch user library (cached 30 min to avoid heavy repeated API calls).
        2. Load recommendation history; build exclusion set (library + history).
        3. Rank artists by library frequency; augment with Spotify top artists.
        4. Build full artist pool (up to 50); anchor on top 5, randomly sample 15 more.
        5. For each seed artist:
           a. artist_top_tracks → up to 5 tracks (shuffled for variety)
           b. artist_albums + album_tracks → up to 15 catalog deep cuts (shuffled)
        6. Candidate pool filtered by exclusion set (library + history).
        7. Tiered random sampling with artist diversity (pass 1: max 1/artist;
           pass 2: max 2/artist; pass 3: uncapped fill).
        8. Save returned track IDs to recommendation history.
        """
        try:
            sp = await self.get_spotify_client(access_token)
            logger.info("Generating recommendations for user %s", user_id)

            all_user_tracks = await self._get_user_library_cached(user_id, sp)
            if not all_user_tracks:
                logger.warning("No user tracks found — aborting")
                return []

            user_track_ids: Set[str] = {t['id'] for t in all_user_tracks}
            logger.info("Library: %d unique tracks", len(user_track_ids))

            rec_history = await self._load_rec_history(user_id)
            exclusion_set: Set[str] = user_track_ids | rec_history
            logger.info(
                "Exclusion set: %d library + %d history = %d total",
                len(user_track_ids), len(rec_history), len(exclusion_set),
            )

            artist_frequency: Dict[str, int] = defaultdict(int)
            for track in all_user_tracks:
                for artist in track.get('artists', []):
                    aid = artist.get('id')
                    if aid:
                        artist_frequency[aid] += 1

            top_artists_by_freq = sorted(
                artist_frequency.items(), key=lambda x: x[1], reverse=True
            )
            logger.info("Artists in library: %d unique", len(top_artists_by_freq))

            logger.info("Fetching Spotify top artists to augment seeds…")
            spotify_top = await self._get_user_top_artists(sp)
            spotify_top_ids = [a['id'] for a in spotify_top if a.get('id')]

            full_artist_pool: List[str] = []
            seen_in_pool: Set[str] = set()
            for aid in spotify_top_ids:
                if aid not in seen_in_pool:
                    full_artist_pool.append(aid)
                    seen_in_pool.add(aid)
            for aid, _ in top_artists_by_freq[:40]:
                if aid not in seen_in_pool:
                    full_artist_pool.append(aid)
                    seen_in_pool.add(aid)

            anchors = full_artist_pool[:5]
            rest = full_artist_pool[5:]
            random.shuffle(rest)
            seed_artist_ids = anchors + rest[:15]
            logger.info(
                "Seed artists: %d anchors + %d random = %d (pool: %d)",
                len(anchors), min(len(rest), 15), len(seed_artist_ids), len(full_artist_pool),
            )

            candidate_pool: List[Dict] = []
            seen_candidate_ids: Set[str] = set(exclusion_set)

            for artist_id in seed_artist_ids:
                if len(candidate_pool) >= 300:
                    break

                top_tracks = await self._get_artist_top_tracks_cached(sp, artist_id)
                shuffled_top = list(top_tracks)
                random.shuffle(shuffled_top)
                for track in shuffled_top[:5]:
                    tid = track.get('id')
                    if tid and tid not in seen_candidate_ids:
                        candidate_pool.append({
                            'id': tid,
                            'name': track['name'],
                            'artists': [a['name'] for a in track.get('artists', [])],
                            'artist_ids': [
                                a['id'] for a in track.get('artists', []) if a.get('id')
                            ],
                            'album': track.get('album', {}).get('name', ''),
                            'album_images': track.get('album', {}).get('images', []),
                            'album_image_url': self._select_album_image_url(
                                track.get('album', {}).get('images', [])
                            ),
                            'preview_url': track.get('preview_url'),
                            'external_urls': track.get('external_urls', {}),
                            'similarity_score': round(random.uniform(0.78, 0.93), 2),
                            'recommendation_reason': 'Popular track from a favourite artist',
                        })
                        seen_candidate_ids.add(tid)

                catalog = await self._get_artist_catalog_tracks(
                    sp, artist_id, seen_candidate_ids, limit=15
                )
                for track in catalog:
                    if track['id'] not in seen_candidate_ids:
                        track['similarity_score'] = round(random.uniform(0.72, 0.88), 2)
                        track['recommendation_reason'] = 'Deep cut from a favourite artist'
                        candidate_pool.append(track)
                        seen_candidate_ids.add(track['id'])
                    if len(candidate_pool) >= 300:
                        break

            unique_artists_in_pool = len({
                (t.get('artist_ids') or [t['artists'][0] if t['artists'] else 'unknown'])[0]
                for t in candidate_pool
            })
            logger.info(
                "Candidate pool: %d tracks | %d unique artists | "
                "excluded library: %d | excluded history: %d",
                len(candidate_pool), unique_artists_in_pool,
                len(user_track_ids), len(rec_history),
            )

            if not candidate_pool:
                logger.warning(
                    "Candidate pool is empty for user %s — "
                    "artist_top_tracks and artist_albums returned no new tracks",
                    user_id,
                )
                return []

            random.shuffle(candidate_pool)
            final_recs: List[Dict] = []
            artist_counts: Dict[str, int] = defaultdict(int)

            def _primary(t: Dict) -> str:
                ids = t.get('artist_ids', [])
                return ids[0] if ids else (t['artists'][0] if t['artists'] else 'unknown')

            for track in candidate_pool:
                if artist_counts[_primary(track)] < 1:
                    final_recs.append(track)
                    artist_counts[_primary(track)] += 1
                if len(final_recs) >= limit:
                    break

            if len(final_recs) < limit:
                used_ids = {t['id'] for t in final_recs}
                for track in candidate_pool:
                    if track['id'] not in used_ids and artist_counts[_primary(track)] < 2:
                        final_recs.append(track)
                        used_ids.add(track['id'])
                        artist_counts[_primary(track)] += 1
                    if len(final_recs) >= limit:
                        break

            if len(final_recs) < limit:
                used_ids = {t['id'] for t in final_recs}
                for track in candidate_pool:
                    if track['id'] not in used_ids:
                        final_recs.append(track)
                        used_ids.add(track['id'])
                    if len(final_recs) >= limit:
                        break

            logger.info(
                "Final: %d tracks, %d unique artists",
                len(final_recs), len({_primary(t) for t in final_recs}),
            )

            await self._save_rec_history(user_id, [t['id'] for t in final_recs])

            return final_recs[:limit]

        except Exception as exc:
            logger.error("Error generating recommendations for user %s: %s", user_id, exc)
            return []

    async def generate_mood_playlist(
        self, user_id: str, access_token: str, mood: str, limit: int = 20
    ) -> List[Dict]:
        """
        Generate a mood-based playlist using only working Spotify endpoints.

        Restricted endpoints intentionally NOT used:
        - audio_features  → 403 (deprecated for apps created after Nov 2024)
        - recommendations → 404 (deprecated for apps created after Nov 2024)

        Strategy (in order):
        1. Fetch user's full library (saved tracks + top tracks + playlists).
        2. Keyword matching against track/artist/album names from the library.
        3. Catalog filler: artist_top_tracks + artist_albums/album_tracks for
           the user's most-frequent artists, filtered to exclude library tracks.
        """
        try:
            sp = await self.get_spotify_client(access_token)
            all_user_tracks = await self._get_user_library_cached(user_id, sp)
            if not all_user_tracks:
                return []

            user_track_ids: Set[str] = {t['id'] for t in all_user_tracks}

            rec_history = await self._load_rec_history(user_id)
            logger.info(
                "Mood playlist '%s': %d library tracks, %d history exclusions "
                "(audio_features skipped — 403; recommendations skipped — 404)",
                mood, len(all_user_tracks), len(rec_history),
            )

            mood_recs: List[Dict] = []

            mood_keywords: Dict[str, List[str]] = {
                'happy':     ['love', 'happy', 'good', 'feel', 'dance', 'party', 'sun', 'bright', 'joy'],
                'sad':       ['sad', 'cry', 'alone', 'broken', 'hurt', 'miss', 'lost', 'tear', 'rain'],
                'energetic': ['run', 'fire', 'energy', 'power', 'rock', 'electric', 'pump', 'wild'],
                'chill':     ['chill', 'calm', 'slow', 'smooth', 'relax', 'soft', 'dream', 'float'],
                'focus':     ['focus', 'ambient', 'instrumental', 'study', 'concentrate', 'mind'],
                'party':     ['party', 'dance', 'club', 'beat', 'bass', 'pump', 'turn', 'wild', 'night'],
            }
            keywords = mood_keywords.get(mood, [])

            kw_scored: List[tuple] = []
            for track in all_user_tracks:
                if track['id'] in rec_history:
                    continue
                text = ' '.join([
                    track.get('name', ''),
                    ' '.join(a.get('name', '') for a in track.get('artists', [])),
                    track.get('album', {}).get('name', ''),
                ]).lower()
                score = sum(1 for kw in keywords if kw in text)
                if score > 0:
                    kw_scored.append((track, score))

            kw_scored.sort(key=lambda x: x[1], reverse=True)
            if kw_scored:
                top_score = kw_scored[0][1]
                top_group = [x for x in kw_scored if x[1] == top_score]
                rest_group = [x for x in kw_scored if x[1] < top_score]
                random.shuffle(top_group)
                kw_scored = top_group + rest_group

            for track, _ in kw_scored[:limit]:
                mood_recs.append({
                    'id': track['id'],
                    'name': track['name'],
                    'artists': [a['name'] for a in track.get('artists', [])],
                    'album': track.get('album', {}).get('name', ''),
                    'preview_url': track.get('preview_url'),
                    'external_urls': track.get('external_urls', {}),
                    'similarity_score': round(random.uniform(0.78, 0.93), 2),
                    'recommendation_reason': f'From your library — perfect for {mood}',
                })
            logger.info("Mood '%s': %d tracks from keyword matching", mood, len(mood_recs))

            if len(mood_recs) < limit:
                artist_frequency: Dict[str, int] = defaultdict(int)
                for track in all_user_tracks:
                    for artist in track.get('artists', []):
                        aid = artist.get('id')
                        if aid:
                            artist_frequency[aid] += 1

                existing_ids: Set[str] = {r['id'] for r in mood_recs} | user_track_ids | rec_history
                needed = limit - len(mood_recs)

                for artist_id, _ in sorted(
                    artist_frequency.items(), key=lambda x: x[1], reverse=True
                )[:15]:
                    if needed <= 0:
                        break

                    top_tracks = await self._get_artist_top_tracks_cached(sp, artist_id)
                    for track in top_tracks[:3]:
                        tid = track.get('id')
                        if tid and tid not in existing_ids:
                            mood_recs.append({
                                'id': tid,
                                'name': track['name'],
                                'artists': [a['name'] for a in track.get('artists', [])],
                                'album': track.get('album', {}).get('name', ''),
                                'album_images': track.get('album', {}).get('images', []),
                                'album_image_url': self._select_album_image_url(
                                    track.get('album', {}).get('images', [])
                                ),
                                'preview_url': track.get('preview_url'),
                                'external_urls': track.get('external_urls', {}),
                                'similarity_score': round(random.uniform(0.72, 0.88), 2),
                                'recommendation_reason': f'More {mood} vibes',
                            })
                            existing_ids.add(tid)
                            needed -= 1
                        if needed <= 0:
                            break

                    if needed > 0:
                        catalog = await self._get_artist_catalog_tracks(
                            sp, artist_id, existing_ids, limit=5
                        )
                        for track in catalog:
                            if track['id'] not in existing_ids:
                                track['similarity_score'] = round(random.uniform(0.70, 0.85), 2)
                                track['recommendation_reason'] = f'More {mood} vibes'
                                mood_recs.append(track)
                                existing_ids.add(track['id'])
                                needed -= 1
                            if needed <= 0:
                                break

                logger.info("Mood '%s': %d tracks after catalog filler", mood, len(mood_recs))

            random.shuffle(mood_recs)
            logger.info("Generated %d tracks for '%s' mood", len(mood_recs), mood)
            return mood_recs[:limit]

        except Exception as exc:
            logger.error("Error generating mood playlist: %s", exc)
            return []
