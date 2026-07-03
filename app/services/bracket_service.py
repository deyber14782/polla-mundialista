from app.core.firebase import db
from google.cloud.firestore_v1.base_query import FieldFilter

ROUND_OF_32_BRACKET = [
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
    (10113, "3rd_1", "3rd_2"),
    (10114, "3rd_3", "3rd_4"),
    (10115, "3rd_5", "3rd_6"),
    (10116, "3rd_7", "3rd_8"),
]

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


def calculate_group_table(group_matches: list, predictions: dict) -> list:
    teams = {}

    for match in group_matches:
        home_code = match["home_team"]["code"]
        away_code = match["away_team"]["code"]

        for code, data in [(home_code, match["home_team"]), (away_code, match["away_team"])]:
            if code not in teams:
                teams[code] = {
                    "code": code,
                    "name": data["name"],
                    "logo": data["logo"],
                    "pts": 0, "pj": 0, "pg": 0, "pe": 0, "pp": 0,
                    "gf": 0, "gc": 0, "dg": 0,
                    "h2h": {},
                }

        pred = predictions.get(match["fixture_id"])
        if not pred:
            continue

        hg = pred.get("predicted_home", 0)
        ag = pred.get("predicted_away", 0)

        teams[home_code]["pj"] += 1
        teams[away_code]["pj"] += 1
        teams[home_code]["gf"] += hg
        teams[home_code]["gc"] += ag
        teams[away_code]["gf"] += ag
        teams[away_code]["gc"] += hg

        if home_code not in teams[away_code]["h2h"]:
            teams[away_code]["h2h"][home_code] = {"pts": 0, "dg": 0, "gf": 0}
        if away_code not in teams[home_code]["h2h"]:
            teams[home_code]["h2h"][away_code] = {"pts": 0, "dg": 0, "gf": 0}

        if hg > ag:
            teams[home_code]["pts"] += 3
            teams[home_code]["pg"]  += 1
            teams[away_code]["pp"]  += 1
            teams[home_code]["h2h"][away_code]["pts"] += 3
        elif hg < ag:
            teams[away_code]["pts"] += 3
            teams[away_code]["pg"]  += 1
            teams[home_code]["pp"]  += 1
            teams[away_code]["h2h"][home_code]["pts"] += 3
        else:
            teams[home_code]["pts"] += 1
            teams[away_code]["pts"] += 1
            teams[home_code]["pe"]  += 1
            teams[away_code]["pe"]  += 1
            teams[home_code]["h2h"][away_code]["pts"] += 1
            teams[away_code]["h2h"][home_code]["pts"] += 1

        teams[home_code]["h2h"][away_code]["dg"] += (hg - ag)
        teams[away_code]["h2h"][home_code]["dg"] += (ag - hg)
        teams[home_code]["h2h"][away_code]["gf"] += hg
        teams[away_code]["h2h"][home_code]["gf"] += ag

    for t in teams.values():
        t["dg"] = t["gf"] - t["gc"]

    return sorted(
        teams.values(),
        key=lambda x: (
            -x["pts"], -x["dg"], -x["gf"],
            -(x["h2h"].get(list(teams.keys())[0], {}).get("pts", 0))
        )
    )


def get_best_third_places(all_groups_tables: dict) -> list:
    third_places = []
    for group, table in all_groups_tables.items():
        if len(table) >= 3:
            third = dict(table[2])
            third["group"] = group
            third_places.append(third)

    return sorted(
        third_places,
        key=lambda x: (-x["pts"], -x["dg"], -x["gf"])
    )[:8]


def _tbd_team(slot: str) -> dict:
    return {
        "id": 999, "name": slot, "code": "TBD",
        "logo": "https://flagcdn.com/w80/un.png",
    }


