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


def push(data):
    ref = db.reference("data")
    ref.push(data)


def get(ref_path):
    ref = db.reference(ref_path)
    return ref.get()


def set(ref_path, data):
    ref = db.reference(ref_path)
    ref.set(data)


def update(ref_path, data):
    ref = db.reference(ref_path)
    ref.update(data)
