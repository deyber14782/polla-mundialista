from fastapi import APIRouter, HTTPException, Depends
from app.core.firebase import db
from app.core.auth import get_current_user, require_admin
from app.services.matches_service import seed_matches_from_api
from app.services.football_api import get_world_cup_league_id
from google.cloud.firestore_v1.base_query import FieldFilter
from app.core import cache
import httpx
from app.core.config import settings

router = APIRouter(prefix="/matches", tags=["Matches"])


def _get_all_matches_cached():
    """Lee matches de caché o Firestore. Cachea 5 min."""
    cached = cache.get("all_matches")
    if cached is not None:
        return cached

    docs = db.collection("matches").order_by("kickoff").stream()
    matches = [doc.to_dict() for doc in docs]
    cache.set("all_matches", matches, ttl=300)
    return matches


def get_matches_dict_cached() -> dict:
    """Devuelve {fixture_id: match_dict} — usado por otros módulos."""
    cached = cache.get("matches_dict")
    if cached is not None:
        return cached

    all_matches = _get_all_matches_cached()
    matches_dict = {m["fixture_id"]: m for m in all_matches}
    cache.set("matches_dict", matches_dict, ttl=300)
    return matches_dict


@router.get("")
async def get_all_matches(
    phase: str = None,
    current_user: dict = Depends(get_current_user)
):
    matches = _get_all_matches_cached()

    if phase:
        matches = [m for m in matches if m.get("phase") == phase]

    return {"matches": matches}


@router.post("/seed")
async def seed_matches(current_user: dict = Depends(require_admin)):
    result = await seed_matches_from_api()
    cache.invalidate("all_matches", "matches_dict")
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
    from app.services.bracket_service import project_bracket_for_user

    uid = current_user["uid"]
    matches_dict = get_matches_dict_cached()

    # Leer predicciones del usuario (1 sola query)
    predictions_docs = db.collection("predictions")\
        .where(filter=FieldFilter("uid", "==", uid))\
        .stream()

    user_group_preds = 0
    for p in predictions_docs:
        pred = p.to_dict()
        match = matches_dict.get(pred["fixture_id"])
        if match and match.get("phase") == "group":
            user_group_preds += 1

    total_group_matches = len([m for m in matches_dict.values() if m.get("phase") == "group"])

    if user_group_preds < total_group_matches:
        raise HTTPException(
            status_code=400,
            detail=f"Debes predecir todos los partidos de grupos primero. "
                   f"Tienes {user_group_preds} de {total_group_matches}."
        )

    result = await project_bracket_for_user(uid)
    return result


@router.get("/{fixture_id}")
async def get_match(fixture_id: int, current_user: dict = Depends(get_current_user)):
    matches_dict = get_matches_dict_cached()
    match = matches_dict.get(fixture_id)
    if not match:
        raise HTTPException(status_code=404, detail="Partido no encontrado")
    return match