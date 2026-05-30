from fastapi import APIRouter, HTTPException, Depends, status
from app.core.firebase import db
from app.core.auth import get_current_user, require_admin
from app.models.user import UserCreate, UserResponse, UserRole
from firebase_admin import auth as firebase_auth

router = APIRouter(prefix="/users", tags=["Users"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register_user(
    user_data: UserCreate,
    current_user: dict = Depends(require_admin)
):
    """
    Registra un nuevo usuario. Solo accesible para administradores.
    Crea el usuario en Firebase Auth y su perfil en Firestore.
    """
    # Verificar que el teléfono no esté ya registrado
    existing = db.collection("users").where("phone", "==", user_data.phone).limit(1).get()
    if len(existing) > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe un usuario con ese número de celular"
        )

    # Crear usuario en Firebase Auth
    try:
        firebase_user = firebase_auth.create_user(
            email=user_data.email,
            password=user_data.phone,   # contraseña inicial = celular
            display_name=user_data.display_name,
        )
    except firebase_auth.EmailAlreadyExistsError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe un usuario con ese correo"
        )

    # Guardar perfil en Firestore
    new_user = {
        "uid": firebase_user.uid,
        "email": user_data.email,
        "display_name": user_data.display_name,
        "phone": user_data.phone,
        "photo_url": user_data.photo_url,
        "role": UserRole.player,
        "total_score": 0,
        "predictions_count": 0,
        "exact_results": 0,
    }
    db.collection("users").document(firebase_user.uid).set(new_user)

    return UserResponse(**new_user)


@router.get("/me", response_model=UserResponse)
async def get_my_profile(current_user: dict = Depends(get_current_user)):
    """Devuelve el perfil del usuario autenticado."""
    return UserResponse(**current_user)


@router.put("/me", response_model=UserResponse)
async def update_my_profile(
    display_name: str = None,
    photo_url: str = None,
    current_user: dict = Depends(get_current_user)
):
    """
    El usuario puede actualizar su nombre y foto de perfil.
    No puede cambiar email, teléfono ni rol.
    """
    uid = current_user["uid"]
    updates = {}

    if display_name:
        updates["display_name"] = display_name
    if photo_url:
        updates["photo_url"] = photo_url

    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No hay campos para actualizar"
        )

    db.collection("users").document(uid).update(updates)

    updated_doc = db.collection("users").document(uid).get()
    return UserResponse(**updated_doc.to_dict())


@router.get("/{uid}", response_model=UserResponse)
async def get_user_profile(uid: str, current_user: dict = Depends(get_current_user)):
    """Devuelve el perfil público de cualquier usuario."""
    user_doc = db.collection("users").document(uid).get()
    if not user_doc.exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado"
        )
    return UserResponse(**user_doc.to_dict())


@router.get("/", response_model=list[UserResponse])
async def get_all_users(current_user: dict = Depends(require_admin)):
    """Admin: devuelve la lista de todos los usuarios registrados."""
    docs = db.collection("users").order_by("display_name").stream()
    return [UserResponse(**doc.to_dict()) for doc in docs]


@router.delete("/{uid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(uid: str, current_user: dict = Depends(require_admin)):
    """Admin: elimina un usuario de Firebase Auth y Firestore."""
    user_doc = db.collection("users").document(uid).get()
    if not user_doc.exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado"
        )

    # Eliminar de Firebase Auth
    firebase_auth.delete_user(uid)

    # Eliminar de Firestore
    db.collection("users").document(uid).delete()