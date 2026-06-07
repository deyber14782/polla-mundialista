import firebase_admin
from firebase_admin import credentials, firestore
import json
import os

def init_firebase():
    if not firebase_admin._apps:
        creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
        if creds_json:
            cred = credentials.Certificate(json.loads(creds_json))
        else:
            cred = credentials.Certificate("serviceAccountKey.json")
        firebase_admin.initialize_app(cred)
    return firestore.client()

db = init_firebase()