import type { UsersMap } from '@/lib/firebase-types';

export function formatPageDate(date: Date): string {
  const day = date.getDate();
  const suffix = day === 1 || day === 21 || day === 31 ? 'st' : day === 2 || day === 22 ? 'nd' : day === 3 || day === 23 ? 'rd' : 'th';
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  return `${day}${suffix} ${months[date.getMonth()]} ${date.getFullYear()}`;
}

export function formatUsersSummary(users: UsersMap | null): string {
  if (!users || typeof users !== 'object') return 'Firebase: no users';
  const entries = Object.entries(users);
  if (entries.length === 0) return 'Firebase: 0 users';
  const names = entries
    .map(([, u]) => (u && typeof u === 'object' && 'name' in u ? String(u.name) : null))
    .filter(Boolean);
  return `Firebase: ${entries.length} user(s) — ${names.join(', ') || '—'}`;
}
