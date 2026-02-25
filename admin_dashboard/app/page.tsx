'use client';

import { PageFrame } from '@/components/PageFrame';
import { TotalUsersCard } from '@/components/TotalUsersCard';
import { GraphicStatisticsCard } from '@/components/GraphicStatisticsCard';
import { CaseStatisticsCard } from '@/components/CaseStatisticsCard';

export default function MainDashboardPage() {
  const handleRefresh = () => window.location.reload();

  return (
    <PageFrame title="Main Dashboard" onRefresh={handleRefresh}>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 sm:gap-6 min-h-0 flex-1 min-w-0 w-full max-w-full overflow-hidden">
        <div className="flex flex-col gap-4 sm:gap-6 min-h-0 min-w-0 overflow-x-hidden">
          <TotalUsersCard online={2} offline={0} />
          <CaseStatisticsCard />
        </div>
        <div className="min-h-0 min-w-0 flex flex-col h-full overflow-hidden">
          <GraphicStatisticsCard className="h-full" />
        </div>
      </div>
    </PageFrame>
  );
}
