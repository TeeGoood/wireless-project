'use client';

interface DashboardCardProps {
  title: string;
  icon: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}

export function DashboardCard({ title, icon, children, className = '' }: DashboardCardProps) {
  const isFill = className.includes('h-full');
  return (
    <div className={`bg-white rounded-2xl border-2 border-[#ABB4B3] p-4 sm:p-6 min-w-0 ${isFill ? 'flex flex-col min-h-0 flex-1 overflow-hidden' : 'overflow-x-hidden'} ${className}`}>
      <div className="flex items-center gap-2 mb-3 sm:mb-4 flex-shrink-0 min-w-0">
        <span className="text-darkTeal flex-shrink-0" aria-hidden>{icon}</span>
        <h2 className="text-base sm:text-lg font-semibold text-black truncate">{title}</h2>
      </div>
      <div className="border-b-2 border-[#ABB4B3] -mx-4 sm:-mx-6 mb-3 sm:mb-4 flex-shrink-0" aria-hidden />
      <div className={isFill ? 'flex-1 min-h-0 min-w-0 flex flex-col overflow-hidden' : ''}>
        {children}
      </div>
    </div>
  );
}
