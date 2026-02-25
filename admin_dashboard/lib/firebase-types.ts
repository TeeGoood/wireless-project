/**
 * Matches your Realtime Database structure (e.g. users with name, age).
 * Extend when you add more root keys or user fields.
 */

export interface FirebaseUser {
  car_id: string;
  color: string;
  last_seen: string;
  model: string;
  owner: string;
  plate: string;
}

/** Map of user id → user (e.g. "user1" | "-Om31ZLtQ4KkxMjuTVZW" → FirebaseUser) */
export type UsersMap = Record<string, FirebaseUser>;

/** Root shape if you read the whole DB; currently only `users` is used. */
export interface FirebaseDatabase {
  users?: UsersMap;
}
