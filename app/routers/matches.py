from fastapi import APIRouter, HTTPException, Depends
from app.core.firebase import db
from app.core.auth import get_current_user, require_admin
from app.services.matches_service import seed_matches_from_api
from app.services.football_api import get_world_cup_league_id

router = APIRouter(prefix="/matches", tags=["Matches"])


@router.get("/")
async def get_all_matches(
    phase: str = None,
    current_user: dict = Depends(get_current_user)
):
    """
    Devuelve todos los partidos del Mundial.
    Opcionalmente filtra por fase.
    """
    query = db.collection("matches")

    if phase:
        query = query.where("phase", "==", phase)

    docs = query.order_by("kickoff").stream()
    matches = [doc.to_dict() for doc in docs]

    if not matches:
        raise HTTPException(status_code=404, detail="No se encontraron partidos")

    return {"matches": matches, "total": len(matches)}


@router.get("/live")
async def get_live_matches(current_user: dict = Depends(get_current_user)):
    """Devuelve los partidos que están en vivo ahora mismo."""
    live_statuses = ["1H", "HT", "2H"]
    docs = db.collection("matches").stream()
    live = [
        doc.to_dict() for doc in docs
        if doc.to_dict().get("status") in live_statuses
    ]
    return {"matches": live, "total": len(live)}


@router.get("/{fixture_id}")
async def get_match(fixture_id: int, current_user: dict = Depends(get_current_user)):
    """Devuelve un partido específico por su fixture_id."""
    doc = db.collection("matches").document(str(fixture_id)).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Partido no encontrado")
    return doc.to_dict()


@router.post("/seed")
async def seed_matches(current_user: dict = Depends(require_admin)):
    """
    Admin: pobla Firestore con todos los partidos del Mundial.
    Ejecutar una sola vez.
    """
    result = await seed_matches_from_api()
    return result


@router.get("/admin/check-league-id")
async def check_league_id(current_user: dict = Depends(require_admin)):
    """Admin: verifica el ID correcto del Mundial 2026 en la API."""
    league_id = await get_world_cup_league_id()
    return {"world_cup_league_id": league_id}