'use client';

import { DashboardCard } from './DashboardCard';

function BanIcon() {
  return (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" />
    </svg>
  );
}

export function BannedUsersCard() {
  return (
    <DashboardCard
      title="Banned Users"
      icon={<BanIcon />}
    >
      <div className="min-h-[120px] flex items-center justify-center text-mutedTeal text-sm">
        No banned users
      </div>
    </DashboardCard>
  );
}
