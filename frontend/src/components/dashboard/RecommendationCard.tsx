'use client'

import { motion } from 'framer-motion';
import { ExternalLink, Music2 } from 'lucide-react';
import { Meter } from '@/components/ui/Meter';
import { RecommendationTrack } from '@/lib/api-client';

export function RecommendationCard({ track, index = 0 }: { track: RecommendationTrack; index?: number }) {
  const artwork = track.album_images?.[track.album_images.length - 1]?.url;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: Math.min(index * 0.04, 0.4) }}
      whileHover={{ y: -2 }}
      className="group bg-panel border border-panel-border rounded-2xl p-4 flex flex-col gap-3 transition-colors hover:border-amber/40"
    >
      <div className="flex items-center gap-3">
        <div className="w-12 h-12 rounded-lg bg-panel-light flex items-center justify-center overflow-hidden shrink-0">
          {artwork ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={artwork} alt={track.album || track.name} className="w-full h-full object-cover" />
          ) : (
            <Music2 className="w-5 h-5 text-bone-dim" />
          )}
        </div>
        <div className="min-w-0 flex-1">
          <p className="font-display font-semibold text-sm truncate">{track.name}</p>
          <p className="text-xs text-bone-dim truncate">{track.artists.join(', ')}</p>
        </div>
        {track.external_urls?.spotify && (
          <a
            href={track.external_urls.spotify}
            target="_blank"
            rel="noopener noreferrer"
            className="shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-bone-dim opacity-0 group-hover:opacity-100 hover:text-amber hover:bg-panel-light transition-all"
          >
            <ExternalLink className="w-3.5 h-3.5" />
          </a>
        )}
      </div>

      <Meter value={track.similarity_score} segments={16} color="amber" />
      <p className="text-xs text-bone-dim italic">{track.recommendation_reason}</p>
    </motion.div>
  );
}
