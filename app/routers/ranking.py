from fastapi import APIRouter, Depends, HTTPException
from app.core.firebase import db
from app.core.auth import get_current_user
from app.models.ranking import RankingEntry
from app.core import cache
from google.cloud.firestore_v1.base_query import FieldFilter

router = APIRouter(prefix="/ranking", tags=["Ranking"])


def _compute_ranking() -> list[RankingEntry]:
    """Calcula ranking completo. Cacheado 60s."""
    cached = cache.get("ranking")
    if cached is not None:
        return cached

    # 1 query: todos los jugadores
    users_docs = db.collection("users")\
        .where(filter=FieldFilter("role", "==", "player"))\
        .stream()
    players_map = {}
    for doc in users_docs:
        user = doc.to_dict()
        players_map[user["uid"]] = user

    if not players_map:
        cache.set("ranking", [], ttl=60)
        return []

    # 1 query: TODAS las predicciones procesadas (en vez de 1 por jugador)
    all_preds_docs = db.collection("predictions")\
        .where(filter=FieldFilter("processed", "==", True))\
        .stream()

    # Agrupar por uid
    preds_by_uid: dict[str, list[dict]] = {}
    for doc in all_preds_docs:
        pred = doc.to_dict()
        uid = pred.get("uid")
        if uid and uid in players_map:
            if uid not in preds_by_uid:
                preds_by_uid[uid] = []
            preds_by_uid[uid].append(pred)

    # Construir ranking
    result = []
    for uid, user in players_map.items():
        processed_preds = preds_by_uid.get(uid, [])
        correct_winners = len([p for p in processed_preds if p.get("points", 0) >= 1])
        accuracy = round(
            correct_winners / len(processed_preds) * 100, 1
        ) if processed_preds else 0.0

        result.append({
            "uid": uid,
            "display_name": user.get("display_name", ""),
            "photo_url": user.get("photo_url"),
            "total_score": user.get("total_score", 0),
            "predictions_count": user.get("predictions_count", 0),
            "exact_results": user.get("exact_results", 0),
            "correct_winners": correct_winners,
            "accuracy": accuracy,
        })

    result.sort(key=lambda x: (
        -x["total_score"],
        -x["exact_results"],
        -x["accuracy"]
    ))

    ranking = [
        RankingEntry(position=i + 1, **player)
        for i, player in enumerate(result)
    ]

    cache.set("ranking", ranking, ttl=60)
    return ranking


@router.get("/", response_model=list[RankingEntry])
async def get_ranking(current_user: dict = Depends(get_current_user)):
    return _compute_ranking()


@router.get("/me")
async def get_my_position(current_user: dict = Depends(get_current_user)):
    ranking = _compute_ranking()

    my_entry = next(
        (r for r in ranking if r.uid == current_user["uid"]), None
    )

    if not my_entry:
        raise HTTPException(status_code=404, detail="Usuario no encontrado en el ranking")

    return {
        "position": my_entry.position,
        "total_players": len(ranking),
        "entry": my_entry,
    }


@router.get("/top/{n}")
async def get_top_n(n: int, current_user: dict = Depends(get_current_user)):
    if n < 1 or n > 50:
        raise HTTPException(status_code=400, detail="N debe estar entre 1 y 50")

    ranking = _compute_ranking()
    return {
        "top": ranking[:n],
        "total_players": len(ranking),
    }