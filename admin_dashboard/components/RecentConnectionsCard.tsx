'use client';

import { DashboardCard } from './DashboardCard';

function BroadcastIcon() {
  return (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.536 8.464a5 5 0 010 7.072m2.828-9.9a9 9 0 010 12.728M5.586 15.536a5 5 0 001.414 1.414m2.828-9.9a9 9 0 012.828-2.828" />
    </svg>
  );
}

export function RecentConnectionsCard() {
  return (
    <DashboardCard
      title="Recent Connections"
      icon={<BroadcastIcon />}
    >
      <div className="min-h-[120px] flex items-center justify-center text-mutedTeal text-sm">
        No recent connections
      </div>
    </DashboardCard>
  );
}
