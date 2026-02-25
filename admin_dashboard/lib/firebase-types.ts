interface FirebaseUser {
  car_id: string;
  color: string;
  last_seen: string;
  model: string;
  owner: string;
  plate: string;
}

interface FirebaseStat {
  connect:number;
  error:number;
  getInfo:number;
}

export type UsersMap = Record<string, FirebaseUser>;

export type StatsMap = Record<string, FirebaseStat>;
export type StatsStruct = FirebaseStat;

/** Root shape if you read the whole DB; currently only `users` is used. */
export interface FirebaseDatabase {
  users?: UsersMap;
  stats?: StatsMap;
}
