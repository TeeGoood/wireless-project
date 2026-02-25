import { initializeApp, getApps, FirebaseApp } from 'firebase/app'
import { getDatabase, Database, ref, get, onValue, off } from 'firebase/database'

// Firebase configuration
// You'll need to add your Firebase config here
// Get this from Firebase Console > Project Settings > General > Your apps
const firebaseConfig = {
  databaseURL: 'https://talksig-wireless-default-rtdb.asia-southeast1.firebasedatabase.app/',
  // Add other config values if needed for authentication:
  // apiKey: "your-api-key",
  // authDomain: "your-auth-domain",
  // projectId: "embedproject-ac1d3",
  // storageBucket: "your-storage-bucket",
  // messagingSenderId: "your-messaging-sender-id",
  // appId: "your-app-id"
}

// Initialize Firebase
let app: FirebaseApp
if (getApps().length === 0) {
  app = initializeApp(firebaseConfig)
} else {
  app = getApps()[0]
}

// Initialize Realtime Database
export const database: Database = getDatabase(app)

/**
 * Get a value from Firebase Realtime Database
 * @param path - The path to the data (e.g., 'test', 'waterLevel', 'moistureLevel')
 * @returns Promise with the data value
 */
export async function getFirebaseValue<T = any>(path: string): Promise<T | null> {
  try {
    const dbRef = ref(database, path)
    const snapshot = await get(dbRef)
    
    if (snapshot.exists()) {
      return snapshot.val() as T
    } else {
      console.log(`No data available at path: ${path}`)
      return null
    }
  } catch (error) {
    console.error('Error fetching data from Firebase:', error)
    throw error
  }
}

/**
 * Subscribe to real-time updates from Firebase
 * @param path - The path to the data
 * @param callback - Callback function that receives the data
 * @returns Function to unsubscribe
 */
export function subscribeToFirebaseValue<T = any>(
  path: string,
  callback: (value: T | null) => void
): () => void {
  const dbRef = ref(database, path)
  
  const unsubscribe = onValue(
    dbRef,
    (snapshot) => {
      if (snapshot.exists()) {
        callback(snapshot.val() as T)
      } else {
        callback(null)
      }
    },
    (error) => {
      console.error('Error listening to Firebase:', error)
      callback(null)
    }
  )
  
  // Return unsubscribe function
  return () => {
    off(dbRef)
    unsubscribe()
  }
}

