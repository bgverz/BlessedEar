'use client'

import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Clock, Star } from 'lucide-react';
import toast from 'react-hot-toast';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';
import { Panel } from '@/components/ui/Panel';
import { Meter } from '@/components/ui/Meter';
import { LoadingMeter } from '@/components/ui/LoadingMeter';
import { useAuth } from '@/lib/auth-context';
import { getListeningProfile, getTopTracks, ListeningProfile, TopTrack, UnauthorizedError } from '@/lib/api-client';

const TIME_RANGES: { id: 'short_term' | 'medium_term' | 'long_term'; label: string }[] = [
  { id: 'short_term', label: 'Last 4 weeks' },
  { id: 'medium_term', label: 'Last 6 months' },
  { id: 'long_term', label: 'All time' },
];

const GENRE_COLORS: Array<'amber' | 'coral' | 'violet'> = ['amber', 'coral', 'violet'];

export function AnalyticsTab() {
  const { token } = useAuth();
  const [profile, setProfile] = useState<ListeningProfile | null>(null);
  const [isLoadingProfile, setIsLoadingProfile] = useState(true);
  const [timeRange, setTimeRange] = useState<'short_term' | 'medium_term' | 'long_term'>('medium_term');
  const [topTracks, setTopTracks] = useState<TopTrack[]>([]);
  const [isLoadingTracks, setIsLoadingTracks] = useState(false);

  useEffect(() => {
    if (!token) return;
    setIsLoadingProfile(true);
    getListeningProfile(token)
      .then(setProfile)
      .catch((err) => {
        if (!(err instanceof UnauthorizedError)) toast.error('Could not load listening profile');
      })
      .finally(() => setIsLoadingProfile(false));
  }, [token]);

  useEffect(() => {
    if (!token) return;
    setIsLoadingTracks(true);
    getTopTracks(token, timeRange, 10)
      .then((data) => setTopTracks(data.top_tracks || []))
      .catch((err) => {
        if (!(err instanceof UnauthorizedError)) toast.error('Could not load top tracks');
      })
      .finally(() => setIsLoadingTracks(false));
  }, [token, timeRange]);

  if (isLoadingProfile) {
    return <LoadingMeter label="Analyzing your listening history…" />;
  }

  if (!profile) {
    return (
      <Panel className="text-center py-12">
        <p className="text-bone-dim">Not enough listening data yet — come back after you've played a bit more.</p>
      </Panel>
    );
  }

  const maxEraCount = Math.max(...profile.era_distribution.map((e) => e.count), 1);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display font-bold text-3xl sm:text-4xl tracking-tight">Sound Profile</h1>
        <p className="text-bone-dim text-sm mt-1">
          Built from your real genre, era, and popularity signals — not simulated audio features.
        </p>
      </div>

      {profile.insights && profile.insights.length > 0 && (
        <Panel className="p-5">
          <ul className="space-y-2">
            {profile.insights.map((insight, i) => (
              <li key={i} className="text-sm text-bone flex items-start gap-2.5">
                <span className="w-1.5 h-1.5 rounded-full bg-amber mt-1.5 shrink-0" />
                {insight}
              </li>
            ))}
          </ul>
        </Panel>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Panel>
          <h3 className="font-display font-semibold mb-4">Genre breakdown</h3>
          {profile.genre_breakdown.length > 0 ? (
            <div className="space-y-3.5">
              {profile.genre_breakdown.slice(0, 8).map((g, i) => (
                <Meter
                  key={g.genre}
                  value={g.share}
                  segments={16}
                  color={GENRE_COLORS[i % GENRE_COLORS.length]}
                  label={g.genre}
                  valueLabel={`${Math.round(g.share * 100)}%`}
                  delay={i * 0.05}
                />
              ))}
            </div>
          ) : (
            <p className="text-sm text-bone-dim">No genre data yet.</p>
          )}
        </Panel>

        <div className="space-y-6">
          <Panel>
            <h3 className="font-display font-semibold mb-4">Mainstream vs. niche</h3>
            <Meter
              value={profile.popularity_profile.avg_track_popularity / 100}
              color="coral"
              segments={20}
              valueLabel={profile.popularity_profile.taste_label}
            />
            <div className="flex justify-between text-xs text-bone-dim mt-2">
              <span>Deep cuts</span>
              <span>Mainstream</span>
            </div>
          </Panel>

          <Panel>
            <h3 className="font-display font-semibold mb-4">Taste shift</h3>
            <Meter
              value={profile.taste_shift.new_artist_share}
              color="violet"
              segments={20}
              valueLabel={`${Math.round(profile.taste_shift.new_artist_share * 100)}% new`}
            />
            <p className="text-xs text-bone-dim mt-2">{profile.taste_shift.description}</p>
          </Panel>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Panel>
          <h3 className="font-display font-semibold mb-4">Eras you listen to</h3>
          {profile.era_distribution.length > 0 ? (
            <div className="flex items-end gap-3 h-32">
              {profile.era_distribution.map((era) => (
                <div key={era.decade} className="flex-1 flex flex-col items-center gap-2 h-full justify-end">
                  <motion.div
                    initial={{ height: 0 }}
                    animate={{ height: `${Math.max((era.count / maxEraCount) * 100, 6)}%` }}
                    transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
                    className="w-full rounded-t-md bg-amber/70"
                  />
                  <span className="text-[11px] font-mono text-bone-dim">{era.decade}</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-bone-dim">No era data yet.</p>
          )}
        </Panel>

        <Panel>
          <h3 className="font-display font-semibold mb-4">Library growth</h3>
          {profile.activity_trend.length > 0 ? (
            <ResponsiveContainer width="100%" height={140}>
              <BarChart data={profile.activity_trend}>
                <CartesianGrid strokeDasharray="3 3" stroke="#38333F" vertical={false} />
                <XAxis dataKey="month" tick={{ fill: '#B8B2C4', fontSize: 11 }} axisLine={{ stroke: '#38333F' }} tickLine={false} />
                <YAxis tick={{ fill: '#B8B2C4', fontSize: 11 }} axisLine={false} tickLine={false} allowDecimals={false} />
                <Tooltip
                  contentStyle={{ background: '#211E29', border: '1px solid #38333F', borderRadius: 8, fontSize: 12 }}
                  labelStyle={{ color: '#F2EDE4' }}
                  cursor={{ fill: '#2C2836' }}
                />
                <Bar dataKey="tracks_added" fill="#E8A33D" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-sm text-bone-dim">Not enough saved-track history yet.</p>
          )}
        </Panel>
      </div>

      {profile.most_played_artists.length > 0 && (
        <Panel>
          <h3 className="font-display font-semibold mb-4">Most played artists</h3>
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-4">
            {profile.most_played_artists.slice(0, 10).map((artist) => (
              <div key={artist.id} className="flex flex-col items-center text-center gap-2">
                <div className="w-16 h-16 rounded-full bg-panel-light overflow-hidden">
                  {artist.image && (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={artist.image} alt={artist.name} className="w-full h-full object-cover" />
                  )}
                </div>
                <p className="text-xs font-medium truncate w-full">{artist.name}</p>
                <p className="text-[11px] text-bone-dim font-mono">{artist.count} plays</p>
              </div>
            ))}
          </div>
        </Panel>
      )}

      <Panel>
        <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
          <h3 className="font-display font-semibold">Top tracks</h3>
          <div className="flex gap-2">
            {TIME_RANGES.map((range) => (
              <button
                key={range.id}
                onClick={() => setTimeRange(range.id)}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                  timeRange === range.id ? 'bg-amber text-ink' : 'bg-panel-light text-bone-dim hover:text-bone'
                }`}
              >
                <Clock className="w-3 h-3" />
                {range.label}
              </button>
            ))}
          </div>
        </div>

        {isLoadingTracks ? (
          <LoadingMeter />
        ) : topTracks.length > 0 ? (
          <div className="space-y-2">
            {topTracks.map((track, i) => (
              <div key={track.id} className="flex items-center gap-3 p-2.5 rounded-xl hover:bg-panel-light transition-colors">
                <span className="w-6 text-center text-xs font-mono text-bone-dim">{i + 1}</span>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium truncate">{track.name}</p>
                  <p className="text-xs text-bone-dim truncate">{track.artists.map((a) => a.name).join(', ')}</p>
                </div>
                {track.popularity != null && (
                  <div className="flex items-center gap-1 text-xs text-bone-dim shrink-0">
                    <Star className="w-3 h-3 text-amber fill-amber" />
                    {track.popularity}
                  </div>
                )}
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-bone-dim text-center py-6">No top tracks for this period.</p>
        )}
      </Panel>
    </div>
  );
}
