'use client';

import { createContext, useContext, type ReactNode } from 'react';
import type { StatsMap, StatsStruct, UsersMap } from '@/lib/firebase-types';

export interface DashboardFirebaseValue {
  users: UsersMap | null;
  stats: StatsStruct | null;
  onlineCount: number;
  loading: boolean;
  error: string | null;
  refresh: () => void;
}

const defaultValue: DashboardFirebaseValue = {
  users: null,
  stats: null,
  onlineCount: 0,
  loading: true,
  error: null,
  refresh: () => {},
};

const DashboardFirebaseContext = createContext<DashboardFirebaseValue>(defaultValue);

export function useDashboardFirebase(): DashboardFirebaseValue {
  const ctx = useContext(DashboardFirebaseContext);
  return ctx ?? defaultValue;
}

function computeOnlineCount(users: UsersMap | null): number {
  if (!users || typeof users !== 'object') return 0;
  return Object.entries(users).filter(
    ([, u]) => u && typeof u === 'object' && 'car_id' in u
  ).length;
}

export function computeAggregatedStats(stats: StatsMap | null): StatsStruct | null {
  if (!stats || typeof stats !== 'object') return null;
  const aggregated: StatsStruct = { connect: 0, error: 0, getInfo: 0, sendSound: 0, sounds: {}, maxSound: 0 };
  for (const entry of Object.values(stats)) {
    if (entry && typeof entry === 'object') {
      aggregated.connect += Number(entry.connect ?? 0);
      aggregated.error += Number(entry.error ?? 0);
      aggregated.getInfo += Number(entry.getInfo ?? 0);
      aggregated.sendSound += Number(entry.sendSound ?? 0);
      for (const [key, count] of Object.entries(entry.sounds ?? {})) {
        aggregated.sounds[key] = (aggregated.sounds[key] ?? 0) + count;
        if (aggregated.sounds[key] > aggregated.maxSound) aggregated.maxSound = aggregated.sounds[key];
      }
    }
  }
  return aggregated;
}

export interface DashboardFirebaseProviderProps {
  value: DashboardFirebaseValue;
  children: ReactNode;
}

export function DashboardFirebaseProvider({ value, children }: DashboardFirebaseProviderProps) {
  return (
    <DashboardFirebaseContext.Provider value={value}>
      {children}
    </DashboardFirebaseContext.Provider>
  );
}

export { computeOnlineCount };
