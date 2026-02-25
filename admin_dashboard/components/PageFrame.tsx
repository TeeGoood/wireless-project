'use client';

import { useAuth } from '@/context/AuthContext';
import { Sidebar } from './Sidebar';
import { PageBox } from './PageBox';
import { LoginPopup } from './LoginPopup';

export interface PageFrameProps {
  /** Page title (passed to PageBox) */
  title: string;
  /** Detail content inside the page box */
  children: React.ReactNode;
  onRefresh?: () => void;
}

export function PageFrame({ title, children, onRefresh }: PageFrameProps) {
  const { isLogin } = useAuth();

  return (
    <div className="h-screen max-h-screen overflow-hidden overflow-x-hidden flex gap-3 sm:gap-6 p-3 sm:p-6 bg-[#D0DBDA] min-w-0">
      <Sidebar />
      <PageBox title={title} onRefresh={onRefresh}>
        {children}
      </PageBox>
      {!isLogin && <LoginPopup />}
    </div>
  );
}
