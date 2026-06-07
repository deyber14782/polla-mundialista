from fastapi import APIRouter, HTTPException, Depends
from app.core.firebase import db
from app.core.auth import get_current_user, require_admin
from app.services.matches_service import seed_matches_from_api
from app.services.football_api import get_world_cup_league_id
from google.cloud.firestore_v1.base_query import FieldFilter
import httpx
from app.core.config import settings

router = APIRouter(prefix="/matches", tags=["Matches"])


@router.get("/")
async def get_all_matches(
    phase: str = None,
    current_user: dict = Depends(get_current_user)
):
    query = db.collection("matches")
    if phase:
        query = query.where(filter=FieldFilter("phase", "==", phase))
    docs = query.order_by("kickoff").stream()
    matches = [doc.to_dict() for doc in docs]
    if not matches:
        raise HTTPException(status_code=404, detail="No se encontraron partidos")
    return {"matches": matches, "total": len(matches)}


@router.get("/live")
async def get_live_matches(current_user: dict = Depends(get_current_user)):
    live_statuses = ["1H", "HT", "2H"]
    docs = db.collection("matches").stream()
    live = [
        doc.to_dict() for doc in docs
        if doc.to_dict().get("status") in live_statuses
    ]
    return {"matches": live, "total": len(live)}


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