'use client';

import { DashboardCard } from './DashboardCard';

function UsersIcon() {
  return (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" />
    </svg>
  );
}

interface TotalUsersCardProps {
  online?: number;
  offline?: number;
}

export function TotalUsersCard({ online = 2, offline = 0 }: TotalUsersCardProps) {
  return (
    <DashboardCard
      title="Total Users"
      icon={<UsersIcon />}
    >
      <p className="text-2xl font-bold text-darkTeal">{online} Online Users</p>
      <p className="text-sm text-mutedTeal mt-1">{offline} offline</p>
      <p className="text-xs text-mutedTeal mt-3">
        If the status is not up to date, you may need to reload this page.
      </p>
    </DashboardCard>
  );
}
