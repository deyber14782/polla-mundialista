from datetime import datetime, timezone
from app.core.firebase import db
from google.cloud.firestore_v1.base_query import FieldFilter

WORLD_CUP_START = datetime(2026, 6, 11, 11, 0, 0, tzinfo=timezone.utc)  # 6am Colombia

def get_prediction_id(uid: str, fixture_id: int) -> str:
    return f"{uid}_{fixture_id}"


def is_match_locked(kickoff: str) -> bool:
    now = datetime.now(timezone.utc)
    return now >= WORLD_CUP_START


def enrich_prediction(pred: dict, match: dict) -> dict:
    return {
        **pred,
        "home_team_name": match["home_team"]["name"],
        "away_team_name": match["away_team"]["name"],
        "home_team_logo": match["home_team"]["logo"],
        "away_team_logo": match["away_team"]["logo"],
        "kickoff":        match["kickoff"],
        "phase":          match["phase"],
        "real_home":      match["score"]["home"],
        "real_away":      match["score"]["away"],
        "penalty_winner": pred.get("penalty_winner"),
    }


async def get_user_predictions_with_matches(uid: str) -> list[dict]:
    # Usar matches cacheados en vez de leer 1 por 1
    from app.routers.matches import get_matches_dict_cached
    matches_dict = get_matches_dict_cached()

    predictions_docs = db.collection("predictions")\
        .where(filter=FieldFilter("uid", "==", uid))\
        .stream()

    result = []
    for doc in predictions_docs:
        pred = doc.to_dict()
        match = matches_dict.get(pred["fixture_id"])
        if match:
            result.append(enrich_prediction(pred, match))

    result.sort(key=lambda x: x.get("kickoff", ""))
    return result


async def get_match_predictions_public(fixture_id: int) -> list[dict]:
    from app.routers.matches import get_matches_dict_cached
    matches_dict = get_matches_dict_cached()

    match = matches_dict.get(fixture_id)
    if not match:
        return []

    if not is_match_locked(match["kickoff"]):
        return []

    predictions_docs = db.collection("predictions")\
        .where(filter=FieldFilter("fixture_id", "==", fixture_id))\
        .stream()

    result = []
    for doc in predictions_docs:
        pred = doc.to_dict()
        user_doc = db.collection("users").document(pred["uid"]).get()
        if user_doc.exists:
            user = user_doc.to_dict()
            result.append({
                **pred,
                "display_name": user.get("display_name"),
                "photo_url":    user.get("photo_url"),
            })

    return result