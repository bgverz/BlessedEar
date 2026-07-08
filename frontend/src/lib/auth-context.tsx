'use client'

import { createContext, useContext, useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { API_BASE, TOKEN_STORAGE_KEY } from './api-client';

interface AuthContextValue {
  token: string | null;
  isLoading: boolean;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const urlToken = params.get('token');
    const isFresh = params.get('fresh');

    if (urlToken) {
      if (isFresh) {
        localStorage.clear();
      }
      localStorage.setItem(TOKEN_STORAGE_KEY, urlToken);
      setToken(urlToken);
      window.history.replaceState({}, '', window.location.pathname);
    } else {
      setToken(localStorage.getItem(TOKEN_STORAGE_KEY));
    }
    setIsLoading(false);
  }, []);

  const logout = useCallback(async () => {
    const current = localStorage.getItem(TOKEN_STORAGE_KEY);
    localStorage.removeItem(TOKEN_STORAGE_KEY);
    setToken(null);
    if (current) {
      try {
        await fetch(`${API_BASE}/api/auth/logout`, {
          method: 'POST',
          headers: { Authorization: `Bearer ${current}` },
        });
      } catch {
        // best effort — client-side token is already cleared
      }
    }
    router.push('/login');
  }, [router]);

  return <AuthContext.Provider value={{ token, isLoading, logout }}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
