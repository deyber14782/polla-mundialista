import firebase_admin
from firebase_admin import credentials, firestore
import json
import os

def init_firebase():
    if not firebase_admin._apps:
        creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
        
        print(f"GOOGLE_CREDENTIALS_JSON existe: {bool(creds_json)}")
        print(f"Primeros 50 chars: {creds_json[:50] if creds_json else 'VACIO'}")
        
        if creds_json:
            try:
                cred_dict = json.loads(creds_json)
                cred = credentials.Certificate(cred_dict)
                print("Credenciales cargadas correctamente desde variable de entorno")
            except Exception as e:
                print(f"Error parseando JSON: {e}")
                raise
        else:
            print("Usando serviceAccountKey.json local")
            cred = credentials.Certificate("serviceAccountKey.json")
            
        firebase_admin.initialize_app(cred)
    return firestore.client()

db = init_firebase()