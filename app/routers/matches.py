from fastapi import APIRouter, HTTPException, Depends
from app.core.firebase import db
from app.core.auth import get_current_user, require_admin
from app.services.matches_service import seed_matches_from_api
from app.services.football_api import get_world_cup_league_id
from google.cloud.firestore_v1.base_query import FieldFilter
import httpx
from app.core.config import settings
import time

router = APIRouter(prefix="/matches", tags=["Matches"])


@router.get("")
async def get_all_matches(
    phase: str = None,
    current_user: dict = Depends(get_current_user)
):
    t0 = time.time()

    query = db.collection("matches")

    if phase:
        query = query.where(filter=FieldFilter("phase", "==", phase))

    t1 = time.time()

    docs = query.order_by("kickoff").stream()

    t2 = time.time()

    matches = [doc.to_dict() for doc in docs]

    t3 = time.time()

    print("Construcción query:", round(t1 - t0, 2))
    print("Stream:", round(t2 - t1, 2))
    print("Lectura documentos:", round(t3 - t2, 2))
    print("Total:", round(t3 - t0, 2))

    return {"matches": matches}


@router.post("/seed")
async def seed_matches(current_user: dict = Depends(require_admin)):
    result = await seed_matches_from_api()
    return result


@router.get("/admin/check-league-id")
async def check_league_id(current_user: dict = Depends(require_admin)):
    league_id = await get_world_cup_league_id()
    return {"world_cup_league_id": league_id}


@router.get("/admin/search-leagues")
async def search_leagues(
    name: str = "World Cup",
    current_user: dict = Depends(require_admin)
):
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://v3.football.api-sports.io/leagues",
            headers={"x-apisports-key": settings.API_FOOTBALL_KEY},
            params={"name": name},
            timeout=15.0
        )
        data = response.json()
        leagues = data.get("response", [])
        return {
            "total": len(leagues),
            "leagues": [
                {
                    "id": l["league"]["id"],
                    "name": l["league"]["name"],
                    "type": l["league"]["type"],
                    "seasons": [s["year"] for s in l["seasons"][-3:]]
                }
                for l in leagues
            ]
        }


@router.get("/bracket/me")
async def get_my_bracket(current_user: dict = Depends(get_current_user)):
    """
    Devuelve el cuadro eliminatorio proyectado
    basado en las predicciones de grupos del usuario.
    """
    from app.services.bracket_service import project_bracket_for_user

    uid = current_user["uid"]

    # Verificar predicciones de grupos
    group_preds_docs = db.collection("predictions")\
        .where(filter=FieldFilter("uid", "==", uid))\
        .stream()

    group_matches_docs = db.collection("matches")\
        .where(filter=FieldFilter("phase", "==", "group"))\
        .stream()

    total_group_matches = len(list(group_matches_docs))

    user_group_preds = 0
    for p in group_preds_docs:
        pred = p.to_dict()
        match_doc = db.collection("matches")\
            .document(str(pred["fixture_id"])).get()
        if match_doc.exists and match_doc.to_dict().get("phase") == "group":
            user_group_preds += 1

    if user_group_preds < total_group_matches:
        raise HTTPException(
            status_code=400,
            detail=f"Debes predecir todos los partidos de grupos primero. "
                   f"Tienes {user_group_preds} de {total_group_matches}."
        )

    result = await project_bracket_for_user(uid)
    return result


# ── Ruta con parámetro SIEMPRE AL FINAL ──────────────────────────
@router.get("/{fixture_id}")
async def get_match(fixture_id: int, current_user: dict = Depends(get_current_user)):
    doc = db.collection("matches").document(str(fixture_id)).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Partido no encontrado")
    return doc.to_dict()