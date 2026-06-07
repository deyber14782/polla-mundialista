from fastapi import APIRouter, Depends, HTTPException
from app.core.firebase import db
from app.core.auth import get_current_user
from app.models.ranking import RankingEntry
from google.cloud.firestore_v1.base_query import FieldFilter

router = APIRouter(prefix="/ranking", tags=["Ranking"])


@router.get("/", response_model=list[RankingEntry])
async def get_ranking(current_user: dict = Depends(get_current_user)):
    users_docs = db.collection("users")\
        .where(filter=FieldFilter("role", "==", "player"))\
        .stream()

    players = []
    for doc in users_docs:
        user = doc.to_dict()

        preds = db.collection("predictions")\
            .where(filter=FieldFilter("uid", "==", user["uid"]))\
            .where(filter=FieldFilter("processed", "==", True))\
            .stream()

        processed_preds = [p.to_dict() for p in preds]
        correct_winners = len([p for p in processed_preds if p.get("points", 0) >= 1])
        accuracy = round(
            correct_winners / len(processed_preds) * 100, 1
        ) if processed_preds else 0.0

        players.append({
            "uid": user["uid"],
            "display_name": user.get("display_name", ""),
            "photo_url": user.get("photo_url"),
            "total_score": user.get("total_score", 0),
            "predictions_count": user.get("predictions_count", 0),
            "exact_results": user.get("exact_results", 0),
            "correct_winners": correct_winners,
            "accuracy": accuracy,
        })

    players.sort(key=lambda x: (
        -x["total_score"],
        -x["exact_results"],
        -x["accuracy"]
    ))

    return [
        RankingEntry(position=i + 1, **player)
        for i, player in enumerate(players)
    ]


@router.get("/me")
async def get_my_position(current_user: dict = Depends(get_current_user)):
    ranking = await get_ranking(current_user)

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

    ranking = await get_ranking(current_user)
    return {
        "top": ranking[:n],
        "total_players": len(ranking),
    }