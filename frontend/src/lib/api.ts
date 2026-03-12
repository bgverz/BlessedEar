const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export interface UserProfile {
  user_id: string;
  avg_features: {
    danceability: number;
    energy: number;
    valence: number;
    speechiness: number;
    acousticness: number;
    instrumentalness: number;
    liveness: number;
    tempo: number;
  };
  feature_std: Record<string, number>;
  top_genres: string[];
  total_tracks_analyzed: number;
  created_at: string;
}

export interface RecommendationTrack {
  id: string;
  name: string;
  artists: string[];
  album: string;
  preview_url?: string;
  external_urls: Record<string, string>;
  audio_features: Record<string, number>;
  similarity_score: number;
  recommendation_reason: string;
}

export async function getCurrentUser(token: string) {
  try {
    const response = await fetch(`${API_BASE}/api/auth/me`, {
      headers: {
        'Authorization': `Bearer ${token}`,
      },
    });
    if (!response.ok) throw new Error('Failed to get user');
    return await response.json();
  } catch (error) {
    console.error('Error getting current user:', error);
    return null;
  }
}

export async function getUserProfile(token: string): Promise<UserProfile | null> {
  try {
    const response = await fetch(`${API_BASE}/api/recommendations/profile`, {
      headers: {
        'Authorization': `Bearer ${token}`,
      },
    });
    if (!response.ok) throw new Error('Failed to get profile');
    return await response.json();
  } catch (error) {
    console.error('Error getting user profile:', error);
    return null;
  }
}

export async function generateRecommendations(
  token: string, 
  options: {
    seed_tracks?: string[];
    target_features?: Record<string, number>;
    limit?: number;
  } = {}
): Promise<RecommendationTrack[]> {
  try {
    const response = await fetch(`${API_BASE}/api/recommendations/generate`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        limit: 10,
        ...options,
      }),
    });
    if (!response.ok) throw new Error('Failed to generate recommendations');
    const data = await response.json();
    return data.tracks || [];
  } catch (error) {
    console.error('Error generating recommendations:', error);
    return [];
  }
}

export async function generateMoodPlaylist(
  token: string,
  mood: string,
  limit: number = 10
): Promise<RecommendationTrack[]> {
  try {
    const response = await fetch(`${API_BASE}/api/recommendations/mood-playlist`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ mood, limit }),
    });
    if (!response.ok) throw new Error('Failed to generate mood playlist');
    const data = await response.json();
    return data.tracks || [];
  } catch (error) {
    console.error('Error generating mood playlist:', error);
    return [];
  }
}

export async function getTopTracks(
  token: string,
  timeRange: 'short_term' | 'medium_term' | 'long_term' = 'medium_term',
  limit: number = 20
) {
  try {
    const response = await fetch(
      `${API_BASE}/api/recommendations/top-tracks?time_range=${timeRange}&limit=${limit}`,
      {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      }
    );
    if (!response.ok) throw new Error('Failed to get top tracks');
    return await response.json();
  } catch (error) {
    console.error('Error getting top tracks:', error);
    return { top_tracks: [] };
  }
}
