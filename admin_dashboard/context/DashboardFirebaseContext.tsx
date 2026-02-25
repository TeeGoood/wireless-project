'use client';

import { createContext, useContext, type ReactNode } from 'react';
import type { UsersMap } from '@/lib/firebase-types';

export interface DashboardFirebaseValue {
  users: UsersMap | null;
  onlineCount: number;
  loading: boolean;
  error: string | null;
  refresh: () => void;
}

const defaultValue: DashboardFirebaseValue = {
  users: null,
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
