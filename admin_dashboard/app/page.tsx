'use client';

import { PageFrame } from '@/components/PageFrame';
import { TotalUsersCard } from '@/components/TotalUsersCard';
import { SoundStatisticsCard } from '@/components/SoundStatisticsCard';
import {ConnectionStatisticsCard } from '@/components/ConnectionStatisticsCard';

export default function MainDashboardPage() {
  const handleRefresh = () => window.location.reload();

  return (
    <PageFrame title="Main Dashboard" onRefresh={handleRefresh}>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 sm:gap-6 min-h-0 flex-1 min-w-0 w-full max-w-full overflow-hidden">
        <div className="flex flex-col gap-4 sm:gap-6 min-h-0 min-w-0 overflow-x-hidden">
          <TotalUsersCard />
          <ConnectionStatisticsCard />
        </div>
        <div className="min-h-0 min-w-0 flex flex-col h-full overflow-hidden">
          <SoundStatisticsCard className="h-full" />
        </div>
      </div>
    </PageFrame>
  );
}
