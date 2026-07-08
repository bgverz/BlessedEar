'use client'

import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Save } from 'lucide-react';
import toast from 'react-hot-toast';
import { Panel } from '@/components/ui/Panel';
import { Button } from '@/components/ui/Button';
import { LoadingMeter } from '@/components/ui/LoadingMeter';
import { RecommendationCard } from './RecommendationCard';
import { SavePlaylistModal } from './SavePlaylistModal';
import { useAuth } from '@/lib/auth-context';
import { discoverMusic, RecommendationTrack, UnauthorizedError } from '@/lib/api-client';

const DISCOVER_TYPES: { id: 'similar' | 'new-genres' | 'trending' | 'deep-cuts'; label: string; description: string }[] = [
  { id: 'similar', label: 'Similar', description: 'Deep cuts from artists and albums you already play' },
  { id: 'new-genres', label: 'New genres', description: 'Tracks from genres outside your usual rotation' },
  { id: 'trending', label: 'Trending', description: 'Higher-energy picks in a party mood' },
  { id: 'deep-cuts', label: 'Deep cuts', description: 'Lower-key tracks for background listening' },
];

export function DiscoverTab() {
  const { token } = useAuth();
  const [activeType, setActiveType] = useState<typeof DISCOVER_TYPES[number]['id']>('similar');
  const [tracks, setTracks] = useState<RecommendationTrack[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [showSaveModal, setShowSaveModal] = useState(false);

  useEffect(() => {
    if (!token) return;
    load(activeType);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, activeType]);

  const load = async (type: typeof activeType) => {
    if (!token) return;
    setIsLoading(true);
    try {
      const result = await discoverMusic(token, type, 12);
      setTracks(result);
    } catch (err) {
      if (!(err instanceof UnauthorizedError)) toast.error('Could not load discovery tracks');
    } finally {
      setIsLoading(false);
    }
  };

  const activeMeta = DISCOVER_TYPES.find((t) => t.id === activeType)!;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display font-bold text-3xl sm:text-4xl tracking-tight">Discover</h1>
        <p className="text-bone-dim text-sm mt-1">{activeMeta.description}</p>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        {DISCOVER_TYPES.map((type) => (
          <button
            key={type.id}
            onClick={() => setActiveType(type.id)}
            className={`px-4 py-2.5 rounded-xl text-sm font-medium border transition-colors ${
              activeType === type.id
                ? 'border-amber text-amber bg-amber/10'
                : 'border-panel-border text-bone-dim hover:text-bone hover:border-bone-dim'
            }`}
          >
            {type.label}
          </button>
        ))}
        {tracks.length > 0 && !isLoading && (
          <Button variant="secondary" onClick={() => setShowSaveModal(true)} className="ml-auto">
            <Save className="w-4 h-4" />
            Save playlist
          </Button>
        )}
      </div>

      {isLoading ? (
        <LoadingMeter label="Scanning for new tracks…" />
      ) : tracks.length > 0 ? (
        <motion.div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {tracks.map((track, i) => (
            <RecommendationCard key={track.id} track={track} index={i} />
          ))}
        </motion.div>
      ) : (
        <Panel className="text-center py-12">
          <p className="text-bone-dim">Nothing here yet — try another discovery type.</p>
        </Panel>
      )}

      <SavePlaylistModal
        isOpen={showSaveModal}
        onClose={() => setShowSaveModal(false)}
        tracks={tracks}
        defaultName={`${activeMeta.label} — ${new Date().toLocaleDateString()}`}
        mood={null}
      />
    </div>
  );
}
