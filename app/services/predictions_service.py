from datetime import datetime, timezone
from app.core.firebase import db


def get_prediction_id(uid: str, fixture_id: int) -> str:
    """ID único de predicción = uid + fixture_id."""
    return f"{uid}_{fixture_id}"


def is_match_locked(kickoff: str) -> bool:
    """
    Verifica si el partido ya comenzó comparando
    la hora de inicio con la hora actual UTC.
    """
    kickoff_dt = datetime.fromisoformat(kickoff.replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    return now >= kickoff_dt


def enrich_prediction(pred: dict, match: dict) -> dict:
    """Agrega info del partido a la predicción para el frontend."""
    return {
        **pred,
        "home_team_name": match["home_team"]["name"],
        "away_team_name": match["away_team"]["name"],
        "home_team_logo": match["home_team"]["logo"],
        "away_team_logo": match["away_team"]["logo"],
        "kickoff": match["kickoff"],
        "phase": match["phase"],
        "real_home": match["score"]["home"],
        "real_away": match["score"]["away"],
    }


async def get_user_predictions_with_matches(uid: str) -> list[dict]:
    """
    Devuelve todas las predicciones de un usuario
    enriquecidas con la info del partido.
    """
    predictions_docs = db.collection("predictions")\
        .where("uid", "==", uid)\
        .stream()

    result = []
    for doc in predictions_docs:
        pred = doc.to_dict()
        match_doc = db.collection("matches")\
            .document(str(pred["fixture_id"])).get()

        if match_doc.exists:
            result.append(enrich_prediction(pred, match_doc.to_dict()))

    # Ordenamos por fecha de kickoff
    result.sort(key=lambda x: x.get("kickoff", ""))
    return result


async def get_match_predictions_public(fixture_id: int) -> list[dict]:
    """
    Devuelve las predicciones de todos los usuarios para un partido.
    Solo disponible si el partido ya comenzó (para evitar copias).
    """
    match_doc = db.collection("matches").document(str(fixture_id)).get()
    if not match_doc.exists:
        return []

    match = match_doc.to_dict()

    # Solo mostramos predicciones si el partido ya empezó
    if not is_match_locked(match["kickoff"]):
        return []

    predictions_docs = db.collection("predictions")\
        .where("fixture_id", "==", fixture_id)\
        .stream()

    result = []
    for doc in predictions_docs:
        pred = doc.to_dict()
        # Traemos nombre del usuario
        user_doc = db.collection("users").document(pred["uid"]).get()
        if user_doc.exists:
            user = user_doc.to_dict()
            result.append({
                **pred,
                "display_name": user.get("display_name"),
                "photo_url": user.get("photo_url"),
            })

    return result