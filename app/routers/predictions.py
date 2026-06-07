from fastapi import APIRouter, HTTPException, Depends, status
from app.core.firebase import db
from app.core.auth import get_current_user, require_admin
from app.models.prediction import (
    PredictionCreate, PredictionUpdate,
    PredictionResponse, PredictionStatus
)
from app.services.predictions_service import (
    get_prediction_id, is_match_locked,
    enrich_prediction, get_user_predictions_with_matches,
    get_match_predictions_public
)
from app.models.special_prediction import TopScorerPrediction, TopScorerResponse

router = APIRouter(prefix="/predictions", tags=["Predictions"])


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_prediction(
    data: PredictionCreate,
    current_user: dict = Depends(get_current_user)
):
    """
    Crea una predicción para un partido.
    Solo permitido si el partido no ha comenzado.
    """
    uid = current_user["uid"]

    # Verificar que el partido existe
    match_doc = db.collection("matches").document(str(data.fixture_id)).get()
    if not match_doc.exists:
        raise HTTPException(status_code=404, detail="Partido no encontrado")

    match = match_doc.to_dict()

    # Verificar que el partido no ha comenzado
    if is_match_locked(match["kickoff"]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El partido ya comenzó, no puedes predecir"
        )

    # Verificar que no existe ya una predicción para este partido
    pred_id = get_prediction_id(uid, data.fixture_id)
    existing = db.collection("predictions").document(pred_id).get()
    if existing.exists:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya tienes una predicción para este partido, usa PUT para editarla"
        )

    new_prediction = {
        "id": pred_id,
        "uid": uid,
        "fixture_id": data.fixture_id,
        "predicted_home": data.predicted_home,
        "predicted_away": data.predicted_away,
        "points": None,
        "status": PredictionStatus.pending,
        "processed": False,
    }

    db.collection("predictions").document(pred_id).set(new_prediction)
    return enrich_prediction(new_prediction, match)


@router.put("/{fixture_id}", status_code=status.HTTP_200_OK)
async def update_prediction(
    fixture_id: int,
    data: PredictionUpdate,
    current_user: dict = Depends(get_current_user)
):
    """
    Edita una predicción existente.
    Solo permitido si el partido no ha comenzado.
    """
    uid = current_user["uid"]
    pred_id = get_prediction_id(uid, fixture_id)

    # Verificar que la predicción existe
    pred_doc = db.collection("predictions").document(pred_id).get()
    if not pred_doc.exists:
        raise HTTPException(status_code=404, detail="Predicción no encontrada")

    # Verificar que el partido no ha comenzado
    match_doc = db.collection("matches").document(str(fixture_id)).get()
    if not match_doc.exists:
        raise HTTPException(status_code=404, detail="Partido no encontrado")

    match = match_doc.to_dict()
    if is_match_locked(match["kickoff"]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El partido ya comenzó, no puedes editar tu predicción"
        )

    db.collection("predictions").document(pred_id).update({
        "predicted_home": data.predicted_home,
        "predicted_away": data.predicted_away,
    })

    updated = db.collection("predictions").document(pred_id).get().to_dict()
    return enrich_prediction(updated, match)


@router.get("/me")
async def get_my_predictions(current_user: dict = Depends(get_current_user)):
    """
    Devuelve todas las predicciones del usuario autenticado
    enriquecidas con info de cada partido.
    """
    uid = current_user["uid"]
    predictions = await get_user_predictions_with_matches(uid)
    return {"predictions": predictions, "total": len(predictions)}


@router.get("/me/stats")
async def get_my_stats(current_user: dict = Depends(get_current_user)):
    """Devuelve estadísticas personales del usuario."""
    uid = current_user["uid"]
    predictions = await get_user_predictions_with_matches(uid)

    processed = [p for p in predictions if p.get("processed")]
    pending = [p for p in predictions if not p.get("processed")]
    exact = [p for p in processed if p.get("points") == 5]
    correct_winner = [p for p in processed if p.get("points", 0) >= 1]

    return {
        "total_predictions": len(predictions),
        "processed": len(processed),
        "pending": len(pending),
        "exact_results": len(exact),
        "correct_winners": len(correct_winner),
        "total_score": current_user.get("total_score", 0),
        "accuracy": round(len(correct_winner) / len(processed) * 100, 1) if processed else 0,
    }


@router.get("/match/{fixture_id}")
async def get_match_predictions(
    fixture_id: int,
    current_user: dict = Depends(get_current_user)
):
    """
    Devuelve las predicciones de todos los usuarios para un partido.
    Solo disponible después de que el partido haya comenzado.
    """
    match_doc = db.collection("matches").document(str(fixture_id)).get()
    if not match_doc.exists:
        raise HTTPException(status_code=404, detail="Partido no encontrado")

    match = match_doc.to_dict()
    predictions = await get_match_predictions_public(fixture_id)

    return {
        "fixture_id": fixture_id,
        "match_locked": True,
        "home_team": match["home_team"]["name"],
        "away_team": match["away_team"]["name"],
        "real_score": match["score"],
        "predictions": predictions,
        "total": len(predictions),
    }


@router.post("/batch", status_code=status.HTTP_201_CREATED)
async def create_batch_predictions(
    predictions: list[PredictionCreate],
    current_user: dict = Depends(get_current_user)
):
    """
    Crea o actualiza múltiples predicciones de una sola vez.
    Ideal para que el usuario prediga todo el Mundial de un tirón.
    Omite silenciosamente los partidos que ya comenzaron.
    """
    uid = current_user["uid"]
    saved = []
    skipped = []

    for data in predictions:
        match_doc = db.collection("matches").document(str(data.fixture_id)).get()
        if not match_doc.exists:
            skipped.append({"fixture_id": data.fixture_id, "reason": "Partido no encontrado"})
            continue

        match = match_doc.to_dict()
        if is_match_locked(match["kickoff"]):
            skipped.append({"fixture_id": data.fixture_id, "reason": "Partido ya comenzó"})
            continue

        pred_id = get_prediction_id(uid, data.fixture_id)
        prediction = {
            "id": pred_id,
            "uid": uid,
            "fixture_id": data.fixture_id,
            "predicted_home": data.predicted_home,
            "predicted_away": data.predicted_away,
            "penalty_winner": data.penalty_winner,
            "points": None,
            "status": PredictionStatus.pending,
            "processed": False,
        }
        db.collection("predictions").document(pred_id).set(prediction)
        saved.append(data.fixture_id)

    return {
        "saved": len(saved),
        "skipped": len(skipped),
        "skipped_detail": skipped,
    }

@router.post("/top-scorer", status_code=status.HTTP_201_CREATED)
async def save_top_scorer(
    data: TopScorerPrediction,
    current_user: dict = Depends(get_current_user)
):
    """Guarda la predicción del máximo goleador."""
    uid = current_user["uid"]
    doc_ref = db.collection("special_predictions").document(uid)
    doc_ref.set({
        "uid":         uid,
        "player_name": data.player_name,
        "team_name":   data.team_name,
        "points":      None,
        "processed":   False,
    }, merge=True)
    return {"message": "Predicción guardada", "player_name": data.player_name}


@router.get("/top-scorer/me")
async def get_my_top_scorer(current_user: dict = Depends(get_current_user)):
    """Devuelve la predicción del máximo goleador del usuario."""
    uid = current_user["uid"]
    doc = db.collection("special_predictions").document(uid).get()
    if not doc.exists:
        return {"player_name": "", "team_name": ""}
    return doc.to_dict()