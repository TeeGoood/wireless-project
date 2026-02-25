'use client';

import { useDashboardFirebase } from '@/context/DashboardFirebaseContext';
import { DashboardCard } from './DashboardCard';

function DocumentIcon() {
  return (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
    </svg>
  );
}

export function ConnectionStatisticsCard() {
  const { loading, stats } = useDashboardFirebase();
  const successfulCases = stats?.connect ?? 0;
  const unsuccessfulCases = stats?.error ?? 0;
  const totalCases = successfulCases + unsuccessfulCases;
  const solvedPercent = totalCases > 0 ? successfulCases / totalCases : 0;
  const r = 16;
  const circumference = 2 * Math.PI * r;
  const tealLength = loading ? circumference : circumference * solvedPercent;
  const redLength = loading ? 0 : circumference * (1 - solvedPercent);

  return (
    <DashboardCard
      title="Connection Statistics"
      icon={<DocumentIcon />}
    >
      <p className="text-lg sm:text-2xl font-bold text-darkTeal mb-3 sm:mb-4">{loading ? '...' : (solvedPercent * 100).toFixed(2)}% of connections are successful</p>
      <div className="flex flex-wrap items-center gap-3 sm:gap-6 min-w-0 flex-shrink-0">
        <div className="flex-shrink-0 relative w-20 h-20 sm:w-24 sm:h-24">
          <svg viewBox="0 0 36 36" className="w-full h-full -rotate-90">
            <circle cx="18" cy="18" r={r} fill="none" stroke="#CFD7C7" strokeWidth="3" />
            <circle
              cx="18"
              cy="18"
              r={r}
              fill="none"
              stroke="#DC2626"
              strokeWidth="3"
              strokeDasharray={`0 ${tealLength} ${redLength}`}
              strokeLinecap="round"
            />
            <circle
              cx="18"
              cy="18"
              r={r}
              fill="none"
              stroke="#70A9A1"
              strokeWidth="3"
              strokeDasharray={`${tealLength} ${redLength}`}
              strokeLinecap="round"
            />
          </svg>
        </div>
        <div className="text-xs sm:text-sm min-w-0 leading-snug py-0.5">
          <p className="text-darkTeal font-medium">{successfulCases} successful connections</p>
          <p className="text-red-600">{unsuccessfulCases} unsuccessful connections</p>
        </div>
      </div>
    </DashboardCard>
  );
}
