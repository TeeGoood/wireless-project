'use client';

import { useState } from 'react';
import { DashboardCard } from '@/components/DashboardCard';

function ChartIcon() {
  return (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4v16" />
    </svg>
  );
}

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
const WEEKS = ['Week 1', 'Week 2', 'Week 3', 'Week 4'];

// Figma: bar values ~5, 8, 2, 13 (0–20 scale)
const defaultData = [5, 8, 2, 13];

const Y_AXIS_MAX = 20;

export function GraphicStatisticsCard({ className }: { className?: string }) {
  const [monthIndex, setMonthIndex] = useState(1); // February
  const [data] = useState(defaultData);

  return (
    <DashboardCard
      title="Graphic Statistics"
      icon={<ChartIcon />}
      className={className}
    >
      <div className="flex flex-col flex-1 min-h-0 overflow-hidden min-w-0">
        <div className="mb-3 sm:mb-4 flex-shrink-0 flex flex-wrap items-center gap-2">
          <label htmlFor="month-select" className="sr-only">Select month</label>
          <select
            id="month-select"
            value={monthIndex}
            onChange={(e) => setMonthIndex(Number(e.target.value))}
            className="text-sm border border-lightGrey rounded-lg px-2 sm:px-3 py-1.5 sm:py-2 text-darkTeal bg-white focus:outline-none focus:ring-2 focus:ring-mediumBlue"
          >
            {MONTHS.map((name, i) => (
              <option key={name} value={i}>{name}</option>
            ))}
          </select>
          <span className="text-xs sm:text-sm text-mutedTeal">Currently Showing: {MONTHS[monthIndex]} ▼</span>
        </div>
        <p className="text-sm font-medium text-darkTeal mb-2 sm:mb-3 flex-shrink-0">Total Users</p>
        <div className="flex gap-1 sm:gap-2 flex-1 min-h-0 min-w-0 overflow-x-auto overflow-y-hidden">
          <div className="flex flex-col justify-between text-[10px] sm:text-xs text-mutedTeal py-0.5 flex-shrink-0">
            <span>20</span>
            <span>15</span>
            <span>10</span>
            <span>5</span>
            <span>0</span>
          </div>
          <div className="flex flex-1 items-stretch gap-1 sm:gap-2 md:gap-4 min-h-0 min-w-[12rem] flex-shrink-0">
            {WEEKS.map((label, i) => (
              <div key={label} className="flex-1 min-w-[3rem] flex flex-col items-center gap-1 sm:gap-2 min-h-0">
                <div className="w-full flex-1 flex flex-col justify-end min-h-0 rounded-t-lg overflow-hidden">
                  <div
                    className="w-full bg-lightGrey/30 transition-all duration-300"
                    style={{ flex: Y_AXIS_MAX - data[i] }}
                  />
                  <div
                    className="w-full bg-darkTeal rounded-t transition-all duration-300"
                    style={{ flex: data[i], minHeight: data[i] > 0 ? '4px' : 0 }}
                  />
                </div>
                <span className="text-[10px] sm:text-xs text-darkTeal font-medium flex-shrink-0 truncate max-w-full">{label}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </DashboardCard>
  );
}
