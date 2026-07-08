export const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export const TOKEN_STORAGE_KEY = 'blessedear_token';

export class UnauthorizedError extends Error {
  constructor() {
    super('Session expired');
    this.name = 'UnauthorizedError';
  }
}

async function request<T>(path: string, token: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      Authorization: `Bearer ${token}`,
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...options.headers,
    },
  });

  if (response.status === 401) {
    if (typeof window !== 'undefined') {
      localStorage.removeItem(TOKEN_STORAGE_KEY);
      if (window.location.pathname !== '/login') {
        window.location.href = '/login';
      }
    }
    throw new UnauthorizedError();
  }

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed: ${response.status}`);
  }

  return response.json();
}

// ---- Types ----

export interface RecommendationTrack {
  id: string;
  name: string;
  artists: string[];
  album?: string;
  album_images?: Array<{ url: string; width: number; height: number }>;
  preview_url?: string;
  external_urls?: { spotify?: string };
  similarity_score: number;
  recommendation_reason: string;
}

export interface TopTrack {
  id: string;
  name: string;
  artists: { name: string }[];
  album: { name: string; images?: Array<{ url: string }> };
  popularity: number;
  preview_url?: string;
  external_urls?: { spotify?: string };
}

export interface GenreShare {
  genre: string;
  count: number;
  share: number;
}

export interface EraShare {
  decade: string;
  count: number;
  share: number;
}

export interface PopularityProfile {
  avg_track_popularity: number;
  avg_artist_popularity: number;
  taste_label: string;
}

export interface MostPlayedArtist {
  id: string;
  name: string;
  count: number;
  genres: string[];
  image?: string;
}

export interface ActivityPoint {
  month: string;
  tracks_added: number;
}

export interface TasteShift {
  new_artist_share: number;
  description: string;
}

export interface ListeningProfile {
  user_id?: string;
  total_tracks_analyzed: number;
  genre_breakdown: GenreShare[];
  diversity_score: number;
  era_distribution: EraShare[];
  popularity_profile: PopularityProfile;
  most_played_artists: MostPlayedArtist[];
  activity_trend: ActivityPoint[];
  taste_shift: TasteShift;
  insights?: string[];
  created_at: string;
}

export interface SavedPlaylist {
  id: number;
  name: string;
  description?: string;
  track_count: number;
  mood?: string;
  generation_type: string;
  is_exported: boolean;
  spotify_playlist_id?: string;
  created_at: string;
}

export interface CurrentUser {
  id: number;
  spotify_id: string;
  email?: string;
  display_name?: string;
}

// ---- Auth ----

export async function getCurrentUser(token: string): Promise<CurrentUser> {
  return request('/api/auth/me', token);
}

export async function logoutRequest(token: string): Promise<void> {
  await request('/api/auth/logout', token, { method: 'POST' });
}

// ---- Recommendations ----

export async function getUserProfile(token: string): Promise<ListeningProfile> {
  return request('/api/recommendations/profile', token);
}

export async function generateRecommendations(
  token: string,
  options: { seed_tracks?: string[]; target_features?: any; limit?: number } = {}
): Promise<RecommendationTrack[]> {
  const data = await request<{ tracks: RecommendationTrack[] }>('/api/recommendations/generate', token, {
    method: 'POST',
    body: JSON.stringify({ limit: 10, ...options }),
  });
  return data.tracks || [];
}

export async function generateMoodPlaylist(
  token: string,
  mood: string,
  limit: number = 10
): Promise<RecommendationTrack[]> {
  const data = await request<{ tracks: RecommendationTrack[] }>('/api/recommendations/mood-playlist', token, {
    method: 'POST',
    body: JSON.stringify({ mood, limit }),
  });
  return data.tracks || [];
}

export async function discoverMusic(
  token: string,
  discoverType: 'similar' | 'new-genres' | 'trending' | 'deep-cuts',
  limit: number = 12
): Promise<RecommendationTrack[]> {
  const data = await request<{ tracks: RecommendationTrack[] }>(
    `/api/recommendations/discover/${discoverType}?limit=${limit}`,
    token
  );
  return data.tracks || [];
}

export async function getTopTracks(
  token: string,
  timeRange: 'short_term' | 'medium_term' | 'long_term' = 'medium_term',
  limit: number = 20
): Promise<{ top_tracks: TopTrack[] }> {
  return request(`/api/recommendations/top-tracks?time_range=${timeRange}&limit=${limit}`, token);
}

// ---- Analytics ----

export async function getListeningProfile(token: string): Promise<ListeningProfile> {
  return request('/api/analytics/listening-profile', token);
}

// ---- Playlists ----

export async function getMyPlaylists(token: string): Promise<SavedPlaylist[]> {
  return request('/api/playlists/my-playlists', token);
}

export interface PlaylistDetails extends SavedPlaylist {
  tracks: RecommendationTrack[];
}

export async function getPlaylistDetails(token: string, playlistId: number): Promise<PlaylistDetails> {
  return request(`/api/playlists/${playlistId}`, token);
}

export async function savePlaylist(
  token: string,
  payload: { name: string; description?: string; tracks: RecommendationTrack[]; mood?: string | null; generation_type: string }
) {
  return request('/api/playlists/save', token, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function deletePlaylist(token: string, playlistId: number) {
  return request(`/api/playlists/${playlistId}`, token, { method: 'DELETE' });
}

export interface ExportResult {
  message: string;
  spotify_playlist_id: string;
  spotify_url: string;
  track_count: number;
}

export async function exportPlaylistToSpotify(
  token: string,
  playlistId: number,
  payload: { spotify_name?: string; spotify_description?: string } = {}
): Promise<ExportResult> {
  return request(`/api/playlists/${playlistId}/export-to-spotify`, token, {
    method: 'POST',
    body: JSON.stringify({ playlist_id: playlistId, ...payload }),
  });
}
