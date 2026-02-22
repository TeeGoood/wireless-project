import firebase_admin
from firebase_admin import credentials, db

# Path to service account JSON
cred = credentials.Certificate("firebase-key.json")

# Initialize app
firebase_admin.initialize_app(
    cred,
    {
        "databaseURL": "https://talksig-wireless-default-rtdb.asia-southeast1.firebasedatabase.app/"
    },
)

print("Connected")

ref = db.reference("users/user1")

ref.set({"name": "Alice", "age": 30})

data = ref.get()
print(data)
