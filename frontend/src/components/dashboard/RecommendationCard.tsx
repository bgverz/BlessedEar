'use client'

import { motion } from 'framer-motion';
import { ExternalLink, Music2, Play, Pause } from 'lucide-react';
import { Meter } from '@/components/ui/Meter';
import { RecommendationTrack } from '@/lib/api-client';
import { usePlayer } from '@/lib/player-context';

export function RecommendationCard({ track, index = 0 }: { track: RecommendationTrack; index?: number }) {
  const artwork = track.album_images?.[0]?.url;
  const { currentTrack, isPlaying, toggle } = usePlayer();
  const isCurrent = currentTrack?.id === track.id;
  const isCurrentlyPlaying = isCurrent && isPlaying;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: Math.min(index * 0.04, 0.4) }}
      whileHover={{ y: -3 }}
      className={`group bg-panel border rounded-2xl overflow-hidden flex flex-col transition-colors ${
        isCurrent ? 'border-amber/60' : 'border-panel-border hover:border-amber/40'
      }`}
    >
      <div className="relative aspect-square bg-panel-light">
        {artwork ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={artwork} alt={track.album || track.name} className="w-full h-full object-cover" />
        ) : (
          <div className="w-full h-full flex items-center justify-center">
            <Music2 className="w-8 h-8 text-bone-dim" />
          </div>
        )}

        <div
          className={`absolute inset-0 bg-ink/50 flex items-center justify-center transition-opacity ${
            isCurrent ? 'opacity-100 bg-ink/30' : 'opacity-0 group-hover:opacity-100'
          }`}
        >
          {track.preview_url ? (
            <button
              onClick={() => toggle(track)}
              className="w-12 h-12 rounded-full bg-amber text-ink flex items-center justify-center shadow-glow hover:scale-105 transition-transform"
            >
              {isCurrentlyPlaying ? (
                <Pause className="w-5 h-5" fill="currentColor" />
              ) : (
                <Play className="w-5 h-5 ml-0.5" fill="currentColor" />
              )}
            </button>
          ) : (
            <span className="text-xs text-bone-dim bg-ink/60 px-2.5 py-1 rounded-full">No preview</span>
          )}
        </div>

        {track.external_urls?.spotify && (
          <a
            href={track.external_urls.spotify}
            target="_blank"
            rel="noopener noreferrer"
            className="absolute top-2 right-2 w-7 h-7 rounded-full bg-ink/60 flex items-center justify-center text-bone opacity-0 group-hover:opacity-100 hover:text-amber transition-all"
          >
            <ExternalLink className="w-3.5 h-3.5" />
          </a>
        )}

        {isCurrentlyPlaying && (
          <div className="absolute bottom-2 left-2 flex items-end gap-[2px] h-3">
            {[0.4, 1, 0.6].map((h, i) => (
              <motion.span
                key={i}
                className="w-[3px] bg-amber rounded-full"
                animate={{ scaleY: [0.3, h, 0.3] }}
                transition={{ duration: 0.7, repeat: Infinity, delay: i * 0.15 }}
                style={{ height: '100%', transformOrigin: 'bottom' }}
              />
            ))}
          </div>
        )}
      </div>

      <div className="p-3.5 flex flex-col gap-2.5">
        <div className="min-w-0">
          <p className="font-display font-semibold text-sm truncate">{track.name}</p>
          <p className="text-xs text-bone-dim truncate">{track.artists.join(', ')}</p>
        </div>
        <Meter value={track.similarity_score} segments={14} color="amber" />
        <p className="text-xs text-bone-dim italic truncate">{track.recommendation_reason}</p>
      </div>
    </motion.div>
  );
}
