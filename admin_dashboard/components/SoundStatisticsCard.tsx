'use client';

import { useState } from 'react';
import { DashboardCard } from './DashboardCard';

function ChartIcon() {
  return (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4v16" />
    </svg>
  );
}

const ENTITIES = ['1', '2', '3', '4'];
const defaultData = [5, 8, 2, 13];
const BAR_MAX = Math.max(...defaultData);

export function SoundStatisticsCard({ className }: { className?: string }) {
  const [data] = useState(defaultData);

  const rows = ENTITIES.map((label, i) => ({ label, value: data[i] ?? 0 }))
    .sort((a, b) => b.value - a.value);

  return (
    <DashboardCard
      title="Sound Statistics"
      icon={<ChartIcon />}
      className={className}
    >
      <div className="flex flex-col flex-1 min-h-0 overflow-hidden min-w-0 gap-3 sm:gap-4">
        {rows.map(({ label, value }) => {
          const percent = BAR_MAX > 0 ? Math.min(100, (value / BAR_MAX) * 100) : 0;
          return (
            <div
              key={label}
              className="flex items-center gap-2 sm:gap-3 min-w-0 flex-shrink-0"
            >
              <span className="text-sm font-medium text-darkTeal w-5 flex-shrink-0">
                {label}
              </span>
              <div className="flex-1 min-w-0 h-6 sm:h-7 bg-lightGrey/30 rounded-full overflow-hidden flex">
                <div
                  className="h-full bg-darkTeal rounded-full transition-all duration-300"
                  style={{ width: `${percent}%`, minWidth: value > 0 ? '4px' : 0 }}
                />
              </div>
              <span className="text-sm font-semibold text-darkTeal w-6 sm:w-8 text-right flex-shrink-0">
                {value}
              </span>
            </div>
          );
        })}
      </div>
    </DashboardCard>
  );
}
