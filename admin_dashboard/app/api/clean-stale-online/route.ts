import { NextResponse } from 'next/server';
import * as admin from 'firebase-admin';

const STALE_MS = 60 * 1000; // 1 minute

/**
 * Parse last_seen to UTC timestamp in ms.
 * Supports: ISO string, or number (ms or seconds).
 * If the string has no timezone (no Z or ±HH:MM) and LAST_SEEN_TZ_OFFSET_HOURS is set,
 * the value is treated as local time in that zone (e.g. 7 = UTC+7 Bangkok) and converted to UTC.
 */
function parseLastSeen(value: unknown, tzOffsetHours?: number): number {
  if (value == null) return 0;
  if (typeof value === 'number' && !Number.isNaN(value)) {
    return value < 1e12 ? value * 1000 : value;
  }
  if (typeof value !== 'string') return 0;
  const s = value.trim();
  if (!s) return 0;
  const hasTz = /[Z+-]\d{2}:?\d{2}$/.test(s);
  const withTz = hasTz ? s : s + 'Z';
  let t = Date.parse(withTz);
  if (Number.isNaN(t)) return 0;
  if (!hasTz && tzOffsetHours != null) {
    t -= tzOffsetHours * 60 * 60 * 1000;
  }
  return t;
}

function getAdminDb(): admin.database.Database {
  if (!admin.apps.length) {
    const serviceAccountJson = process.env.FIREBASE_SERVICE_ACCOUNT_JSON;
    const databaseURL =
      process.env.FIREBASE_DATABASE_URL ||
      'https://talksig-wireless-default-rtdb.asia-southeast1.firebasedatabase.app/';
    if (!serviceAccountJson) {
      throw new Error('FIREBASE_SERVICE_ACCOUNT_JSON is not set');
    }
    admin.initializeApp({
      credential: admin.credential.cert(JSON.parse(serviceAccountJson) as admin.ServiceAccount),
      databaseURL,
    });
  }
  return admin.database();
}

export async function GET(request: Request) {
  const auth = request.headers.get('authorization');
  const cronSecret = process.env.CRON_SECRET;
  if (cronSecret && auth !== `Bearer ${cronSecret}`) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    const db = getAdminDb();
    const ref = db.ref('online');
    const snapshot = await ref.once('value');
    const data = snapshot.val();

    if (!data || typeof data !== 'object') {
      return NextResponse.json({
        removed: 0,
        total: 0,
        message: 'No data at /online or not an object (check Firebase env on this host)',
      });
    }

    const total = Object.keys(data).length;
    const now = Date.now();
    const tzOffsetEnv = process.env.LAST_SEEN_TZ_OFFSET_HOURS;
    const tzOffsetHours =
      tzOffsetEnv != null ? parseInt(tzOffsetEnv, 10) : NaN;
    const tzOffset = Number.isInteger(tzOffsetHours) ? tzOffsetHours : undefined;
    const url = new URL(request.url);
    const staleSecondsParam = url.searchParams.get('stale_seconds');
    const parsedSec =
      staleSecondsParam != null && cronSecret ? parseInt(staleSecondsParam, 10) : NaN;
    const staleMs =
      Number.isInteger(parsedSec) && parsedSec >= 0 ? parsedSec * 1000 : STALE_MS;
    const cutoff = now - staleMs;
    const toRemove: string[] = [];

    for (const [key, node] of Object.entries(data)) {
      if (node == null || typeof node !== 'object') continue;
      const lastSeen = parseLastSeen(
        (node as { last_seen?: unknown }).last_seen,
        tzOffset
      );
      if (lastSeen < cutoff) {
        toRemove.push(key);
      }
    }

    if (toRemove.length === 0) {
      const debug = url.searchParams.get('debug') === '1';
      const body: Record<string, unknown> = {
        removed: 0,
        total,
        message: 'No stale entries (all last_seen within 1 minute)',
      };
      if (debug) {
        const nowIso = new Date(now).toISOString();
        const cutoffIso = new Date(cutoff).toISOString();
        const sample = Object.entries(data).slice(0, 2).map(([k, n]) => {
          const node = n as Record<string, unknown>;
          const raw = node?.last_seen;
          const parsed = parseLastSeen(raw, tzOffset);
          return { key: k, last_seen: raw, parsed_ms: parsed, is_stale: parsed < cutoff };
        });
        body.debug = { now: nowIso, cutoff: cutoffIso, sample };
      }
      return NextResponse.json(body);
    }

    const updates: Record<string, null> = {};
    for (const key of toRemove) {
      updates[key] = null;
    }
    await ref.update(updates);

    return NextResponse.json({
      removed: toRemove.length,
      total,
      keys: toRemove,
    });
  } catch (err) {
    console.error('clean-stale-online error:', err);
    return NextResponse.json(
      { error: err instanceof Error ? err.message : 'Unknown error' },
      { status: 500 }
    );
  }
}
