'use client';

import { PageFrame } from '@/components/PageFrame';
import { ReportedUsersTable } from '@/components/ReportedUsersTable';

export default function AdminPanelPage() {
  const handleRefresh = () => window.location.reload();

  return (
    <PageFrame title="Admin Panel" onRefresh={handleRefresh}>
      <ReportedUsersTable />
    </PageFrame>
  );
}
