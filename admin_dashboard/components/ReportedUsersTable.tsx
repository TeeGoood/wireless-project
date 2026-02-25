'use client';

import { DashboardCard } from './DashboardCard';

function BroadcastIcon() {
  return (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.536 8.464a5 5 0 010 7.072m2.828-9.9a9 9 0 010 12.728M5.586 15.536a5 5 0 001.414 1.414m2.828-9.9a9 9 0 012.828-2.828" />
    </svg>
  );
}

export interface ReportedUser {
  id: string;
  name: string;
  reason: string;
}

const defaultReported: ReportedUser[] = [
  { id: '1', name: 'Abico', reason: "Doesn't speak Thai nor English" },
];

function BanActionIcon() {
  return (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" />
    </svg>
  );
}

function PauseActionIcon() {
  return (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 9v6m4-6v6m7-3a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  );
}

function CheckActionIcon() {
  return (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
    </svg>
  );
}

export function ReportedUsersTable({ rows = defaultReported }: { rows?: ReportedUser[] }) {
  return (
    <DashboardCard
      title="Reported Users"
      icon={<BroadcastIcon />}
    >
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-lightGrey text-darkTeal font-semibold">
              <th className="py-3 pr-4">Name</th>
              <th className="py-3 pr-4">Reason</th>
              <th className="py-3">Actions</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id} className="border-b border-lightGrey/50 text-darkTeal">
                <td className="py-3 pr-4">{row.name}</td>
                <td className="py-3 pr-4">{row.reason}</td>
                <td className="py-3">
                  <div className="flex gap-2">
                    <button type="button" className="w-9 h-9 rounded-full bg-red-500 text-white flex items-center justify-center hover:bg-red-600 transition-colors" aria-label="Ban user">
                      <BanActionIcon />
                    </button>
                    <button type="button" className="w-9 h-9 rounded-full bg-amber-500 text-white flex items-center justify-center hover:bg-amber-600 transition-colors" aria-label="Pause user">
                      <PauseActionIcon />
                    </button>
                    <button type="button" className="w-9 h-9 rounded-full bg-green-500 text-white flex items-center justify-center hover:bg-green-600 transition-colors" aria-label="Approve user">
                      <CheckActionIcon />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </DashboardCard>
  );
}
