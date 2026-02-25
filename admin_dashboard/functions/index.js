const functions = require("firebase-functions");
const admin = require("firebase-admin");

admin.initializeApp();

const db = admin.database();

/** Cutoff: entries with last_seen older than this are removed (ms). */
const STALE_MS = 60 * 1000; // 1 minute

/**
 * Parses last_seen (ISO string like "2026-02-25T17:14:40.634838") to timestamp.
 * Returns 0 if invalid so the entry is treated as stale.
 */
function parseLastSeen(value) {
  if (value == null || typeof value !== "string") return 0;
  const t = Date.parse(value);
  return Number.isNaN(t) ? 0 : t;
}

/**
 * Scheduled function: every minute, remove /online children whose last_seen
 * is older than 1 minute.
 */
exports.cleanStaleOnline = functions
  .region("asia-southeast1")
  .pubsub.schedule("every 1 minutes")
  .onRun(async () => {
    const ref = db.ref("online");
    const snapshot = await ref.once("value");
    const data = snapshot.val();

    if (!data || typeof data !== "object") {
      return null;
    }

    const now = Date.now();
    const cutoff = now - STALE_MS;
    const toRemove = [];

    for (const [key, node] of Object.entries(data)) {
      if (node == null || typeof node !== "object") continue;
      const lastSeen = parseLastSeen(node.last_seen);
      if (lastSeen < cutoff) {
        toRemove.push(key);
      }
    }

    if (toRemove.length === 0) {
      return null;
    }

    const updates = {};
    for (const key of toRemove) {
      updates[key] = null;
    }
    await ref.update(updates);

    functions.logger.info(
      "cleanStaleOnline: removed " + toRemove.length + " stale entries",
      { keys: toRemove }
    );
    return null;
  });
