'use client';

import { useState, useEffect, useCallback, useMemo } from 'react';
import { getFirebaseValue } from '@/lib/firebase';
import type { UsersMap } from '@/lib/firebase-types';
import { DashboardFirebaseProvider, computeOnlineCount } from '@/context/DashboardFirebaseContext';

function RefreshIcon() {
  return (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
    </svg>
  );
}

function formatPageDate(date: Date): string {
  const day = date.getDate();
  const suffix = day === 1 || day === 21 || day === 31 ? 'st' : day === 2 || day === 22 ? 'nd' : day === 3 || day === 23 ? 'rd' : 'th';
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  return `${day}${suffix} ${months[date.getMonth()]} ${date.getFullYear()}`;
}

export interface PageBoxProps {
  /** Page title shown in the header */
  title: string;
  /** Content (detail) rendered inside the box below the divider */
  children: React.ReactNode;
  onRefresh?: () => void;
}

export function PageBox({ title, children, onRefresh }: PageBoxProps) {
  const dateStr = formatPageDate(new Date());
  const [firebaseUsers, setFirebaseUsers] = useState<UsersMap | null>(null);
  const [firebaseLoading, setFirebaseLoading] = useState<boolean>(true);
  const [firebaseError, setFirebaseError] = useState<string | null>(null);

  const fetchFirebase = useCallback(async () => {
    setFirebaseError(null);
    setFirebaseLoading(true);
    try {
      const users = await getFirebaseValue<UsersMap>('online');
      setFirebaseUsers(users);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to fetch';
      setFirebaseError(msg);
    } finally {
      setFirebaseLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchFirebase();
    const interval = setInterval(fetchFirebase, 5000);
    return () => clearInterval(interval);
  }, [fetchFirebase]);

  const handleRefresh = () => {
    fetchFirebase();
    onRefresh?.();
  };

  const firebaseContextValue = useMemo(
    () => ({
      users: firebaseUsers,
      onlineCount: computeOnlineCount(firebaseUsers),
      loading: firebaseLoading,
      error: firebaseError,
      refresh: () => {
        fetchFirebase();
        onRefresh?.();
      },
    }),
    [firebaseUsers, firebaseLoading, firebaseError, fetchFirebase, onRefresh]
  );

  return (
    <DashboardFirebaseProvider value={firebaseContextValue}>
      <div className="flex-1 min-w-0 min-h-0 bg-white rounded-2xl shadow-md border border-lightGrey/40 p-4 sm:p-6 flex flex-col overflow-hidden">
        <header className="flex-shrink-0 flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3 mb-4 sm:mb-6">
          <div className="min-w-0">
            <h1 className="text-xl sm:text-2xl font-bold text-black truncate">{title}</h1>
            <p className="text-sm text-black mt-1">{dateStr}</p>
          </div>
          <button
            type="button"
            onClick={handleRefresh}
            className="flex-shrink-0 self-start sm:self-auto p-2 rounded-full bg-lightGrey/40 text-darkTeal hover:bg-lightGrey/60 transition-colors w-fit"
            aria-label="Refresh"
          >
            <RefreshIcon />
          </button>
        </header>
        <div className="-mx-4 sm:-mx-6 border-b-2 border-[#ABB4B3] mb-4 sm:mb-6" aria-hidden />
        <div className="flex-1 min-h-0 min-w-0 overflow-y-auto overflow-x-hidden flex flex-col">{children}</div>
      </div>
    </DashboardFirebaseProvider>
  );
}
