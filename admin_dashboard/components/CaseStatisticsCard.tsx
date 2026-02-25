'use client';

import { DashboardCard } from './DashboardCard';

function DocumentIcon() {
  return (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
    </svg>
  );
}

const successfulCases = 486;
const unsuccessfulCases = 24;
const solvedPercent = successfulCases / (successfulCases + unsuccessfulCases);
const successAngle = solvedPercent * 360;

export function CaseStatisticsCard() {
  return (
    <DashboardCard
      title="Case Statistics"
      icon={<DocumentIcon />}
    >
      <p className="text-lg sm:text-2xl font-bold text-darkTeal mb-3 sm:mb-4">{(solvedPercent * 100).toFixed(2)}% of cases are solved</p>
      <div className="flex flex-wrap items-center gap-3 sm:gap-6 min-w-0 flex-shrink-0">
        <div className="flex-shrink-0 relative w-20 h-20 sm:w-24 sm:h-24">
          <svg viewBox="0 0 36 36" className="w-full h-full -rotate-90">
            <circle cx="18" cy="18" r="16" fill="none" stroke="#CFD7C7" strokeWidth="3" />
            <circle
              cx="18"
              cy="18"
              r="16"
              fill="none"
              stroke="#70A9A1"
              strokeWidth="3"
              strokeDasharray={`${successAngle} ${360 - successAngle}`}
              strokeLinecap="round"
            />
            <circle
              cx="18"
              cy="18"
              r="16"
              fill="none"
              stroke="#DC2626"
              strokeWidth="3"
              strokeDasharray={`${360 - successAngle} ${successAngle}`}
              strokeLinecap="round"
              style={{ strokeDashoffset: -successAngle }}
            />
          </svg>
        </div>
        <div className="text-xs sm:text-sm min-w-0 leading-snug py-0.5">
          <p className="text-darkTeal font-medium">{successfulCases} successful cases</p>
          <p className="text-red-600">{unsuccessfulCases} unsuccessful cases</p>
        </div>
      </div>
    </DashboardCard>
  );
}