def _get_winner_from_prediction(
    prev_fixture_id: int,
    bracket: dict,
    predictions: dict
) -> dict:
    prev_match = bracket.get(prev_fixture_id)
    if not prev_match:
        return _tbd_team(f"W{prev_fixture_id}")

    pred = predictions.get(prev_fixture_id)
    if not pred:
        return _tbd_team(f"W{prev_fixture_id}")

    hg = pred.get("predicted_home", 0)
    ag = pred.get("predicted_away", 0)

    if hg > ag:
        return prev_match["home_team"]
    elif hg < ag:
        return prev_match["away_team"]
    else:
        # Empate — usar penalty_winner
        penalty_winner = pred.get("penalty_winner", "home")
        if penalty_winner == "home":
            return prev_match["home_team"]
        else:
            return prev_match["away_team"]


def _get_loser_from_prediction(prev_fixture_id: int, bracket: dict, predictions: dict) -> dict:
    prev_match = bracket.get(prev_fixture_id)
    if not prev_match:
        return _tbd_team(f"L{prev_fixture_id}")

    pred = predictions.get(prev_fixture_id)
    if not pred:
        return _tbd_team(f"L{prev_fixture_id}")

    hg = pred.get("predicted_home", 0)
    ag = pred.get("predicted_away", 0)

    if hg >= ag:
        return prev_match["away_team"]
    else:
        return prev_match["home_team"]


def _project_knockout_round(bracket: dict, round_bracket: list, predictions: dict) -> dict:
    for fixture_id, home_slot, away_slot in round_bracket:
        home_prev_id = int(home_slot.replace("W", ""))
        away_prev_id = int(away_slot.replace("W", ""))
        bracket[fixture_id] = {
            "home_team": _get_winner_from_prediction(home_prev_id, bracket, predictions),
            "away_team": _get_winner_from_prediction(away_prev_id, bracket, predictions),
        }
    return bracket


async def project_bracket_for_user(uid: str) -> dict:
    # 1. Partidos de grupos
    group_docs = db.collection("matches")\
        .where(filter=FieldFilter("phase", "==", "group"))\
        .stream()
    group_matches = [doc.to_dict() for doc in group_docs]

    # 2. Predicciones del usuario
    pred_docs = db.collection("predictions")\
        .where(filter=FieldFilter("uid", "==", uid))\
        .stream()
    predictions = {doc.to_dict()["fixture_id"]: doc.to_dict() for doc in pred_docs}

    # 3. Calcular tablas por grupo
    groups = {}
    for match in group_matches:
        g = match.get("group", "")
        if g not in groups:
            groups[g] = []
        groups[g].append(match)

    group_tables = {}
    for group, matches in groups.items():
        group_tables[group] = calculate_group_table(matches, predictions)

    # 4. Clasificados
    classified = {}
    for group, table in group_tables.items():
        letter = group.replace("Group ", "")
        if len(table) >= 1: classified[f"1{letter}"] = table[0]
        if len(table) >= 2: classified[f"2{letter}"] = table[1]

    # 5. Mejores terceros
    best_thirds = get_best_third_places(group_tables)
    for i, third in enumerate(best_thirds):
        classified[f"3rd_{i+1}"] = third

    # 6. Ronda de 32
    bracket = {}
    for fixture_id, home_slot, away_slot in ROUND_OF_32_BRACKET:
        bracket[fixture_id] = {
            "home_team": classified.get(home_slot, _tbd_team(home_slot)),
            "away_team": classified.get(away_slot, _tbd_team(away_slot)),
        }

    # 7. Rondas siguientes
    bracket = _project_knockout_round(bracket, ROUND_OF_16_BRACKET, predictions)
    bracket = _project_knockout_round(bracket, QUARTERFINAL_BRACKET, predictions)
    bracket = _project_knockout_round(bracket, SEMIFINAL_BRACKET, predictions)

    # 8. Final y tercer lugar
    bracket[10501] = {
        "home_team": _get_loser_from_prediction(10401, bracket, predictions),
        "away_team": _get_loser_from_prediction(10402, bracket, predictions),
    }
    bracket[10601] = {
        "home_team": _get_winner_from_prediction(10401, bracket, predictions),
        "away_team": _get_winner_from_prediction(10402, bracket, predictions),
    }

    return {
        "bracket":      bracket,
        "group_tables": {k: list(v) for k, v in group_tables.items()},
        "classified":   classified,
        "best_thirds":  best_thirds,
    }

