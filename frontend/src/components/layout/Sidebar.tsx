'use client'

import { motion } from 'framer-motion';
import { LayoutGrid, Compass, ListMusic, TrendingUp, LogOut, AudioLines } from 'lucide-react';
import { useAuth } from '@/lib/auth-context';

export type DashboardTab = 'home' | 'discover' | 'playlists' | 'analytics';

const TABS: { id: DashboardTab; label: string; icon: typeof LayoutGrid }[] = [
  { id: 'home', label: 'Home', icon: LayoutGrid },
  { id: 'discover', label: 'Discover', icon: Compass },
  { id: 'playlists', label: 'Playlists', icon: ListMusic },
  { id: 'analytics', label: 'Analytics', icon: TrendingUp },
];

export function Sidebar({
  activeTab,
  setActiveTab,
  displayName,
}: {
  activeTab: DashboardTab;
  setActiveTab: (tab: DashboardTab) => void;
  displayName?: string;
}) {
  const { logout } = useAuth();

  return (
    <aside className="fixed left-0 top-0 h-full w-60 bg-ink-light border-r border-panel-border flex flex-col z-20">
      <div className="flex items-center gap-2.5 px-6 py-6">
        <div className="w-8 h-8 rounded-lg bg-amber flex items-center justify-center">
          <AudioLines className="w-4.5 h-4.5 text-ink" strokeWidth={2.5} />
        </div>
        <span className="font-display font-bold text-lg tracking-tight">BlessedEar</span>
      </div>

      <nav className="flex-1 px-3 space-y-1">
        {TABS.map((tab) => {
          const isActive = activeTab === tab.id;
          const Icon = tab.icon;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`relative w-full flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-sm font-medium transition-colors duration-150 ${
                isActive ? 'text-bone' : 'text-bone-dim hover:text-bone hover:bg-panel-light'
              }`}
            >
              {isActive && (
                <motion.div
                  layoutId="sidebar-active"
                  className="absolute inset-0 bg-panel-light rounded-xl"
                  transition={{ type: 'spring', stiffness: 380, damping: 32 }}
                />
              )}
              <span className="relative flex items-center gap-3">
                {isActive && <span className="absolute -left-3.5 h-4 w-[3px] rounded-full bg-amber" />}
                <Icon className="w-4 h-4" strokeWidth={2} />
                {tab.label}
              </span>
            </button>
          );
        })}
      </nav>

      <div className="px-3 pb-5 pt-3 border-t border-panel-border mx-3">
        <div className="px-3.5 py-2 mb-1">
          <p className="text-xs text-bone-dim">Signed in as</p>
          <p className="text-sm font-medium truncate">{displayName || 'Listener'}</p>
        </div>
        <button
          onClick={() => logout()}
          className="w-full flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-sm font-medium text-bone-dim hover:text-coral hover:bg-coral/10 transition-colors duration-150"
        >
          <LogOut className="w-4 h-4" strokeWidth={2} />
          Log out
        </button>
      </div>
    </aside>
  );
}
