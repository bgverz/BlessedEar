'use client'

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { AnimatePresence, motion } from 'framer-motion';
import { AuthProvider, useAuth } from '@/lib/auth-context';
import { getCurrentUser, CurrentUser, UnauthorizedError } from '@/lib/api-client';
import { Sidebar, DashboardTab } from '@/components/layout/Sidebar';
import { LoadingMeter } from '@/components/ui/LoadingMeter';
import { HomeTab } from '@/components/dashboard/HomeTab';
import { DiscoverTab } from '@/components/dashboard/DiscoverTab';
import { AnalyticsTab } from '@/components/dashboard/AnalyticsTab';
import { PlaylistsTab } from '@/components/dashboard/PlaylistsTab';

function DashboardShell() {
  const { token, isLoading } = useAuth();
  const router = useRouter();
  const [activeTab, setActiveTab] = useState<DashboardTab>('home');
  const [user, setUser] = useState<CurrentUser | null>(null);

  useEffect(() => {
    if (!isLoading && !token) {
      router.replace('/login');
    }
  }, [isLoading, token, router]);

  useEffect(() => {
    if (!token) return;
    getCurrentUser(token)
      .then(setUser)
      .catch((err) => {
        if (!(err instanceof UnauthorizedError)) console.error(err);
      });
  }, [token]);

  if (isLoading || !token) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-ink">
        <LoadingMeter />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-ink">
      <Sidebar activeTab={activeTab} setActiveTab={setActiveTab} displayName={user?.display_name} />
      <main className="ml-60 px-8 py-10 max-w-6xl">
        <AnimatePresence mode="wait">
          <motion.div
            key={activeTab}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.18 }}
          >
            {activeTab === 'home' && <HomeTab displayName={user?.display_name} />}
            {activeTab === 'discover' && <DiscoverTab />}
            {activeTab === 'analytics' && <AnalyticsTab />}
            {activeTab === 'playlists' && <PlaylistsTab />}
          </motion.div>
        </AnimatePresence>
      </main>
    </div>
  );
}

export default function DashboardPage() {
  return (
    <AuthProvider>
      <DashboardShell />
    </AuthProvider>
  );
}
