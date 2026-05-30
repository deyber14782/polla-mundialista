from app.core.firebase import db
from app.services.football_api import get_world_cup_fixtures, get_live_fixtures, get_fixture_by_id
from app.models.match import MatchStatus, MatchPhase


def map_round_to_phase(round_str: str) -> MatchPhase:
    """Convierte el string de ronda de la API al enum de fase."""
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
    """Convierte la respuesta de API-Football al formato de Firestore."""
    fixture = fixture_data["fixture"]
    teams = fixture_data["teams"]
    goals = fixture_data["goals"]
    league = fixture_data["league"]

    return {
        "fixture_id": fixture["id"],
        "phase": map_round_to_phase(league.get("round", "")).value,
        "round": league.get("round"),
        "group": league.get("round") if "group" in league.get("round", "").lower() else None,
        "home_team": {
            "id": teams["home"]["id"],
            "name": teams["home"]["name"],
            "logo": teams["home"]["logo"],
            "code": teams["home"].get("code"),
        },
        "away_team": {
            "id": teams["away"]["id"],
            "name": teams["away"]["name"],
            "logo": teams["away"]["logo"],
            "code": teams["away"].get("code"),
        },
        "kickoff": fixture["date"],
        "status": fixture["status"]["short"],
        "score": {
            "home": goals["home"],
            "away": goals["away"],
        },
        "venue": fixture.get("venue", {}).get("name"),
    }


async def seed_matches_from_api():
    """
    Pobla Firestore con todos los partidos del Mundial.
    Ejecutar una sola vez al inicio del proyecto.
    """
    fixtures = await get_world_cup_fixtures()

    if not fixtures:
        return {"seeded": 0, "message": "No se encontraron partidos"}

    batch = db.batch()
    count = 0

    for fixture_data in fixtures:
        parsed = parse_fixture(fixture_data)
        doc_ref = db.collection("matches").document(str(parsed["fixture_id"]))
        batch.set(doc_ref, parsed)
        count += 1

        # Firestore permite máximo 500 operaciones por batch
        if count % 499 == 0:
            batch.commit()
            batch = db.batch()

    batch.commit()
    return {"seeded": count, "message": f"{count} partidos guardados en Firestore"}


async def update_live_matches():
    """
    Actualiza en Firestore los partidos que están en vivo.
    Lo llama el APScheduler cada 5 minutos.
    """
    live_fixtures = await get_live_fixtures()

    if not live_fixtures:
        return {"updated": 0}

    batch = db.batch()
    count = 0

    for fixture_data in live_fixtures:
        parsed = parse_fixture(fixture_data)
        doc_ref = db.collection("matches").document(str(parsed["fixture_id"]))
        batch.update(doc_ref, {
            "status": parsed["status"],
            "score": parsed["score"],
        })
        count += 1

    batch.commit()

    # Si algún partido terminó, recalculamos puntos
    finished = [f for f in live_fixtures if f["fixture"]["status"]["short"] == "FT"]
    for fixture_data in finished:
        await calculate_points_for_match(fixture_data["fixture"]["id"])

    return {"updated": count}


async def calculate_points_for_match(fixture_id: int):
    """
    Calcula y actualiza los puntos de todos los usuarios
    que predijeron este partido.
    """
    match_doc = db.collection("matches").document(str(fixture_id)).get()
    if not match_doc.exists:
        return

    match = match_doc.to_dict()
    real_home = match["score"]["home"]
    real_away = match["score"]["away"]

    if real_home is None or real_away is None:
        return

    # Traemos todas las predicciones de este partido
    predictions = db.collection("predictions")\
        .where("fixture_id", "==", fixture_id)\
        .stream()

    for pred_doc in predictions:
        pred = pred_doc.to_dict()
        points = calculate_points(
            pred_home=pred["predicted_home"],
            pred_away=pred["predicted_away"],
            real_home=real_home,
            real_away=real_away,
        )

        # Actualizamos la predicción con los puntos obtenidos
        pred_doc.reference.update({
            "points": points,
            "processed": True,
        })

        # Actualizamos el score total del usuario
        user_ref = db.collection("users").document(pred["uid"])
        user_doc = user_ref.get()
        if user_doc.exists:
            user_data = user_doc.to_dict()
            exact = 1 if points == 5 else 0
            user_ref.update({
                "total_score": user_data.get("total_score", 0) + points,
                "predictions_count": user_data.get("predictions_count", 0) + 1,
                "exact_results": user_data.get("exact_results", 0) + exact,
            })


def calculate_points(pred_home: int, pred_away: int, real_home: int, real_away: int) -> int:
    """
    Sistema de puntuación:
    5 pts → resultado exacto
    3 pts → ganador correcto + misma diferencia de goles
    1 pt  → solo ganador o empate correcto
    0 pts → fallo total
    """
    # Resultado exacto
    if pred_home == real_home and pred_away == real_away:
        return 5

    pred_diff = pred_home - pred_away
    real_diff = real_home - real_away

    pred_winner = "home" if pred_diff > 0 else ("away" if pred_diff < 0 else "draw")
    real_winner = "home" if real_diff > 0 else ("away" if real_diff < 0 else "draw")

    # Ganador correcto + misma diferencia
    if pred_winner == real_winner and pred_diff == real_diff:
        return 3

    # Solo ganador o empate correcto
    if pred_winner == real_winner:
        return 1

    return 0