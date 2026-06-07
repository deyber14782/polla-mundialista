from app.core.firebase import db
from google.cloud.firestore_v1.base_query import FieldFilter

# ── Cruces fijos de Ronda de 32 ──────────────────────────────────
# Formato: (fixture_id, equipo_local, equipo_visitante)
# donde equipo = "1A", "2B", "3rd_1", etc.
ROUND_OF_32_BRACKET = [
    # Cruces fijos primeros vs segundos
    (10101, "1A", "2B"),
    (10102, "1C", "2D"),
    (10103, "1E", "2F"),
    (10104, "1G", "2H"),
    (10105, "1I", "2J"),
    (10106, "1K", "2L"),
    (10107, "1B", "2A"),
    (10108, "1D", "2C"),
    (10109, "1F", "2E"),
    (10110, "1H", "2G"),
    (10111, "1J", "2I"),
    (10112, "1L", "2K"),
    # Cruces mejores terceros (posiciones en ranking de 3eros)
    (10113, "3rd_1", "3rd_2"),
    (10114, "3rd_3", "3rd_4"),
    (10115, "3rd_5", "3rd_6"),
    (10116, "3rd_7", "3rd_8"),
]

# Cuadro de octavos en adelante
ROUND_OF_16_BRACKET = [
    (10201, "W10101", "W10102"),
    (10202, "W10103", "W10104"),
    (10203, "W10105", "W10106"),
    (10204, "W10107", "W10108"),
    (10205, "W10109", "W10110"),
    (10206, "W10111", "W10112"),
    (10207, "W10113", "W10114"),
    (10208, "W10115", "W10116"),
]

QUARTERFINAL_BRACKET = [
    (10301, "W10201", "W10202"),
    (10302, "W10203", "W10204"),
    (10303, "W10205", "W10206"),
    (10304, "W10207", "W10208"),
]

SEMIFINAL_BRACKET = [
    (10401, "W10301", "W10302"),
    (10402, "W10303", "W10304"),
]

FINAL_BRACKET = [
    (10501, "L10401", "L10402"),   # tercer lugar
    (10601, "W10401", "W10402"),   # final
]


def calculate_group_table(group_matches: list[dict], predictions: dict) -> list[dict]:
    """
    Calcula la tabla de un grupo basado en las predicciones del usuario.
    Retorna lista de equipos ordenada por puntos, dif. goles, goles a favor.
    """
    teams = {}

    for match in group_matches:
        home_id   = match["home_team"]["code"]
        away_id   = match["away_team"]["code"]
        fixture_id = match["fixture_id"]

        # Inicializar equipos si no existen
        for team_code, team_data in [
            (home_id, match["home_team"]),
            (away_id, match["away_team"])
        ]:
            if team_code not in teams:
                teams[team_code] = {
                    "code":     team_code,
                    "name":     team_data["name"],
                    "logo":     team_data["logo"],
                    "pts":      0,
                    "pj":       0,
                    "pg":       0,
                    "pe":       0,
                    "pp":       0,
                    "gf":       0,
                    "gc":       0,
                    "dg":       0,
                }

        pred = predictions.get(fixture_id)
        if not pred:
            continue

        home_goals = pred["predicted_home"]
        away_goals = pred["predicted_away"]

        # Actualizar stats
        teams[home_id]["pj"] += 1
        teams[away_id]["pj"] += 1
        teams[home_id]["gf"] += home_goals
        teams[home_id]["gc"] += away_goals
        teams[away_id]["gf"] += away_goals
        teams[away_id]["gc"] += home_goals

        if home_goals > away_goals:
            teams[home_id]["pts"] += 3
            teams[home_id]["pg"]  += 1
            teams[away_id]["pp"]  += 1
        elif home_goals < away_goals:
            teams[away_id]["pts"] += 3
            teams[away_id]["pg"]  += 1
            teams[home_id]["pp"]  += 1
        else:
            teams[home_id]["pts"] += 1
            teams[away_id]["pts"] += 1
            teams[home_id]["pe"]  += 1
            teams[away_id]["pe"]  += 1

    # Calcular diferencia de goles
    for t in teams.values():
        t["dg"] = t["gf"] - t["gc"]

    # Ordenar: pts → dg → gf
    return sorted(
        teams.values(),
        key=lambda x: (-x["pts"], -x["dg"], -x["gf"])
    )


def get_best_third_places(all_groups_tables: dict) -> list[dict]:
    """
    De todos los terceros lugares de cada grupo,
    retorna los 8 mejores ordenados por pts, dg, gf.
    """
    third_places = []
    for group, table in all_groups_tables.items():
        if len(table) >= 3:
            third = table[2].copy()
            third["group"] = group
            third_places.append(third)

    return sorted(
        third_places,
        key=lambda x: (-x["pts"], -x["dg"], -x["gf"])
    )[:8]


