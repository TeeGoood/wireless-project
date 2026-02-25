'use client';

import { PageFrame } from '@/components/PageFrame';
import { BannedUsersCard } from '@/components/BannedUsersCard';
import { RecentConnectionsCard } from '@/components/RecentConnectionsCard';

export default function HistoryPage() {
  const handleRefresh = () => window.location.reload();

  return (
    <PageFrame title="History" onRefresh={handleRefresh}>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <BannedUsersCard />
        <RecentConnectionsCard />
      </div>
    </PageFrame>
  );
}
