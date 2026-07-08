'use client'

import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Sparkles, Save } from 'lucide-react';
import toast from 'react-hot-toast';
import { Panel } from '@/components/ui/Panel';
import { Button } from '@/components/ui/Button';
import { Meter } from '@/components/ui/Meter';
import { LoadingMeter } from '@/components/ui/LoadingMeter';
import { RecommendationCard } from './RecommendationCard';
import { SavePlaylistModal } from './SavePlaylistModal';
import { useAuth } from '@/lib/auth-context';
import {
  generateRecommendations,
  generateMoodPlaylist,
  getUserProfile,
  RecommendationTrack,
  ListeningProfile,
  UnauthorizedError,
} from '@/lib/api-client';

const MOODS = [
  { id: 'happy', label: 'Happy', color: 'amber' as const },
  { id: 'chill', label: 'Chill', color: 'violet' as const },
  { id: 'energetic', label: 'Energetic', color: 'coral' as const },
];

export function HomeTab({ displayName }: { displayName?: string }) {
  const { token } = useAuth();
  const [profile, setProfile] = useState<ListeningProfile | null>(null);
  const [recommendations, setRecommendations] = useState<RecommendationTrack[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [currentMood, setCurrentMood] = useState<string | null>(null);
  const [showSaveModal, setShowSaveModal] = useState(false);

  useEffect(() => {
    if (!token) return;
    getUserProfile(token).then(setProfile).catch(() => {});
    handleGenerate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const handleGenerate = async () => {
    if (!token) return;
    setIsLoading(true);
    setCurrentMood(null);
    try {
      const recs = await generateRecommendations(token, { limit: 8 });
      setRecommendations(recs);
    } catch (err) {
      if (!(err instanceof UnauthorizedError)) toast.error('Could not generate recommendations');
    } finally {
      setIsLoading(false);
    }
  };

  const handleMood = async (mood: string) => {
    if (!token) return;
    setIsLoading(true);
    setCurrentMood(mood);
    try {
      const recs = await generateMoodPlaylist(token, mood, 8);
      setRecommendations(recs);
    } catch (err) {
      if (!(err instanceof UnauthorizedError)) toast.error(`Could not generate ${mood} playlist`);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display font-bold text-2xl">
          Welcome back{displayName ? `, ${displayName}` : ''}
        </h1>
        <p className="text-bone-dim text-sm mt-1">
          Fresh picks pulled from artists and albums already in your rotation.
        </p>
      </div>

      {profile && (
        <Panel className="p-5">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
            <div>
              <p className="text-xs text-bone-dim mb-1">Top genre</p>
              <p className="font-display font-semibold capitalize">
                {profile.genre_breakdown[0]?.genre || 'Still listening…'}
              </p>
            </div>
            <div>
              <p className="text-xs text-bone-dim mb-1">Taste</p>
              <p className="font-display font-semibold">{profile.popularity_profile.taste_label}</p>
            </div>
            <div>
              <Meter
                value={profile.diversity_score}
                color="violet"
                segments={10}
                label="Genre diversity"
                valueLabel={`${Math.round(profile.diversity_score * 100)}%`}
              />
            </div>
          </div>
        </Panel>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <Button onClick={handleGenerate} disabled={isLoading}>
          <Sparkles className="w-4 h-4" />
          {currentMood === null && isLoading ? 'Generating…' : 'New recommendations'}
        </Button>
        {MOODS.map((mood) => (
          <button
            key={mood.id}
            onClick={() => handleMood(mood.id)}
            disabled={isLoading}
            className={`px-4 py-2.5 rounded-xl text-sm font-medium border transition-colors disabled:opacity-40 ${
              currentMood === mood.id
                ? 'border-amber text-amber bg-amber/10'
                : 'border-panel-border text-bone-dim hover:text-bone hover:border-bone-dim'
            }`}
          >
            {mood.label}
          </button>
        ))}
        {recommendations.length > 0 && !isLoading && (
          <Button variant="secondary" onClick={() => setShowSaveModal(true)} className="ml-auto">
            <Save className="w-4 h-4" />
            Save playlist
          </Button>
        )}
      </div>

      {isLoading ? (
        <LoadingMeter label="Digging through your library…" />
      ) : recommendations.length > 0 ? (
        <motion.div
          initial="hidden"
          animate="visible"
          className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4"
        >
          {recommendations.map((track, i) => (
            <RecommendationCard key={track.id} track={track} index={i} />
          ))}
        </motion.div>
      ) : (
        <Panel className="text-center py-12">
          <p className="text-bone-dim">No recommendations yet — try generating a fresh batch.</p>
        </Panel>
      )}

      <SavePlaylistModal
        isOpen={showSaveModal}
        onClose={() => setShowSaveModal(false)}
        tracks={recommendations}
        defaultName={currentMood ? `${currentMood[0].toUpperCase()}${currentMood.slice(1)} Vibes` : `Recommendations ${new Date().toLocaleDateString()}`}
        mood={currentMood}
      />
    </div>
  );
}