async def project_bracket_for_user(uid: str) -> dict:
    """
    Calcula el cuadro eliminatorio proyectado para un usuario
    basado en sus predicciones de fase de grupos.

    Retorna un dict con los equipos proyectados para cada fixture
    de las fases eliminatorias.
    """
    # 1. Traer todos los partidos de grupos
    group_matches_docs = db.collection("matches")\
        .where(filter=FieldFilter("phase", "==", "group"))\
        .stream()
    group_matches = [doc.to_dict() for doc in group_matches_docs]

    # 2. Traer predicciones del usuario para grupos
    user_preds_docs = db.collection("predictions")\
        .where(filter=FieldFilter("uid", "==", uid))\
        .stream()

    predictions = {}
    for doc in user_preds_docs:
        pred = doc.to_dict()
        predictions[pred["fixture_id"]] = pred

    # 3. Calcular tabla de cada grupo
    groups = {}
    for match in group_matches:
        group = match.get("group", "")
        if group not in groups:
            groups[group] = []
        groups[group].append(match)

    group_tables = {}
    for group, matches in groups.items():
        group_tables[group] = calculate_group_table(matches, predictions)

    # 4. Extraer clasificados
    classified = {}
    for group, table in group_tables.items():
        group_letter = group.replace("Group ", "")
        if len(table) >= 1:
            classified[f"1{group_letter}"] = table[0]
        if len(table) >= 2:
            classified[f"2{group_letter}"] = table[1]

    # 5. Mejores terceros
    best_thirds = get_best_third_places(group_tables)
    for i, third in enumerate(best_thirds):
        classified[f"3rd_{i+1}"] = third

    # 6. Armar fixture de ronda de 32
    bracket = {}
    for fixture_id, home_slot, away_slot in ROUND_OF_32_BRACKET:
        bracket[fixture_id] = {
            "home_team": classified.get(home_slot, _tbd_team(home_slot)),
            "away_team": classified.get(away_slot, _tbd_team(away_slot)),
        }

    # 7. Proyectar rondas siguientes basado en predicciones del usuario
    bracket = _project_knockout_round(
        bracket, ROUND_OF_16_BRACKET, predictions, uid
    )
    bracket = _project_knockout_round(
        bracket, QUARTERFINAL_BRACKET, predictions, uid
    )
    bracket = _project_knockout_round(
        bracket, SEMIFINAL_BRACKET, predictions, uid
    )
    bracket = _project_final(bracket, predictions)

    return {
        "bracket":      bracket,
        "group_tables": {
            k: list(v) for k, v in group_tables.items()
        },
        "classified":   classified,
        "best_thirds":  best_thirds,
    }


def _project_knockout_round(
    bracket: dict,
    round_bracket: list,
    predictions: dict,
    uid: str
) -> dict:
    """
    Para cada partido de una ronda, determina el equipo proyectado
    basado en la predicción del usuario del partido anterior.
    """
    for fixture_id, home_slot, away_slot in round_bracket:
        # Extraer fixture_id del partido anterior del slot
        home_prev_id = int(home_slot.replace("W", ""))
        away_prev_id = int(away_slot.replace("W", ""))

        home_team = _get_winner_from_prediction(
            home_prev_id, bracket, predictions
        )
        away_team = _get_winner_from_prediction(
            away_prev_id, bracket, predictions
        )

        bracket[fixture_id] = {
            "home_team": home_team,
            "away_team": away_team,
        }

    return bracket


def _get_winner_from_prediction(
    prev_fixture_id: int,
    bracket: dict,
    predictions: dict
) -> dict:
    """
    Dado el fixture_id de un partido anterior,
    devuelve el equipo ganador según la predicción del usuario.
    """
    prev_match = bracket.get(prev_fixture_id)
    if not prev_match:
        return _tbd_team(f"W{prev_fixture_id}")

    pred = predictions.get(prev_fixture_id)
    if not pred:
        return _tbd_team(f"W{prev_fixture_id}")

    home_goals = pred["predicted_home"]
    away_goals = pred["predicted_away"]

    # En eliminatorias no hay empate — si predijo empate
    # asumimos que gana el local (simplificación)
    if home_goals >= away_goals:
        return prev_match["home_team"]
    else:
        return prev_match["away_team"]


def _project_final(bracket: dict, predictions: dict) -> dict:
    """Proyecta el tercer lugar y la final."""
    # Tercer lugar: perdedores de semis
    sf1 = bracket.get(10401)
    sf2 = bracket.get(10402)

    if sf1 and sf2:
        pred_sf1 = predictions.get(10401)
        pred_sf2 = predictions.get(10402)

        loser_sf1 = _get_loser_from_prediction(10401, bracket, predictions)
        loser_sf2 = _get_loser_from_prediction(10402, bracket, predictions)

        bracket[10501] = {
            "home_team": loser_sf1,
            "away_team": loser_sf2,
        }

        winner_sf1 = _get_winner_from_prediction(10401, bracket, predictions)
        winner_sf2 = _get_winner_from_prediction(10402, bracket, predictions)

        bracket[10601] = {
            "home_team": winner_sf1,
            "away_team": winner_sf2,
        }

    return bracket


def _get_loser_from_prediction(
    prev_fixture_id: int,
    bracket: dict,
    predictions: dict
) -> dict:
    """Devuelve el perdedor de un partido según la predicción."""
    prev_match = bracket.get(prev_fixture_id)
    if not prev_match:
        return _tbd_team(f"L{prev_fixture_id}")

    pred = predictions.get(prev_fixture_id)
    if not pred:
        return _tbd_team(f"L{prev_fixture_id}")

    if pred["predicted_home"] >= pred["predicted_away"]:
        return prev_match["away_team"]
    else:
        return prev_match["home_team"]


def _tbd_team(slot: str) -> dict:
    return {
        "id":   999,
        "name": slot,
        "code": "TBD",
        "logo": "https://flagcdn.com/w80/un.png",
    }