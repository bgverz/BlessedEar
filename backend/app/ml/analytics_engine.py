import spotipy
import math
from collections import Counter, defaultdict
from datetime import datetime
from typing import List, Dict, Any


class AnalyticsEngine:
    """Computes real listening analytics from Spotify data that's still available
    (track/artist popularity, artist genre tags, album release dates, play/save
    timestamps). Deliberately avoids the deprecated audio-features/recommendations
    endpoints.
    """

    async def get_saved_tracks_with_dates(self, sp: spotipy.Spotify, limit: int = 150) -> List[Dict[str, Any]]:
        """Fetch saved tracks along with when they were added to the library"""
        tracks = []
        offset = 0
        while len(tracks) < limit:
            batch = sp.current_user_saved_tracks(limit=50, offset=offset)
            if not batch['items']:
                break
            for item in batch['items']:
                if item['track'] and item['track']['id']:
                    track = item['track']
                    track['added_at'] = item.get('added_at')
                    tracks.append(track)
            if len(batch['items']) < 50:
                break
            offset += 50
        return tracks[:limit]

    def _artist_ids_from_tracks(self, tracks: List[Dict[str, Any]]) -> List[str]:
        ids = []
        seen = set()
        for track in tracks:
            for artist in track.get('artists', []):
                artist_id = artist.get('id')
                if artist_id and artist_id not in seen:
                    seen.add(artist_id)
                    ids.append(artist_id)
        return ids

    def _fetch_artists(self, sp: spotipy.Spotify, artist_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """Batch-fetch full artist objects (genres, popularity) in chunks of 50"""
        artists_by_id = {}
        for i in range(0, len(artist_ids), 50):
            chunk = artist_ids[i:i + 50]
            try:
                result = sp.artists(chunk)
                for artist in result['artists']:
                    if artist:
                        artists_by_id[artist['id']] = artist
            except Exception as e:
                print(f"Error fetching artist batch: {e}")
        return artists_by_id

    def _genre_breakdown(self, tracks: List[Dict[str, Any]], artists_by_id: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        genre_counts = Counter()
        for track in tracks:
            primary_artist = track.get('artists', [{}])[0]
            artist = artists_by_id.get(primary_artist.get('id'))
            if artist:
                for genre in artist.get('genres', []):
                    genre_counts[genre] += 1

        total = sum(genre_counts.values())
        if total == 0:
            return []

        return [
            {"genre": genre, "count": count, "share": round(count / total, 4)}
            for genre, count in genre_counts.most_common(12)
        ]

    def _diversity_score(self, genre_breakdown: List[Dict[str, Any]]) -> float:
        """Normalized Shannon entropy over the genre distribution (0 = one genre, 1 = maximally spread out)"""
        if len(genre_breakdown) <= 1:
            return 0.0

        shares = [g['share'] for g in genre_breakdown]
        entropy = -sum(p * math.log2(p) for p in shares if p > 0)
        max_entropy = math.log2(len(shares))
        return round(entropy / max_entropy, 3) if max_entropy > 0 else 0.0

    def _era_distribution(self, tracks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        decade_counts = Counter()
        for track in tracks:
            release_date = track.get('album', {}).get('release_date', '')
            if len(release_date) >= 4 and release_date[:4].isdigit():
                year = int(release_date[:4])
                decade = f"{(year // 10) * 10}s"
                decade_counts[decade] += 1

        total = sum(decade_counts.values())
        if total == 0:
            return []

        return [
            {"decade": decade, "count": count, "share": round(count / total, 4)}
            for decade, count in sorted(decade_counts.items())
        ]

    def _popularity_profile(self, tracks: List[Dict[str, Any]], artists_by_id: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        track_popularities = [t.get('popularity', 0) for t in tracks if t.get('popularity') is not None]
        artist_popularities = [a.get('popularity', 0) for a in artists_by_id.values() if a.get('popularity') is not None]

        avg_track_pop = round(sum(track_popularities) / len(track_popularities), 1) if track_popularities else 0
        avg_artist_pop = round(sum(artist_popularities) / len(artist_popularities), 1) if artist_popularities else 0

        if avg_track_pop >= 65:
            taste_label = "Mainstream"
        elif avg_track_pop >= 35:
            taste_label = "Balanced"
        else:
            taste_label = "Deep cuts / niche"

        return {
            "avg_track_popularity": avg_track_pop,
            "avg_artist_popularity": avg_artist_pop,
            "taste_label": taste_label,
        }

    def _activity_trend(self, saved_tracks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Bucket library additions by month to show a real listening-activity trend"""
        month_counts = Counter()
        for track in saved_tracks:
            added_at = track.get('added_at')
            if not added_at:
                continue
            try:
                dt = datetime.strptime(added_at[:7], "%Y-%m")
                month_counts[dt.strftime("%Y-%m")] += 1
            except ValueError:
                continue

        return [
            {"month": month, "tracks_added": count}
            for month, count in sorted(month_counts.items())
        ]

    def _taste_shift(self, short_term_tracks: List[Dict[str, Any]], long_term_tracks: List[Dict[str, Any]]) -> Dict[str, Any]:
        short_artist_ids = {a['id'] for t in short_term_tracks for a in t.get('artists', []) if a.get('id')}
        long_artist_ids = {a['id'] for t in long_term_tracks for a in t.get('artists', []) if a.get('id')}

        if not short_artist_ids:
            return {"new_artist_share": 0.0, "description": "Not enough recent listening data yet"}

        new_artists = short_artist_ids - long_artist_ids
        new_share = round(len(new_artists) / len(short_artist_ids), 3)

        if new_share >= 0.6:
            description = "Your recent listening is mostly new artists"
        elif new_share >= 0.25:
            description = "You're mixing in a healthy amount of new artists"
        else:
            description = "You're mostly sticking with long-time favorites"

        return {"new_artist_share": new_share, "description": description}

    async def build_profile(
        self,
        sp: spotipy.Spotify,
        short_term_tracks: List[Dict[str, Any]],
        medium_term_tracks: List[Dict[str, Any]],
        long_term_tracks: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Build the full real analytics profile from already-fetched top-track lists"""
        saved_tracks = await self.get_saved_tracks_with_dates(sp, limit=150)

        all_tracks = medium_term_tracks + saved_tracks
        seen_ids = set()
        unique_tracks = []
        for track in all_tracks:
            if track.get('id') and track['id'] not in seen_ids:
                seen_ids.add(track['id'])
                unique_tracks.append(track)

        if not unique_tracks:
            return {"error": "No listening data available yet"}

        artist_ids = self._artist_ids_from_tracks(unique_tracks)
        artists_by_id = self._fetch_artists(sp, artist_ids)

        genre_breakdown = self._genre_breakdown(unique_tracks, artists_by_id)
        top_artists = sorted(
            artists_by_id.values(), key=lambda a: a.get('popularity', 0), reverse=True
        )
        artist_frequency = Counter()
        for track in unique_tracks:
            for artist in track.get('artists', []):
                if artist.get('id'):
                    artist_frequency[artist['id']] += 1
        most_played_artists = [
            {
                "id": artist_id,
                "name": artists_by_id[artist_id]['name'],
                "count": count,
                "genres": artists_by_id[artist_id].get('genres', [])[:3],
                "image": (artists_by_id[artist_id].get('images') or [{}])[0].get('url'),
            }
            for artist_id, count in artist_frequency.most_common(10)
            if artist_id in artists_by_id
        ]

        return {
            "total_tracks_analyzed": len(unique_tracks),
            "genre_breakdown": genre_breakdown,
            "diversity_score": self._diversity_score(genre_breakdown),
            "era_distribution": self._era_distribution(unique_tracks),
            "popularity_profile": self._popularity_profile(unique_tracks, artists_by_id),
            "most_played_artists": most_played_artists,
            "activity_trend": self._activity_trend(saved_tracks),
            "taste_shift": self._taste_shift(short_term_tracks, long_term_tracks),
            "created_at": datetime.utcnow().isoformat(),
        }
