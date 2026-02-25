import { NextResponse } from 'next/server';
import * as admin from 'firebase-admin';

const STALE_MS = 60 * 1000; // 1 minute

function parseLastSeen(value: unknown): number {
  if (value == null || typeof value !== 'string') return 0;
  const t = Date.parse(value);
  return Number.isNaN(t) ? 0 : t;
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
      return NextResponse.json({ removed: 0 });
    }

    const now = Date.now();
    const cutoff = now - STALE_MS;
    const toRemove: string[] = [];

    for (const [key, node] of Object.entries(data)) {
      if (node == null || typeof node !== 'object') continue;
      const lastSeen = parseLastSeen((node as { last_seen?: unknown }).last_seen);
      if (lastSeen < cutoff) {
        toRemove.push(key);
      }
    }

    if (toRemove.length === 0) {
      return NextResponse.json({ removed: 0 });
    }

    const updates: Record<string, null> = {};
    for (const key of toRemove) {
      updates[key] = null;
    }
    await ref.update(updates);

    return NextResponse.json({ removed: toRemove.length, keys: toRemove });
  } catch (err) {
    console.error('clean-stale-online error:', err);
    return NextResponse.json(
      { error: err instanceof Error ? err.message : 'Unknown error' },
      { status: 500 }
    );
  }
}
