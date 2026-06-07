from app.core.firebase import db
from app.services.football_api import get_world_cup_fixtures, get_live_fixtures
from app.models.match import MatchPhase
from google.cloud.firestore_v1.base_query import FieldFilter


def map_round_to_phase(round_str: str) -> MatchPhase:
    round_lower = round_str.lower()
    if "group" in round_lower:
        return MatchPhase.group
    elif "round of 16" in round_lower or "last 16" in round_lower:
        return MatchPhase.round_of_16
    elif "quarter" in round_lower:
        return MatchPhase.quarterfinal
    elif "semi" in round_lower:
        return MatchPhase.semifinal
    elif "3rd" in round_lower or "third" in round_lower:
        return MatchPhase.third_place
    elif "final" in round_lower:
        return MatchPhase.final
    return MatchPhase.group


def parse_fixture(fixture_data: dict) -> dict:
    fixture = fixture_data["fixture"]
    teams   = fixture_data["teams"]
    goals   = fixture_data["goals"]
    league  = fixture_data["league"]

    return {
        "fixture_id": fixture["id"],
        "phase": map_round_to_phase(league.get("round", "")).value,
        "round": league.get("round"),
        "group": league.get("round") if "group" in league.get("round", "").lower() else None,
        "home_team": {
            "id":   teams["home"]["id"],
            "name": teams["home"]["name"],
            "logo": teams["home"]["logo"],
            "code": teams["home"].get("code"),
        },
        "away_team": {
            "id":   teams["away"]["id"],
            "name": teams["away"]["name"],
            "logo": teams["away"]["logo"],
            "code": teams["away"].get("code"),
        },
        "kickoff": fixture["date"],
        "status":  fixture["status"]["short"],
        "score": {
            "home": goals["home"],
            "away": goals["away"],
        },
        "venue": fixture.get("venue", {}).get("name"),
    }


async def seed_matches_from_api():
    fixtures = await get_world_cup_fixtures()
    if not fixtures:
        return {"seeded": 0, "message": "No se encontraron partidos"}

    batch = db.batch()
    count = 0
    for fixture_data in fixtures:
        parsed  = parse_fixture(fixture_data)
        doc_ref = db.collection("matches").document(str(parsed["fixture_id"]))
        batch.set(doc_ref, parsed)
        count += 1
        if count % 499 == 0:
            batch.commit()
            batch = db.batch()

    batch.commit()
    return {"seeded": count, "message": f"{count} partidos guardados en Firestore"}


async def update_live_matches():
    live_fixtures = await get_live_fixtures()
    if not live_fixtures:
        return {"updated": 0}

    batch = db.batch()
    count = 0
    for fixture_data in live_fixtures:
        parsed  = parse_fixture(fixture_data)
        doc_ref = db.collection("matches").document(str(parsed["fixture_id"]))
        batch.update(doc_ref, {
            "status": parsed["status"],
            "score":  parsed["score"],
        })
        count += 1

    batch.commit()

    finished = [f for f in live_fixtures if f["fixture"]["status"]["short"] == "FT"]
    for fixture_data in finished:
        await calculate_points_for_match(fixture_data["fixture"]["id"])

    return {"updated": count}


async def calculate_points_for_match(fixture_id: int):
    match_doc = db.collection("matches").document(str(fixture_id)).get()
    if not match_doc.exists:
        return

    match     = match_doc.to_dict()
    real_home = match["score"]["home"]
    real_away = match["score"]["away"]

    if real_home is None or real_away is None:
        return

    predictions = db.collection("predictions")\
        .where(filter=FieldFilter("fixture_id", "==", fixture_id))\
        .stream()

    for pred_doc in predictions:
        pred   = pred_doc.to_dict()
        points = calculate_points(
            pred_home=pred["predicted_home"],
            pred_away=pred["predicted_away"],
            real_home=real_home,
            real_away=real_away,
        )
        pred_doc.reference.update({"points": points, "processed": True})

        user_ref = db.collection("users").document(pred["uid"])
        user_doc = user_ref.get()
        if user_doc.exists:
            user_data = user_doc.to_dict()
            exact = 1 if points == 5 else 0
            user_ref.update({
                "total_score":      user_data.get("total_score", 0) + points,
                "predictions_count": user_data.get("predictions_count", 0) + 1,
                "exact_results":    user_data.get("exact_results", 0) + exact,
            })


def calculate_points(pred_home: int, pred_away: int, real_home: int, real_away: int) -> int:
    """
    Sistema de puntuación oficial Python Cup 2026:
    3 pts → marcador exacto
    1 pt  → resultado correcto (L-E-V)
    0 pts → fallo total
    Nota: puntos por clasificación se calculan por separado
    """
    # Marcador exacto
    if pred_home == real_home and pred_away == real_away:
        return 3

    # Solo resultado correcto (L-E-V)
    pred_result = "L" if pred_home > pred_away else ("V" if pred_home < pred_away else "E")
    real_result = "L" if real_home > real_away else ("V" if real_home < real_away else "E")

    if pred_result == real_result:
        return 1

    return 0


CLASSIFICATION_POINTS = {
    "round_of_32":  2,
    "round_of_16":  4,
    "quarterfinal": 6,
    "semifinal":    8,
    "third_place":  10,
    "final":        10,
}

WRONG_POSITION_POINTS = 1  # clasificó pero en otra posición

async def calculate_classification_points(fixture_id: int, winning_team_id: int):
    """
    Calcula puntos de clasificación cuando un equipo avanza de ronda.
    Compara contra las predicciones del bracket de cada usuario.
    """
    match_doc = db.collection("matches").document(str(fixture_id)).get()
    if not match_doc.exists:
        return

    match = match_doc.to_dict()
    phase = match.get("phase")
    pts   = CLASSIFICATION_POINTS.get(phase, 0)
    if not pts:
        return

    # Buscar todos los usuarios
    users = db.collection("users").where(
        filter=FieldFilter("role", "==", "player")
    ).stream()

    for user_doc in users:
        user = user_doc.to_dict()
        uid  = user["uid"]

        # Buscar la predicción del usuario para este partido
        pred_doc = db.collection("predictions")\
            .document(f"{uid}_{fixture_id}").get()

        if not pred_doc.exists:
            continue

        pred = pred_doc.to_dict()
        pred_home = pred.get("predicted_home", 0)
        pred_away = pred.get("predicted_away", 0)

        # Determinar ganador predicho
        if pred_home > pred_away:
            pred_winner_side = "home"
        elif pred_home < pred_away:
            pred_winner_side = "away"
        else:
            # Empate en eliminatoria — se toma local como ganador proyectado
            pred_winner_side = "home"

        # Verificar si predijo el equipo correcto
        home_id = match["home_team"]["id"]
        away_id = match["away_team"]["id"]

        if pred_winner_side == "home" and home_id == winning_team_id:
            classification_pts = pts
        elif pred_winner_side == "away" and away_id == winning_team_id:
            classification_pts = pts
        else:
            classification_pts = 0

        if classification_pts > 0:
            pred_doc.reference.update({
                "classification_pts": classification_pts
            })
            # Sumar al total del usuario
            user_ref = db.collection("users").document(uid)
            user_data = user_ref.get().to_dict()
            user_ref.update({
                "total_score": user_data.get("total_score", 0) + classification_pts
            })