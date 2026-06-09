from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from firebase_admin import auth
from app.core.firebase import db
import time

security = HTTPBearer()

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    start = time.time()
    token = credentials.credentials
    try:
        t1 = time.time()
        decoded_token = auth.verify_id_token(token, clock_skew_seconds=10)
        print("verify_id_token:", round(time.time() - t1, 2))
        uid = decoded_token["uid"]

        uid = decoded_token["uid"]

        user_ref = db.collection("users").document(uid)
        t2 = time.time()
        user_doc = user_ref.get()
        print("user_doc:", round(time.time() - t2, 2))

        print("TOTAL AUTH:", round(time.time() - start, 2))

        if not user_doc.exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Usuario no encontrado en Firestore"
            )

        return {"uid": uid, **user_doc.to_dict()}

    except auth.ExpiredIdTokenError:
        raise HTTPException(status_code=401, detail="Token expirado")
    except auth.InvalidIdTokenError:
        raise HTTPException(status_code=401, detail="Token inválido")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Error de autenticación: {str(e)}")


async def require_admin(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso denegado. Se requiere rol de administrador"
        )
    return current_user