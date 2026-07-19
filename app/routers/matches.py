from fastapi import APIRouter, HTTPException, Depends
from app.core.firebase import db
from app.core.auth import get_current_user, require_admin
from app.services.matches_service import seed_matches_from_api
from app.services.football_api import get_world_cup_league_id
from google.cloud.firestore_v1.base_query import FieldFilter
from app.core import cache
import httpx
from app.core.config import settings
from app.core import cache
from pydantic import BaseModel
from typing import Optional



router = APIRouter(prefix="/matches", tags=["Matches"])

class SetTeamsBody(BaseModel):
    fixture_id: int
    home_code: str
    away_code: str
    kickoff: Optional[str] = None  # ISO format opcional

def _get_all_matches_cached():
    """Lee matches de caché o Firestore. Cachea 5 min."""
    cached = cache.get("all_matches")
    if cached is not None:
        return cached

    docs = db.collection("matches").order_by("kickoff").stream()
    matches = [doc.to_dict() for doc in docs]
    cache.set("all_matches", matches, ttl=300)
    return matches


def get_matches_dict_cached() -> dict:
    """Devuelve {fixture_id: match_dict} — usado por otros módulos."""
    cached = cache.get("matches_dict")
    if cached is not None:
        return cached

    all_matches = _get_all_matches_cached()
    matches_dict = {m["fixture_id"]: m for m in all_matches}
    cache.set("matches_dict", matches_dict, ttl=300)
    return matches_dict


@router.get("")
async def get_all_matches(
    phase: str = None,
    current_user: dict = Depends(get_current_user)
):
    matches = _get_all_matches_cached()

    if phase:
        matches = [m for m in matches if m.get("phase") == phase]

    return {"matches": matches}


@router.post("/seed")
async def seed_matches(current_user: dict = Depends(require_admin)):
    result = await seed_matches_from_api()
    cache.invalidate("all_matches", "matches_dict")
    return result


@router.get("/admin/check-league-id")
async def check_league_id(current_user: dict = Depends(require_admin)):
    league_id = await get_world_cup_league_id()
    return {"world_cup_league_id": league_id}


@router.get("/admin/search-leagues")
async def search_leagues(
    name: str = "World Cup",
    current_user: dict = Depends(require_admin)
):
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://v3.football.api-sports.io/leagues",
            headers={"x-apisports-key": settings.API_FOOTBALL_KEY},
            params={"name": name},
            timeout=15.0
        )
        data = response.json()
        leagues = data.get("response", [])
        return {
            "total": len(leagues),
            "leagues": [
                {
                    "id": l["league"]["id"],
                    "name": l["league"]["name"],
                    "type": l["league"]["type"],
                    "seasons": [s["year"] for s in l["seasons"][-3:]]
                }
                for l in leagues
            ]
        }


@router.get("/bracket/me")
async def get_my_bracket(current_user: dict = Depends(get_current_user)):
    from app.services.bracket_service import project_bracket_for_user

    uid = current_user["uid"]
    matches_dict = get_matches_dict_cached()

    # Leer predicciones del usuario (1 sola query)
    predictions_docs = db.collection("predictions")\
        .where(filter=FieldFilter("uid", "==", uid))\
        .stream()

    user_group_preds = 0
    for p in predictions_docs:
        pred = p.to_dict()
        match = matches_dict.get(pred["fixture_id"])
        if match and match.get("phase") == "group":
            user_group_preds += 1

    total_group_matches = len([m for m in matches_dict.values() if m.get("phase") == "group"])

    if user_group_preds < total_group_matches:
        raise HTTPException(
            status_code=400,
            detail=f"Debes predecir todos los partidos de grupos primero. "
                   f"Tienes {user_group_preds} de {total_group_matches}."
        )

    result = await project_bracket_for_user(uid)
    return result


@router.get("/{fixture_id}")
async def get_match(fixture_id: int, current_user: dict = Depends(get_current_user)):
    matches_dict = get_matches_dict_cached()
    match = matches_dict.get(fixture_id)
    if not match:
        raise HTTPException(status_code=404, detail="Partido no encontrado")
    return match

@router.post("/admin/force-sync")
async def force_sync(current_user: dict = Depends(require_admin)):
    from app.services.football_api import get_world_cup_fixtures
    from app.services.matches_service import parse_fixture, calculate_points_for_match

    # Mapeo español (Firestore) → inglés (API)
    NAME_MAP = {
        "méxico": "mexico",
        "sudáfrica": "south africa",
        "corea del sur": "south korea",
        "chequia": "czech republic",
        "canadá": "canada",
        "bosnia-herzegovina": "bosnia & herzegovina",
        "catar": "qatar",
        "suiza": "switzerland",
        "brasil": "brazil",
        "haití": "haiti",
        "escocia": "scotland",
        "marruecos": "morocco",
        "estados unidos": "usa",
        "turquía": "turkey",
        "alemania": "germany",
        "curazao": "curacao",
        "costa de marfil": "ivory coast",
        "países bajos": "netherlands",
        "japón": "japan",
        "suecia": "sweden",
        "túnez": "tunisia",
        "bélgica": "belgium",
        "egipto": "egypt",
        "irán": "iran",
        "nueva zelanda": "new zealand",
        "españa": "spain",
        "cabo verde": "cape verde",
        "arabia saudita": "saudi arabia",
        "francia": "france",
        "senegal": "senegal",
        "irak": "iraq",
        "noruega": "norway",
        "argentina": "argentina",
        "argelia": "algeria",
        "austria": "austria",
        "jordania": "jordan",
        "portugal": "portugal",
        "rd congo": "dr congo",
        "uzbekistán": "uzbekistan",
        "colombia": "colombia",
        "inglaterra": "england",
        "croacia": "croatia",
        "ghana": "ghana",
        "panamá": "panama",
        "ecuador": "ecuador",
        "uruguay": "uruguay",
        "türkiye": "turkey",
        "curaçao": "curacao",
        "cape verde islands": "cape verde",
        "rd congo": "dr congo",
        "congo dr": "dr congo",
        "czechia": "czech republic",
    }

    def normalize(name):
        n = name.lower().strip()
        return NAME_MAP.get(n, n)

    fixtures = await get_world_cup_fixtures()
    if not fixtures:
        return {"error": "La API no devolvió fixtures", "updated": 0}

    api_lookup = {}
    for f in fixtures:
        parsed = parse_fixture(f)
        home = normalize(parsed["home_team"]["name"])
        away = normalize(parsed["away_team"]["name"])
        ko_date = parsed["kickoff"][:10]
        api_lookup[(home, away, ko_date)] = parsed

    all_docs = list(db.collection("matches").stream())
    updated = 0
    points_calculated = 0
    not_found = []

    for doc in all_docs:
        m = doc.to_dict()
        home = normalize(m["home_team"]["name"])
        away = normalize(m["away_team"]["name"])
        ko_date = m["kickoff"][:10]

        api_match = api_lookup.get((home, away, ko_date))
        if not api_match:
            api_match = api_lookup.get((away, home, ko_date))

        if not api_match:
            if m.get("status") == "NS":
                not_found.append(f"{m['home_team']['name']} vs {m['away_team']['name']} ({ko_date})")
            continue

        doc.reference.update({
            "status": api_match["status"],
            "score": api_match["score"],
        })
        updated += 1

        if api_match["status"] == "FT" and api_match["score"]["home"] is not None:
            await calculate_points_for_match(int(m["fixture_id"]))
            points_calculated += 1

    cache.invalidate("all_matches", "matches_dict", "ranking")

    return {
        "total_from_api": len(fixtures),
        "updated": updated,
        "points_calculated": points_calculated,
        "not_matched": not_found[:20],
    }

@router.get("/admin/debug-api")
async def debug_api(current_user: dict = Depends(require_admin)):
    import httpx
    from app.core.config import settings
    
    results = {}
    
    async with httpx.AsyncClient() as client:
        # Test 1: fixtures con league=1, season=2026
        r1 = await client.get(
            "https://v3.football.api-sports.io/fixtures",
            headers={"x-apisports-key": settings.API_FOOTBALL_KEY},
            params={"league": 1, "season": 2026},
            timeout=15.0
        )
        d1 = r1.json()
        results["test1_league1_2026"] = {
            "results": d1.get("results", 0),
            "errors": d1.get("errors", {}),
            "first": d1.get("response", [])[:1]
        }
        
        # Test 2: fixtures en vivo del mundial
        r2 = await client.get(
            "https://v3.football.api-sports.io/fixtures",
            headers={"x-apisports-key": settings.API_FOOTBALL_KEY},
            params={"league": 1, "season": 2026, "status": "FT"},
            timeout=15.0
        )
        d2 = r2.json()
        results["test2_finished"] = {
            "results": d2.get("results", 0),
            "errors": d2.get("errors", {}),
        }
        
        # Test 3: fixtures de hoy
        from datetime import date
        r3 = await client.get(
            "https://v3.football.api-sports.io/fixtures",
            headers={"x-apisports-key": settings.API_FOOTBALL_KEY},
            params={"date": str(date.today())},
            timeout=15.0
        )
        d3 = r3.json()
        results["test3_today"] = {
            "results": d3.get("results", 0),
            "errors": d3.get("errors", {}),
        }
        
        # Test 4: status de la cuenta
        r4 = await client.get(
            "https://v3.football.api-sports.io/status",
            headers={"x-apisports-key": settings.API_FOOTBALL_KEY},
            timeout=15.0
        )
        results["test4_account"] = r4.json().get("response", {})
    
    return results

@router.get("/admin/debug-names")
async def debug_names(current_user: dict = Depends(require_admin)):
    from app.services.football_api import get_world_cup_fixtures
    from app.services.matches_service import parse_fixture
    
    fixtures = await get_world_cup_fixtures()
    return {
        "total": len(fixtures),
        "matches": [
            {
                "home": parse_fixture(f)["home_team"]["name"],
                "away": parse_fixture(f)["away_team"]["name"],
                "date": parse_fixture(f)["kickoff"][:10],
                "status": parse_fixture(f)["status"],
                "score_home": parse_fixture(f)["score"]["home"],
                "score_away": parse_fixture(f)["score"]["away"],
            }
            for f in fixtures
        ]
    }

@router.post("/admin/recalculate-all")
async def recalculate_all(current_user: dict = Depends(require_admin)):
    """Resetea puntos y recalcula. Usuarios creados después del kickoff → 0 pts."""
    from app.services.matches_service import calculate_points
    from datetime import datetime, timezone
    from firebase_admin import auth as firebase_auth

    # 1. Resetear usuarios
    users = list(db.collection("users").stream())
    for u in users:
        u.reference.update({"total_score": 0, "exact_results": 0, "predictions_count": 0})

    # 2. Cargar matches
    matches_dict = {doc.to_dict()["fixture_id"]: doc.to_dict()
                    for doc in db.collection("matches").stream()}

    # 3. Cache de fechas de creación de usuarios (para no consultar Auth N veces)
    user_created_cache = {}

    def get_user_created(uid):
        if uid in user_created_cache:
            return user_created_cache[uid]
        try:
            auth_user = firebase_auth.get_user(uid)
            created_ms = auth_user.user_metadata.creation_timestamp
            created_time = datetime.fromtimestamp(created_ms / 1000, tz=timezone.utc)
            user_created_cache[uid] = created_time
            return created_time
        except:
            user_created_cache[uid] = None
            return None

    # 4. Procesar predicciones
    all_preds = list(db.collection("predictions").stream())
    processed_count = 0
    late_count = 0

    for pred_doc in all_preds:
        pred = pred_doc.to_dict()
        fixture_id = pred.get("fixture_id")
        uid = pred.get("uid")
        match = matches_dict.get(fixture_id)

        if not match or match.get("status") != "FT":
            pred_doc.reference.update({"points": None, "processed": False, "status": "pending"})
            continue

        real_home = match["score"]["home"]
        real_away = match["score"]["away"]
        if real_home is None or real_away is None:
            continue

        # Verificar si el usuario fue creado después del kickoff
        kickoff_str = match.get("kickoff", "")
        is_late = False

        try:
            kickoff_time = datetime.fromisoformat(kickoff_str.replace("Z", "+00:00"))
            created_time = get_user_created(uid)
            if created_time and created_time > kickoff_time:
                is_late = True
        except:
            pass

        if is_late:
            pred_doc.reference.update({"points": 0, "processed": True, "status": "processed"})
            late_count += 1
            continue

        # Calcular puntos normalmente
        points = calculate_points(
            pred_home=pred.get("predicted_home", 0),
            pred_away=pred.get("predicted_away", 0),
            real_home=real_home,
            real_away=real_away,
        )

        pred_doc.reference.update({"points": points, "processed": True, "status": "processed"})

        # Actualizar usuario
        if uid:
            user_ref = db.collection("users").document(uid)
            user_doc = user_ref.get()
            if user_doc.exists:
                ud = user_doc.to_dict()
                exact = 1 if points == 3 else 0
                user_ref.update({
                    "total_score": ud.get("total_score", 0) + points,
                    "exact_results": ud.get("exact_results", 0) + exact,
                })

        processed_count += 1

    # 5. Actualizar predictions_count
    for u in db.collection("users").stream():
        uid = u.to_dict().get("uid")
        if not uid:
            continue
        count = sum(1 for _ in db.collection("predictions")
            .where(filter=FieldFilter("uid", "==", uid)).stream())
        u.reference.update({"predictions_count": count})

    cache.invalidate("all_matches", "matches_dict", "ranking")

    return {
        "users_reset": len(users),
        "predictions_total": len(all_preds),
        "processed": processed_count,
        "late_predictions": late_count,
    }

@router.get("/admin/debug-api2")
async def debug_api2(current_user: dict = Depends(require_admin)):
    import httpx
    from app.core.config import settings
    from datetime import date, timedelta
    
    results = {}
    
    async with httpx.AsyncClient() as client:
        # Check account status
        r0 = await client.get(
            "https://v3.football.api-sports.io/status",
            headers={"x-apisports-key": settings.API_FOOTBALL_KEY},
            timeout=15.0
        )
        results["account"] = r0.json().get("response", {})
        
        # Check each day individually
        for days_ago in range(5, -1, -1):
            d = date.today() - timedelta(days=days_ago)
            r = await client.get(
                "https://v3.football.api-sports.io/fixtures",
                headers={"x-apisports-key": settings.API_FOOTBALL_KEY},
                params={"date": str(d)},
                timeout=15.0
            )
            data = r.json()
            all_fixtures = data.get("response", [])
            wc = [f for f in all_fixtures if f.get("league", {}).get("id") == 1]
            results[str(d)] = {
                "total_all": len(all_fixtures),
                "world_cup": len(wc),
                "errors": data.get("errors", {}),
                "wc_matches": [
                    f"{f['teams']['home']['name']} vs {f['teams']['away']['name']} ({f['fixture']['status']['short']})"
                    for f in wc
                ]
            }
    
    return results

@router.post("/admin/sync-knockouts")
async def sync_knockouts(current_user: dict = Depends(require_admin)):
    """Sincroniza eliminatorias por orden cronológico con la API."""
    from app.services.football_api import get_world_cup_fixtures
    from app.services.matches_service import parse_fixture

    fixtures = await get_world_cup_fixtures()
    if not fixtures:
        return {"error": "API sin datos", "updated": 0}

    # Parsear y filtrar solo knockouts de la API (no group stage)
    # La API marca la ronda en league.round
    api_ko = []
    for f in fixtures:
        round_name = f.get("league", {}).get("round", "").lower()
        if "group" in round_name:
            continue
        parsed = parse_fixture(f)
        api_ko.append(parsed)

    # Ordenar por kickoff
    api_ko.sort(key=lambda x: x["kickoff"])

    # Traer knockouts de Firestore ordenados por kickoff
    ko_docs = []
    for doc in db.collection("matches").stream():
        m = doc.to_dict()
        if m.get("phase") != "group":
            ko_docs.append((doc, m))
    ko_docs.sort(key=lambda x: x[1]["kickoff"])

    # Emparejar por orden cronológico
    updated = 0
    detail = []
    for i, (doc, m) in enumerate(ko_docs):
        if i >= len(api_ko):
            break
        api_match = api_ko[i]
        doc.reference.update({
            "home_team": api_match["home_team"],
            "away_team": api_match["away_team"],
            "kickoff": api_match["kickoff"],
            "status": api_match["status"],
            "score": api_match["score"],
        })
        updated += 1
        detail.append(f'{m["fixture_id"]}: {api_match["home_team"]["name"]} vs {api_match["away_team"]["name"]} ({api_match["status"]})')

    cache.invalidate("all_matches", "matches_dict", "ranking")

    return {
        "api_knockouts": len(api_ko),
        "firestore_knockouts": len(ko_docs),
        "updated": updated,
        "detail": detail,
    }

@router.get("/admin/preview-qualified")
async def preview_qualified(current_user: dict = Depends(require_admin)):
    """Muestra quiénes clasificaron a 32avos según resultados reales. NO toca puntos."""
    from app.services.bracket_service import calculate_group_table, get_best_third_places

    group_docs = db.collection("matches")\
        .where(filter=FieldFilter("phase", "==", "group"))\
        .stream()
    group_matches = [doc.to_dict() for doc in group_docs]

    real_results = {}
    for m in group_matches:
        if m.get("status") == "FT" and m["score"]["home"] is not None:
            real_results[m["fixture_id"]] = {
                "predicted_home": m["score"]["home"],
                "predicted_away": m["score"]["away"],
            }

    groups = {}
    for match in group_matches:
        g = match.get("group", "")
        if g not in groups:
            groups[g] = []
        groups[g].append(match)

    output = {}
    real_tables = {}
    for group in sorted(groups.keys()):
        table = calculate_group_table(groups[group], real_results)
        real_tables[group] = table
        output[group] = [
            {
                "pos": i + 1,
                "team": t["name"],
                "pts": t["pts"],
                "dg": t["dg"],
                "gf": t["gf"],
                "qualifies": i < 2,
            }
            for i, t in enumerate(table)
        ]

    # Mejores terceros
    thirds = get_best_third_places(real_tables)
    best_thirds = [{"team": t["name"], "group": t.get("group", "?"), "pts": t["pts"], "dg": t["dg"]} for t in thirds]

    # Contar partidos jugados
    played = sum(1 for m in group_matches if m.get("status") == "FT")

    return {
        "group_matches_played": f"{played}/{len(group_matches)}",
        "tables": output,
        "best_thirds_qualified": best_thirds,
    }

@router.post("/admin/calculate-group-classification")
async def calculate_group_classification(current_user: dict = Depends(require_admin)):
    """Da 2 pts por cada equipo que el usuario proyectó que clasificaba a 32avos."""
    from app.services.bracket_service import calculate_group_table, get_best_third_places

    # 1. Partidos de grupos
    group_docs = db.collection("matches")\
        .where(filter=FieldFilter("phase", "==", "group"))\
        .stream()
    group_matches = [doc.to_dict() for doc in group_docs]

    # 2. Calcular CLASIFICADOS REALES (según resultados reales)
    real_results = {}
    for m in group_matches:
        if m.get("status") == "FT" and m["score"]["home"] is not None:
            real_results[m["fixture_id"]] = {
                "predicted_home": m["score"]["home"],
                "predicted_away": m["score"]["away"],
            }

    groups = {}
    for match in group_matches:
        g = match.get("group", "")
        if g not in groups:
            groups[g] = []
        groups[g].append(match)

    # Equipos realmente clasificados (1ros, 2dos, mejores terceros)
    real_qualified = set()  # set de team ids
    real_tables = {}
    for group, matches in groups.items():
        table = calculate_group_table(matches, real_results)
        real_tables[group] = table
        if len(table) >= 1: real_qualified.add(table[0]["code"])
        if len(table) >= 2: real_qualified.add(table[1]["code"])

    real_thirds = get_best_third_places(real_tables)
    for third in real_thirds:
        real_qualified.add(third["code"])

    # 3. Para cada usuario, calcular SU proyección y comparar
    users = list(db.collection("users")
        .where(filter=FieldFilter("role", "==", "player")).stream())

    results = []
    for user_doc in users:
        user = user_doc.to_dict()
        uid = user["uid"]

        # Predicciones del usuario
        pred_docs = db.collection("predictions")\
            .where(filter=FieldFilter("uid", "==", uid))\
            .stream()
        user_preds = {p.to_dict()["fixture_id"]: p.to_dict() for p in pred_docs}

        # Calcular tablas proyectadas del usuario
        user_qualified = set()
        for group, matches in groups.items():
            table = calculate_group_table(matches, user_preds)
            if len(table) >= 1: user_qualified.add(table[0]["code"])
            if len(table) >= 2: user_qualified.add(table[1]["code"])

        # Mejores terceros proyectados
        user_tables = {g: calculate_group_table(m, user_preds) for g, m in groups.items()}
        user_thirds = get_best_third_places(user_tables)
        for third in user_thirds:
            user_qualified.add(third["code"])

        # Comparar: cuántos equipos proyectados están en los reales
        correct = user_qualified & real_qualified
        classification_pts = len(correct) * 2

        # Guardar en el usuario (campo separado para no duplicar)
        prev_class_pts = user.get("classification_pts", 0)
        user_doc.reference.update({
            "classification_pts": classification_pts,
            "total_score": user.get("total_score", 0) - prev_class_pts + classification_pts,
        })

        results.append({
            "name": user.get("display_name", ""),
            "correct_teams": len(correct),
            "points": classification_pts,
        })

    cache.invalidate("ranking")

    return {
        "real_qualified_count": len(real_qualified),
        "users_processed": len(results),
        "results": sorted(results, key=lambda x: -x["points"]),
    }

@router.get("/admin/preview-classification-points")
async def preview_classification_points(current_user: dict = Depends(require_admin)):
    """Muestra puntos de clasificación que ganaría cada usuario. NO guarda nada."""
    from app.services.bracket_service import calculate_group_table, get_best_third_places

    group_docs = db.collection("matches")\
        .where(filter=FieldFilter("phase", "==", "group"))\
        .stream()
    group_matches = [doc.to_dict() for doc in group_docs]

    # Clasificados reales
    real_results = {}
    for m in group_matches:
        if m.get("status") == "FT" and m["score"]["home"] is not None:
            real_results[m["fixture_id"]] = {
                "predicted_home": m["score"]["home"],
                "predicted_away": m["score"]["away"],
            }

    groups = {}
    for match in group_matches:
        g = match.get("group", "")
        if g not in groups:
            groups[g] = []
        groups[g].append(match)

    real_qualified = set()
    real_tables = {}
    for group, matches in groups.items():
        table = calculate_group_table(matches, real_results)
        real_tables[group] = table
        if len(table) >= 1: real_qualified.add(table[0]["code"])
        if len(table) >= 2: real_qualified.add(table[1]["code"])
    real_thirds = get_best_third_places(real_tables)
    for third in real_thirds:
        real_qualified.add(third["code"])

    users = list(db.collection("users")
        .where(filter=FieldFilter("role", "==", "player")).stream())

    results = []
    for user_doc in users:
        user = user_doc.to_dict()
        uid = user["uid"]

        pred_docs = db.collection("predictions")\
            .where(filter=FieldFilter("uid", "==", uid))\
            .stream()
        user_preds = {p.to_dict()["fixture_id"]: p.to_dict() for p in pred_docs}

        user_qualified = set()
        user_tables = {g: calculate_group_table(m, user_preds) for g, m in groups.items()}
        for group, table in user_tables.items():
            if len(table) >= 1: user_qualified.add(table[0]["code"])
            if len(table) >= 2: user_qualified.add(table[1]["code"])
        user_thirds = get_best_third_places(user_tables)
        for third in user_thirds:
            user_qualified.add(third["code"])

        correct = user_qualified & real_qualified
        class_pts = len(correct) * 2
        prev_class = user.get("classification_pts", 0)
        current_total = user.get("total_score", 0)
        new_total = current_total - prev_class + class_pts

        results.append({
            "name": user.get("display_name", ""),
            "correct_teams": len(correct),
            "classification_points": class_pts,
            "total_antes": current_total,
            "total_despues": new_total,
        })

    return {
        "real_qualified_count": len(real_qualified),
        "users": sorted(results, key=lambda x: -x["total_despues"]),
    }

@router.post("/admin/set-match-teams")
async def set_match_teams(body: SetTeamsBody, current_user: dict = Depends(require_admin)):
    """Asigna equipos reales (y opcionalmente kickoff) a un partido."""
    group_docs = db.collection("matches")\
        .where(filter=FieldFilter("phase", "==", "group"))\
        .stream()

    teams_by_code = {}
    for doc in group_docs:
        m = doc.to_dict()
        for side in ["home_team", "away_team"]:
            t = m[side]
            if t.get("code"):
                teams_by_code[t["code"].upper()] = {
                    "id": t.get("id", 999),
                    "name": t["name"],
                    "code": t["code"],
                    "logo": t.get("logo", ""),
                }

    home = teams_by_code.get(body.home_code.upper())
    away = teams_by_code.get(body.away_code.upper())

    if not home or not away:
        return {
            "error": "Código no encontrado",
            "home_found": home is not None,
            "away_found": away is not None,
            "available_codes": sorted(teams_by_code.keys()),
        }

    doc_ref = db.collection("matches").document(str(body.fixture_id))
    if not doc_ref.get().exists:
        return {"error": f"Partido {body.fixture_id} no existe"}

    update_data = {"home_team": home, "away_team": away}
    if body.kickoff:
        update_data["kickoff"] = body.kickoff

    doc_ref.update(update_data)

    from app.core import cache
    cache.invalidate("all_matches", "matches_dict", "ranking")

    return {
        "fixture_id": body.fixture_id,
        "set": f"{home['name']} vs {away['name']}",
        "kickoff": body.kickoff or "(sin cambio)",
    }

@router.get("/admin/debug-user-pred")
async def debug_user_pred(uid: str, current_user: dict = Depends(require_admin)):
    """Muestra las predicciones de eliminatoria de un usuario."""
    pred_docs = db.collection("predictions")\
        .where(filter=FieldFilter("uid", "==", uid))\
        .stream()

    knockout_preds = []
    for doc in pred_docs:
        p = doc.to_dict()
        fixture_id = p.get("fixture_id", 0)
        # Solo eliminatorias (fixture_id >= 10101)
        if fixture_id >= 10101:
            match_doc = db.collection("matches").document(str(fixture_id)).get()
            match = match_doc.to_dict() if match_doc.exists else {}
            knockout_preds.append({
                "doc_id": doc.id,
                "fixture_id": fixture_id,
                "prediction_data": p,
                "match_teams": {
                    "home": match.get("home_team", {}).get("name"),
                    "away": match.get("away_team", {}).get("name"),
                } if match else None,
            })

    knockout_preds.sort(key=lambda x: x["fixture_id"])
    return {
        "uid": uid,
        "total_knockout_predictions": len(knockout_preds),
        "predictions": knockout_preds,
    }

@router.get("/admin/preview-corrected-bracket")
async def preview_corrected_bracket(uid: str, current_user: dict = Depends(require_admin)):
    """Muestra cómo quedaría el bracket de un usuario con los cruces oficiales de FIFA. NO guarda."""
    from app.services.bracket_service import (
        calculate_group_table, get_best_third_places, _tbd_team,
        _get_winner_from_prediction, _get_loser_from_prediction
    )

    # Cruces oficiales FIFA 2026 (terceros de grupos B,D,E,F,I,J,K,L)
    R32 = [
        (10101, "2A", "2B"),
        (10102, "1C", "2F"),
        (10103, "1E", "3D"),
        (10104, "1F", "2C"),
        (10105, "2E", "2I"),
        (10106, "1I", "3F"),
        (10107, "1A", "3E"),
        (10108, "1L", "3K"),
        (10109, "1G", "3I"),
        (10110, "1D", "3B"),
        (10111, "1H", "2J"),
        (10112, "2K", "2L"),
        (10113, "1B", "3J"),
        (10114, "2D", "2G"),
        (10115, "1J", "2H"),
        (10116, "1K", "3L"),
    ]
    R16 = [
        (10201, "W10101", "W10104"),
        (10202, "W10103", "W10106"),
        (10203, "W10102", "W10105"),
        (10204, "W10107", "W10108"),
        (10205, "W10112", "W10111"),
        (10206, "W10110", "W10109"),
        (10207, "W10115", "W10114"),
        (10208, "W10113", "W10116"),
    ]
    QF = [
        (10301, "W10201", "W10202"),
        (10302, "W10203", "W10204"),
        (10303, "W10205", "W10206"),
        (10304, "W10207", "W10208"),
    ]
    SF = [
        (10401, "W10301", "W10302"),
        (10402, "W10303", "W10304"),
    ]

    # Cargar grupos y predicciones del usuario
    group_docs = db.collection("matches")\
        .where(filter=FieldFilter("phase", "==", "group")).stream()
    group_matches = [doc.to_dict() for doc in group_docs]

    pred_docs = db.collection("predictions")\
        .where(filter=FieldFilter("uid", "==", uid)).stream()
    predictions = {p.to_dict()["fixture_id"]: p.to_dict() for p in pred_docs}

    groups = {}
    for match in group_matches:
        g = match.get("group", "")
        groups.setdefault(g, []).append(match)

    group_tables = {g: calculate_group_table(m, predictions) for g, m in groups.items()}

    # Clasificados: 1X, 2X por grupo
    classified = {}
    for group, table in group_tables.items():
        letter = group.replace("Group ", "")
        if len(table) >= 1: classified[f"1{letter}"] = table[0]
        if len(table) >= 2: classified[f"2{letter}"] = table[1]

    # Terceros por grupo (para slots 3X)
    for group, table in group_tables.items():
        letter = group.replace("Group ", "")
        if len(table) >= 3:
            classified[f"3{letter}"] = table[2]

    # Construir bracket con cruces oficiales
    bracket = {}
    for fixture_id, home_slot, away_slot in R32:
        bracket[fixture_id] = {
            "home_team": classified.get(home_slot, _tbd_team(home_slot)),
            "away_team": classified.get(away_slot, _tbd_team(away_slot)),
        }

    def project_round(round_bracket):
        for fixture_id, home_slot, away_slot in round_bracket:
            hp = int(home_slot.replace("W", ""))
            ap = int(away_slot.replace("W", ""))
            bracket[fixture_id] = {
                "home_team": _get_winner_from_prediction(hp, bracket, predictions),
                "away_team": _get_winner_from_prediction(ap, bracket, predictions),
            }

    project_round(R16)
    project_round(QF)
    project_round(SF)

    bracket[10501] = {
        "home_team": _get_loser_from_prediction(10401, bracket, predictions),
        "away_team": _get_loser_from_prediction(10402, bracket, predictions),
    }
    bracket[10601] = {
        "home_team": _get_winner_from_prediction(10401, bracket, predictions),
        "away_team": _get_winner_from_prediction(10402, bracket, predictions),
    }

    # Armar salida legible con marcadores predichos
    output = []
    for fid in sorted(bracket.keys()):
        pred = predictions.get(fid, {})
        output.append({
            "fixture_id": fid,
            "home": bracket[fid]["home_team"]["name"],
            "away": bracket[fid]["away_team"]["name"],
            "predicted": f"{pred.get('predicted_home', '-')}-{pred.get('predicted_away', '-')}",
            "penalty_winner": pred.get("penalty_winner"),
        })

    return {"uid": uid, "bracket": output}

@router.get("/admin/preview-user-groups")
async def preview_user_groups(uid: str, current_user: dict = Depends(require_admin)):
    """Muestra las tablas de grupos proyectadas según las predicciones del usuario."""
    from app.services.bracket_service import calculate_group_table, get_best_third_places

    group_docs = db.collection("matches")\
        .where(filter=FieldFilter("phase", "==", "group")).stream()
    group_matches = [doc.to_dict() for doc in group_docs]

    pred_docs = db.collection("predictions")\
        .where(filter=FieldFilter("uid", "==", uid)).stream()
    predictions = {p.to_dict()["fixture_id"]: p.to_dict() for p in pred_docs}

    groups = {}
    for match in group_matches:
        g = match.get("group", "")
        groups.setdefault(g, []).append(match)

    group_tables = {g: calculate_group_table(m, predictions) for g, m in groups.items()}

    output = {}
    for group in sorted(group_tables.keys()):
        output[group] = [
            {"pos": i+1, "team": t["name"], "pts": t["pts"], "dg": t["dg"], "gf": t["gf"]}
            for i, t in enumerate(group_tables[group])
        ]

    thirds = get_best_third_places(group_tables)
    best_thirds = [{"team": t["name"], "group": t.get("group","?"), "pts": t["pts"]} for t in thirds]

    return {"uid": uid, "tables": output, "best_thirds": best_thirds}

@router.get("/admin/preview-r16-classification")
async def preview_r16_classification(current_user: dict = Depends(require_admin)):
    """Preview: 4 pts por cada equipo que el usuario proyectó llegaba a octavos. NO guarda."""
    from app.services.bracket_service import (
        calculate_group_table, _get_winner_from_prediction, _tbd_team
    )

    # 16 equipos REALES que llegaron a octavos (por código)
    REAL_R16_CODES = {
        "CAN", "MAR", "PAR", "FRA", "BRA", "NOR", "MEX", "ENG",
        "ESP", "POR", "USA", "BEL", "EGY", "ARG", "SUI", "COL"
    }

    # Cruces oficiales de R32 (para proyectar el bracket del usuario)
    R32 = [
        (10101, "2A", "2B"), (10102, "1C", "2F"), (10103, "1E", "3D"),
        (10104, "1F", "2C"), (10105, "2E", "2I"), (10106, "1I", "3F"),
        (10107, "1A", "3E"), (10108, "1L", "3K"), (10109, "1G", "3I"),
        (10110, "1D", "3B"), (10111, "1H", "2J"), (10112, "2K", "2L"),
        (10113, "1B", "3J"), (10114, "2D", "2G"), (10115, "1J", "2H"),
        (10116, "1K", "3L"),
    ]

    group_docs = db.collection("matches")\
        .where(filter=FieldFilter("phase", "==", "group")).stream()
    group_matches = [doc.to_dict() for doc in group_docs]

    groups = {}
    for match in group_matches:
        g = match.get("group", "")
        groups.setdefault(g, []).append(match)

    users = list(db.collection("users")
        .where(filter=FieldFilter("role", "==", "player")).stream())

    results = []
    for user_doc in users:
        user = user_doc.to_dict()
        uid = user["uid"]

        pred_docs = db.collection("predictions")\
            .where(filter=FieldFilter("uid", "==", uid)).stream()
        predictions = {p.to_dict()["fixture_id"]: p.to_dict() for p in pred_docs}

        # Tablas del usuario
        group_tables = {g: calculate_group_table(m, predictions) for g, m in groups.items()}
        classified = {}
        for group, table in group_tables.items():
            letter = group.replace("Group ", "")
            if len(table) >= 1: classified[f"1{letter}"] = table[0]
            if len(table) >= 2: classified[f"2{letter}"] = table[1]
            if len(table) >= 3: classified[f"3{letter}"] = table[2]

        # Proyectar bracket R32 y sacar ganadores (los que él cree que van a octavos)
        bracket = {}
        for fid, hs, as_ in R32:
            bracket[fid] = {
                "home_team": classified.get(hs, _tbd_team(hs)),
                "away_team": classified.get(as_, _tbd_team(as_)),
            }

        # Equipos que el usuario proyecta que ganan R32 (llegan a octavos)
        user_r16_codes = set()
        for fid, hs, as_ in R32:
            winner = _get_winner_from_prediction(fid, bracket, predictions)
            if winner and winner.get("code"):
                user_r16_codes.add(winner["code"])

        correct = user_r16_codes & REAL_R16_CODES
        pts = len(correct) * 4

        results.append({
            "name": user.get("display_name", ""),
            "correct_teams": len(correct),
            "r16_points": pts,
            "total_actual": user.get("total_score", 0),
            "total_nuevo": user.get("total_score", 0) - user.get("r16_class_pts", 0) + pts,
        })

    return {
        "real_r16_count": len(REAL_R16_CODES),
        "users": sorted(results, key=lambda x: -x["total_nuevo"]),
    }

@router.post("/admin/calculate-r16-classification")
async def calculate_r16_classification(current_user: dict = Depends(require_admin)):
    """Da 4 pts por cada equipo que el usuario proyectó llegaba a octavos."""
    from app.services.bracket_service import (
        calculate_group_table, _get_winner_from_prediction, _tbd_team
    )

    REAL_R16_CODES = {
        "CAN", "MAR", "PAR", "FRA", "BRA", "NOR", "MEX", "ENG",
        "ESP", "POR", "USA", "BEL", "EGY", "ARG", "SUI", "COL"
    }

    R32 = [
        (10101, "2A", "2B"), (10102, "1C", "2F"), (10103, "1E", "3D"),
        (10104, "1F", "2C"), (10105, "2E", "2I"), (10106, "1I", "3F"),
        (10107, "1A", "3E"), (10108, "1L", "3K"), (10109, "1G", "3I"),
        (10110, "1D", "3B"), (10111, "1H", "2J"), (10112, "2K", "2L"),
        (10113, "1B", "3J"), (10114, "2D", "2G"), (10115, "1J", "2H"),
        (10116, "1K", "3L"),
    ]

    group_docs = db.collection("matches")\
        .where(filter=FieldFilter("phase", "==", "group")).stream()
    group_matches = [doc.to_dict() for doc in group_docs]

    groups = {}
    for match in group_matches:
        g = match.get("group", "")
        groups.setdefault(g, []).append(match)

    users = list(db.collection("users")
        .where(filter=FieldFilter("role", "==", "player")).stream())

    results = []
    for user_doc in users:
        user = user_doc.to_dict()
        uid = user["uid"]

        pred_docs = db.collection("predictions")\
            .where(filter=FieldFilter("uid", "==", uid)).stream()
        predictions = {p.to_dict()["fixture_id"]: p.to_dict() for p in pred_docs}

        group_tables = {g: calculate_group_table(m, predictions) for g, m in groups.items()}
        classified = {}
        for group, table in group_tables.items():
            letter = group.replace("Group ", "")
            if len(table) >= 1: classified[f"1{letter}"] = table[0]
            if len(table) >= 2: classified[f"2{letter}"] = table[1]
            if len(table) >= 3: classified[f"3{letter}"] = table[2]

        bracket = {}
        for fid, hs, as_ in R32:
            bracket[fid] = {
                "home_team": classified.get(hs, _tbd_team(hs)),
                "away_team": classified.get(as_, _tbd_team(as_)),
            }

        user_r16_codes = set()
        for fid, hs, as_ in R32:
            winner = _get_winner_from_prediction(fid, bracket, predictions)
            if winner and winner.get("code"):
                user_r16_codes.add(winner["code"])

        correct = user_r16_codes & REAL_R16_CODES
        pts = len(correct) * 4

        prev = user.get("r16_class_pts", 0)
        new_total = user.get("total_score", 0) - prev + pts

        user_doc.reference.update({
            "r16_class_pts": pts,
            "total_score": new_total,
        })

        results.append({
            "name": user.get("display_name", ""),
            "correct_teams": len(correct),
            "points": pts,
        })

    cache.invalidate("ranking")

    return {
        "users_processed": len(results),
        "results": sorted(results, key=lambda x: -x["points"]),
    }

@router.get("/admin/preview-qf-classification")
async def preview_qf_classification(current_user: dict = Depends(require_admin)):
    """Preview de puntos de cuartos. NO guarda."""
    from app.services.bracket_service import (
        calculate_group_table, _get_winner_from_prediction, _tbd_team
    )
    REAL_QF_CODES = {"MAR", "FRA", "ENG", "NOR", "ESP", "BEL", "ARG", "SUI"}
    R32 = [
        (10101, "2A", "2B"), (10102, "1C", "2F"), (10103, "1E", "3D"),
        (10104, "1F", "2C"), (10105, "2E", "2I"), (10106, "1I", "3F"),
        (10107, "1A", "3E"), (10108, "1L", "3K"), (10109, "1G", "3I"),
        (10110, "1D", "3B"), (10111, "1H", "2J"), (10112, "2K", "2L"),
        (10113, "1B", "3J"), (10114, "2D", "2G"), (10115, "1J", "2H"),
        (10116, "1K", "3L"),
    ]
    R16 = [
        (10201, "W10101", "W10104"), (10202, "W10103", "W10106"),
        (10203, "W10102", "W10105"), (10204, "W10107", "W10108"),
        (10205, "W10112", "W10111"), (10206, "W10110", "W10109"),
        (10207, "W10115", "W10114"), (10208, "W10113", "W10116"),
    ]
    group_docs = db.collection("matches")\
        .where(filter=FieldFilter("phase", "==", "group")).stream()
    group_matches = [doc.to_dict() for doc in group_docs]
    groups = {}
    for match in group_matches:
        g = match.get("group", "")
        groups.setdefault(g, []).append(match)
    users = list(db.collection("users")
        .where(filter=FieldFilter("role", "==", "player")).stream())
    results = []
    for user_doc in users:
        user = user_doc.to_dict()
        uid = user["uid"]
        pred_docs = db.collection("predictions")\
            .where(filter=FieldFilter("uid", "==", uid)).stream()
        predictions = {p.to_dict()["fixture_id"]: p.to_dict() for p in pred_docs}
        group_tables = {g: calculate_group_table(m, predictions) for g, m in groups.items()}
        classified = {}
        for group, table in group_tables.items():
            letter = group.replace("Group ", "")
            if len(table) >= 1: classified[f"1{letter}"] = table[0]
            if len(table) >= 2: classified[f"2{letter}"] = table[1]
            if len(table) >= 3: classified[f"3{letter}"] = table[2]
        bracket = {}
        for fid, hs, as_ in R32:
            bracket[fid] = {
                "home_team": classified.get(hs, _tbd_team(hs)),
                "away_team": classified.get(as_, _tbd_team(as_)),
            }
        for fid, hs, as_ in R16:
            hp = int(hs.replace("W", ""))
            ap = int(as_.replace("W", ""))
            bracket[fid] = {
                "home_team": _get_winner_from_prediction(hp, bracket, predictions),
                "away_team": _get_winner_from_prediction(ap, bracket, predictions),
            }
        user_qf_codes = set()
        for fid, hs, as_ in R16:
            winner = _get_winner_from_prediction(fid, bracket, predictions)
            if winner and winner.get("code"):
                user_qf_codes.add(winner["code"])
        correct = user_qf_codes & REAL_QF_CODES
        pts = len(correct) * 6
        prev = user.get("qf_class_pts", 0)
        results.append({
            "name": user.get("display_name", ""),
            "correct_teams": len(correct),
            "qf_points": pts,
            "total_actual": user.get("total_score", 0),
            "total_nuevo": user.get("total_score", 0) - prev + pts,
        })
    return {"users": sorted(results, key=lambda x: -x["total_nuevo"])}

@router.post("/admin/calculate-qf-classification")
async def calculate_qf_classification(current_user: dict = Depends(require_admin)):
    """Da 6 pts por cada equipo que el usuario proyectó llegaba a cuartos."""
    from app.services.bracket_service import (
        calculate_group_table, _get_winner_from_prediction, _tbd_team
    )

    REAL_QF_CODES = {"MAR", "FRA", "ENG", "NOR", "ESP", "BEL", "ARG", "SUI"}

    R32 = [
        (10101, "2A", "2B"), (10102, "1C", "2F"), (10103, "1E", "3D"),
        (10104, "1F", "2C"), (10105, "2E", "2I"), (10106, "1I", "3F"),
        (10107, "1A", "3E"), (10108, "1L", "3K"), (10109, "1G", "3I"),
        (10110, "1D", "3B"), (10111, "1H", "2J"), (10112, "2K", "2L"),
        (10113, "1B", "3J"), (10114, "2D", "2G"), (10115, "1J", "2H"),
        (10116, "1K", "3L"),
    ]
    R16 = [
        (10201, "W10101", "W10104"), (10202, "W10103", "W10106"),
        (10203, "W10102", "W10105"), (10204, "W10107", "W10108"),
        (10205, "W10112", "W10111"), (10206, "W10110", "W10109"),
        (10207, "W10115", "W10114"), (10208, "W10113", "W10116"),
    ]

    group_docs = db.collection("matches")\
        .where(filter=FieldFilter("phase", "==", "group")).stream()
    group_matches = [doc.to_dict() for doc in group_docs]

    groups = {}
    for match in group_matches:
        g = match.get("group", "")
        groups.setdefault(g, []).append(match)

    users = list(db.collection("users")
        .where(filter=FieldFilter("role", "==", "player")).stream())

    results = []
    for user_doc in users:
        user = user_doc.to_dict()
        uid = user["uid"]

        pred_docs = db.collection("predictions")\
            .where(filter=FieldFilter("uid", "==", uid)).stream()
        predictions = {p.to_dict()["fixture_id"]: p.to_dict() for p in pred_docs}

        group_tables = {g: calculate_group_table(m, predictions) for g, m in groups.items()}
        classified = {}
        for group, table in group_tables.items():
            letter = group.replace("Group ", "")
            if len(table) >= 1: classified[f"1{letter}"] = table[0]
            if len(table) >= 2: classified[f"2{letter}"] = table[1]
            if len(table) >= 3: classified[f"3{letter}"] = table[2]

        bracket = {}
        for fid, hs, as_ in R32:
            bracket[fid] = {
                "home_team": classified.get(hs, _tbd_team(hs)),
                "away_team": classified.get(as_, _tbd_team(as_)),
            }
        # Proyectar R16 para saber quién llega a cuartos
        for fid, hs, as_ in R16:
            hp = int(hs.replace("W", ""))
            ap = int(as_.replace("W", ""))
            bracket[fid] = {
                "home_team": _get_winner_from_prediction(hp, bracket, predictions),
                "away_team": _get_winner_from_prediction(ap, bracket, predictions),
            }

        # Ganadores de R16 = equipos que el usuario proyecta en cuartos
        user_qf_codes = set()
        for fid, hs, as_ in R16:
            winner = _get_winner_from_prediction(fid, bracket, predictions)
            if winner and winner.get("code"):
                user_qf_codes.add(winner["code"])

        correct = user_qf_codes & REAL_QF_CODES
        pts = len(correct) * 6

        prev = user.get("qf_class_pts", 0)
        new_total = user.get("total_score", 0) - prev + pts
        user_doc.reference.update({
            "qf_class_pts": pts,
            "total_score": new_total,
        })

        results.append({
            "name": user.get("display_name", ""),
            "correct_teams": len(correct),
            "points": pts,
        })

    cache.invalidate("ranking")
    return {"users_processed": len(results), "results": sorted(results, key=lambda x: -x["points"])}

@router.post("/admin/calculate-sf-classification")
async def calculate_sf_classification(current_user: dict = Depends(require_admin)):
    """Da 8 pts por cada equipo que el usuario proyectó llegaba a semis."""
    from app.services.bracket_service import (
        calculate_group_table, _get_winner_from_prediction, _tbd_team
    )

    REAL_SF_CODES = {"FRA", "ESP", "ENG", "ARG"}

    R32 = [
        (10101, "2A", "2B"), (10102, "1C", "2F"), (10103, "1E", "3D"),
        (10104, "1F", "2C"), (10105, "2E", "2I"), (10106, "1I", "3F"),
        (10107, "1A", "3E"), (10108, "1L", "3K"), (10109, "1G", "3I"),
        (10110, "1D", "3B"), (10111, "1H", "2J"), (10112, "2K", "2L"),
        (10113, "1B", "3J"), (10114, "2D", "2G"), (10115, "1J", "2H"),
        (10116, "1K", "3L"),
    ]
    R16 = [
        (10201, "W10101", "W10104"), (10202, "W10103", "W10106"),
        (10203, "W10102", "W10105"), (10204, "W10107", "W10108"),
        (10205, "W10112", "W10111"), (10206, "W10110", "W10109"),
        (10207, "W10115", "W10114"), (10208, "W10113", "W10116"),
    ]
    QF = [
        (10301, "W10201", "W10202"), (10302, "W10203", "W10204"),
        (10303, "W10205", "W10206"), (10304, "W10207", "W10208"),
    ]

    group_docs = db.collection("matches")\
        .where(filter=FieldFilter("phase", "==", "group")).stream()
    group_matches = [doc.to_dict() for doc in group_docs]
    groups = {}
    for match in group_matches:
        g = match.get("group", "")
        groups.setdefault(g, []).append(match)

    users = list(db.collection("users")
        .where(filter=FieldFilter("role", "==", "player")).stream())

    results = []
    for user_doc in users:
        user = user_doc.to_dict()
        uid = user["uid"]
        pred_docs = db.collection("predictions")\
            .where(filter=FieldFilter("uid", "==", uid)).stream()
        predictions = {p.to_dict()["fixture_id"]: p.to_dict() for p in pred_docs}

        group_tables = {g: calculate_group_table(m, predictions) for g, m in groups.items()}
        classified = {}
        for group, table in group_tables.items():
            letter = group.replace("Group ", "")
            if len(table) >= 1: classified[f"1{letter}"] = table[0]
            if len(table) >= 2: classified[f"2{letter}"] = table[1]
            if len(table) >= 3: classified[f"3{letter}"] = table[2]

        bracket = {}
        for fid, hs, as_ in R32:
            bracket[fid] = {
                "home_team": classified.get(hs, _tbd_team(hs)),
                "away_team": classified.get(as_, _tbd_team(as_)),
            }
        for fid, hs, as_ in R16:
            hp, ap = int(hs.replace("W","")), int(as_.replace("W",""))
            bracket[fid] = {
                "home_team": _get_winner_from_prediction(hp, bracket, predictions),
                "away_team": _get_winner_from_prediction(ap, bracket, predictions),
            }
        for fid, hs, as_ in QF:
            hp, ap = int(hs.replace("W","")), int(as_.replace("W",""))
            bracket[fid] = {
                "home_team": _get_winner_from_prediction(hp, bracket, predictions),
                "away_team": _get_winner_from_prediction(ap, bracket, predictions),
            }

        user_sf_codes = set()
        for fid, hs, as_ in QF:
            winner = _get_winner_from_prediction(fid, bracket, predictions)
            if winner and winner.get("code"):
                user_sf_codes.add(winner["code"])

        correct = user_sf_codes & REAL_SF_CODES
        pts = len(correct) * 8
        prev = user.get("sf_class_pts", 0)
        new_total = user.get("total_score", 0) - prev + pts
        user_doc.reference.update({"sf_class_pts": pts, "total_score": new_total})

        results.append({"name": user.get("display_name",""), "correct_teams": len(correct), "points": pts})

    cache.invalidate("ranking")
    return {"users_processed": len(results), "results": sorted(results, key=lambda x: -x["points"])}

@router.post("/admin/calculate-final-classification")
async def calculate_final_classification(current_user: dict = Depends(require_admin)):
    """Da 10 pts por cada equipo que el usuario proyectó llegaba a la final."""
    from app.services.bracket_service import (
        calculate_group_table, _get_winner_from_prediction, _tbd_team
    )

    REAL_FINAL_CODES = {"ESP", "ARG"}

    R32 = [
        (10101, "2A", "2B"), (10102, "1C", "2F"), (10103, "1E", "3D"),
        (10104, "1F", "2C"), (10105, "2E", "2I"), (10106, "1I", "3F"),
        (10107, "1A", "3E"), (10108, "1L", "3K"), (10109, "1G", "3I"),
        (10110, "1D", "3B"), (10111, "1H", "2J"), (10112, "2K", "2L"),
        (10113, "1B", "3J"), (10114, "2D", "2G"), (10115, "1J", "2H"),
        (10116, "1K", "3L"),
    ]
    R16 = [
        (10201, "W10101", "W10104"), (10202, "W10103", "W10106"),
        (10203, "W10102", "W10105"), (10204, "W10107", "W10108"),
        (10205, "W10112", "W10111"), (10206, "W10110", "W10109"),
        (10207, "W10115", "W10114"), (10208, "W10113", "W10116"),
    ]
    QF = [
        (10301, "W10201", "W10202"), (10302, "W10203", "W10204"),
        (10303, "W10205", "W10206"), (10304, "W10207", "W10208"),
    ]
    SF = [
        (10401, "W10301", "W10302"), (10402, "W10303", "W10304"),
    ]

    group_docs = db.collection("matches")\
        .where(filter=FieldFilter("phase", "==", "group")).stream()
    group_matches = [doc.to_dict() for doc in group_docs]
    groups = {}
    for match in group_matches:
        g = match.get("group", "")
        groups.setdefault(g, []).append(match)

    users = list(db.collection("users")
        .where(filter=FieldFilter("role", "==", "player")).stream())

    results = []
    for user_doc in users:
        user = user_doc.to_dict()
        uid = user["uid"]
        pred_docs = db.collection("predictions")\
            .where(filter=FieldFilter("uid", "==", uid)).stream()
        predictions = {p.to_dict()["fixture_id"]: p.to_dict() for p in pred_docs}

        group_tables = {g: calculate_group_table(m, predictions) for g, m in groups.items()}
        classified = {}
        for group, table in group_tables.items():
            letter = group.replace("Group ", "")
            if len(table) >= 1: classified[f"1{letter}"] = table[0]
            if len(table) >= 2: classified[f"2{letter}"] = table[1]
            if len(table) >= 3: classified[f"3{letter}"] = table[2]

        bracket = {}
        for fid, hs, as_ in R32:
            bracket[fid] = {
                "home_team": classified.get(hs, _tbd_team(hs)),
                "away_team": classified.get(as_, _tbd_team(as_)),
            }
        for fid, hs, as_ in R16:
            hp, ap = int(hs.replace("W","")), int(as_.replace("W",""))
            bracket[fid] = {
                "home_team": _get_winner_from_prediction(hp, bracket, predictions),
                "away_team": _get_winner_from_prediction(ap, bracket, predictions),
            }
        for fid, hs, as_ in QF:
            hp, ap = int(hs.replace("W","")), int(as_.replace("W",""))
            bracket[fid] = {
                "home_team": _get_winner_from_prediction(hp, bracket, predictions),
                "away_team": _get_winner_from_prediction(ap, bracket, predictions),
            }
        for fid, hs, as_ in SF:
            hp, ap = int(hs.replace("W","")), int(as_.replace("W",""))
            bracket[fid] = {
                "home_team": _get_winner_from_prediction(hp, bracket, predictions),
                "away_team": _get_winner_from_prediction(ap, bracket, predictions),
            }

        user_final_codes = set()
        for fid, hs, as_ in SF:
            winner = _get_winner_from_prediction(fid, bracket, predictions)
            if winner and winner.get("code"):
                user_final_codes.add(winner["code"])

        correct = user_final_codes & REAL_FINAL_CODES
        pts = len(correct) * 10
        prev = user.get("final_class_pts", 0)
        new_total = user.get("total_score", 0) - prev + pts
        user_doc.reference.update({"final_class_pts": pts, "total_score": new_total})

        results.append({"name": user.get("display_name",""), "correct_teams": len(correct), "points": pts})

    cache.invalidate("ranking")
    return {"users_processed": len(results), "results": sorted(results, key=lambda x: -x["points"])}

@router.post("/admin/calculate-final-positions")
async def calculate_final_positions(current_user: dict = Depends(require_admin)):
    """Da puntos por Campeón(12), Subcampeón(10), 3er puesto(8), 4to puesto(6).
    Se compara el equipo predicho por el usuario contra el resultado real,
    SIN importar si acertó también el rival."""
    from app.services.bracket_service import calculate_group_table, _get_winner_from_prediction, _tbd_team

    REAL = {
        "champion": "ESP",
        "runner_up": "ARG",
        "third": "ENG",
        "fourth": "FRA",
    }

    R32 = [
        (10101, "2A", "2B"), (10102, "1C", "2F"), (10103, "1E", "3D"),
        (10104, "1F", "2C"), (10105, "2E", "2I"), (10106, "1I", "3F"),
        (10107, "1A", "3E"), (10108, "1L", "3K"), (10109, "1G", "3I"),
        (10110, "1D", "3B"), (10111, "1H", "2J"), (10112, "2K", "2L"),
        (10113, "1B", "3J"), (10114, "2D", "2G"), (10115, "1J", "2H"),
        (10116, "1K", "3L"),
    ]
    R16 = [
        (10201, "W10101", "W10104"), (10202, "W10103", "W10106"),
        (10203, "W10102", "W10105"), (10204, "W10107", "W10108"),
        (10205, "W10112", "W10111"), (10206, "W10110", "W10109"),
        (10207, "W10115", "W10114"), (10208, "W10113", "W10116"),
    ]
    QF = [
        (10301, "W10201", "W10202"), (10302, "W10203", "W10204"),
        (10303, "W10205", "W10206"), (10304, "W10207", "W10208"),
    ]
    SF = [
        (10401, "W10301", "W10302"), (10402, "W10303", "W10304"),
    ]

    group_docs = db.collection("matches")\
        .where(filter=FieldFilter("phase", "==", "group")).stream()
    group_matches = [doc.to_dict() for doc in group_docs]
    groups = {}
    for match in group_matches:
        g = match.get("group", "")
        groups.setdefault(g, []).append(match)

    users = list(db.collection("users")
        .where(filter=FieldFilter("role", "==", "player")).stream())

    results = []
    for user_doc in users:
        user = user_doc.to_dict()
        uid = user["uid"]
        pred_docs = db.collection("predictions")\
            .where(filter=FieldFilter("uid", "==", uid)).stream()
        predictions = {p.to_dict()["fixture_id"]: p.to_dict() for p in pred_docs}

        group_tables = {g: calculate_group_table(m, predictions) for g, m in groups.items()}
        classified = {}
        for group, table in group_tables.items():
            letter = group.replace("Group ", "")
            if len(table) >= 1: classified[f"1{letter}"] = table[0]
            if len(table) >= 2: classified[f"2{letter}"] = table[1]
            if len(table) >= 3: classified[f"3{letter}"] = table[2]

        bracket = {}
        for fid, hs, as_ in R32:
            bracket[fid] = {
                "home_team": classified.get(hs, _tbd_team(hs)),
                "away_team": classified.get(as_, _tbd_team(as_)),
            }
        for round_list in [R16, QF, SF]:
            for fid, hs, as_ in round_list:
                hp, ap = int(hs.replace("W","")), int(as_.replace("W",""))
                bracket[fid] = {
                    "home_team": _get_winner_from_prediction(hp, bracket, predictions),
                    "away_team": _get_winner_from_prediction(ap, bracket, predictions),
                }
        # Construir la Final (10601) y Tercer puesto (10501) con los ganadores/perdedores de semis
        bracket[10601] = {
            "home_team": _get_winner_from_prediction(10401, bracket, predictions),
            "away_team": _get_winner_from_prediction(10402, bracket, predictions),
        }
        from app.services.bracket_service import _get_loser_from_prediction
        bracket[10501] = {
            "home_team": _get_loser_from_prediction(10401, bracket, predictions),
            "away_team": _get_loser_from_prediction(10402, bracket, predictions),
        }

        pts = 0
        detail = []

        # ── Final: Campeón y Subcampeón (según el marcador que predijo en 10601) ──
        final_pred = predictions.get(10601)
        final_match = bracket.get(10601, {})
        if final_pred and final_match:
            hg, ag = final_pred.get("predicted_home", 0), final_pred.get("predicted_away", 0)
            home_code = final_match.get("home_team", {}).get("code")
            away_code = final_match.get("away_team", {}).get("code")

            if hg > ag:
                pred_champion, pred_runner = home_code, away_code
            elif hg < ag:
                pred_champion, pred_runner = away_code, home_code
            else:
                pw = final_pred.get("penalty_winner", "home")
                pred_champion = home_code if pw == "home" else away_code
                pred_runner = away_code if pw == "home" else home_code

            if pred_champion == REAL["champion"]:
                pts += 12
                detail.append("champion")
            if pred_runner == REAL["runner_up"]:
                pts += 10
                detail.append("runner_up")

        # ── Tercer puesto: 3° y 4° (según el marcador que predijo en 10501) ──
        third_pred = predictions.get(10501)
        third_match = bracket.get(10501, {})
        if third_pred and third_match:
            hg, ag = third_pred.get("predicted_home", 0), third_pred.get("predicted_away", 0)
            home_code = third_match.get("home_team", {}).get("code")
            away_code = third_match.get("away_team", {}).get("code")

            if hg > ag:
                pred_third, pred_fourth = home_code, away_code
            elif hg < ag:
                pred_third, pred_fourth = away_code, home_code
            else:
                pw = third_pred.get("penalty_winner", "home")
                pred_third = home_code if pw == "home" else away_code
                pred_fourth = away_code if pw == "home" else home_code

            if pred_third == REAL["third"]:
                pts += 8
                detail.append("third")
            if pred_fourth == REAL["fourth"]:
                pts += 6
                detail.append("fourth")

        prev = user.get("final_pos_pts", 0)
        new_total = user.get("total_score", 0) - prev + pts
        user_doc.reference.update({"final_pos_pts": pts, "total_score": new_total})

        results.append({"name": user.get("display_name",""), "points": pts, "detail": detail})

    cache.invalidate("ranking")
    return {"users_processed": len(results), "results": sorted(results, key=lambda x: -x["points"])}

@router.get("/admin/debug-projected-finalists")
async def debug_projected_finalists(current_user: dict = Depends(require_admin)):
    from app.services.bracket_service import calculate_group_table, _get_winner_from_prediction, _tbd_team

    R32 = [
        (10101, "2A", "2B"), (10102, "1C", "2F"), (10103, "1E", "3D"),
        (10104, "1F", "2C"), (10105, "2E", "2I"), (10106, "1I", "3F"),
        (10107, "1A", "3E"), (10108, "1L", "3K"), (10109, "1G", "3I"),
        (10110, "1D", "3B"), (10111, "1H", "2J"), (10112, "2K", "2L"),
        (10113, "1B", "3J"), (10114, "2D", "2G"), (10115, "1J", "2H"),
        (10116, "1K", "3L"),
    ]
    R16 = [(10201,"W10101","W10104"),(10202,"W10103","W10106"),(10203,"W10102","W10105"),
           (10204,"W10107","W10108"),(10205,"W10112","W10111"),(10206,"W10110","W10109"),
           (10207,"W10115","W10114"),(10208,"W10113","W10116")]
    QF = [(10301,"W10201","W10202"),(10302,"W10203","W10204"),(10303,"W10205","W10206"),(10304,"W10207","W10208")]
    SF = [(10401,"W10301","W10302"),(10402,"W10303","W10304")]

    group_docs = db.collection("matches").where(filter=FieldFilter("phase","==","group")).stream()
    group_matches = [doc.to_dict() for doc in group_docs]
    groups = {}
    for m in group_matches:
        groups.setdefault(m.get("group",""), []).append(m)

    users = list(db.collection("users").where(filter=FieldFilter("role","==","player")).stream())
    out = []
    for user_doc in users:
        user = user_doc.to_dict()
        uid = user["uid"]
        preds = {p.to_dict()["fixture_id"]: p.to_dict() for p in db.collection("predictions").where(filter=FieldFilter("uid","==",uid)).stream()}
        gt = {g: calculate_group_table(m, preds) for g,m in groups.items()}
        classified = {}
        for g, table in gt.items():
            letter = g.replace("Group ","")
            if len(table)>=1: classified[f"1{letter}"]=table[0]
            if len(table)>=2: classified[f"2{letter}"]=table[1]
            if len(table)>=3: classified[f"3{letter}"]=table[2]
        bracket = {}
        for fid,hs,as_ in R32:
            bracket[fid] = {"home_team": classified.get(hs, _tbd_team(hs)), "away_team": classified.get(as_, _tbd_team(as_))}
        for rl in [R16,QF,SF]:
            for fid,hs,as_ in rl:
                hp,ap = int(hs.replace("W","")), int(as_.replace("W",""))
                bracket[fid] = {"home_team": _get_winner_from_prediction(hp,bracket,preds), "away_team": _get_winner_from_prediction(ap,bracket,preds)}
        
        bracket[10601] = {
            "home_team": _get_winner_from_prediction(10401, bracket, preds),
            "away_team": _get_winner_from_prediction(10402, bracket, preds),
        }
        
        finalists = [bracket[10601]["home_team"]["name"], bracket[10601]["away_team"]["name"]]
        out.append({"name": user.get("display_name",""), "finalists": finalists})
    return {"users": out}

@router.get("/admin/debug-final-calc")
async def debug_final_calc(current_user: dict = Depends(require_admin)):
    from app.services.bracket_service import calculate_group_table, _get_winner_from_prediction, _get_loser_from_prediction, _tbd_team

    R32 = [
        (10101, "2A", "2B"), (10102, "1C", "2F"), (10103, "1E", "3D"),
        (10104, "1F", "2C"), (10105, "2E", "2I"), (10106, "1I", "3F"),
        (10107, "1A", "3E"), (10108, "1L", "3K"), (10109, "1G", "3I"),
        (10110, "1D", "3B"), (10111, "1H", "2J"), (10112, "2K", "2L"),
        (10113, "1B", "3J"), (10114, "2D", "2G"), (10115, "1J", "2H"),
        (10116, "1K", "3L"),
    ]
    R16 = [(10201,"W10101","W10104"),(10202,"W10103","W10106"),(10203,"W10102","W10105"),
           (10204,"W10107","W10108"),(10205,"W10112","W10111"),(10206,"W10110","W10109"),
           (10207,"W10115","W10114"),(10208,"W10113","W10116")]
    QF = [(10301,"W10201","W10202"),(10302,"W10203","W10204"),(10303,"W10205","W10206"),(10304,"W10207","W10208")]
    SF = [(10401,"W10301","W10302"),(10402,"W10303","W10304")]

    group_docs = db.collection("matches").where(filter=FieldFilter("phase","==","group")).stream()
    group_matches = [doc.to_dict() for doc in group_docs]
    groups = {}
    for m in group_matches:
        groups.setdefault(m.get("group",""), []).append(m)

    users = list(db.collection("users").where(filter=FieldFilter("role","==","player")).stream())
    out = []
    for user_doc in users:
        user = user_doc.to_dict()
        uid = user["uid"]
        preds = {p.to_dict()["fixture_id"]: p.to_dict() for p in db.collection("predictions").where(filter=FieldFilter("uid","==",uid)).stream()}
        gt = {g: calculate_group_table(m, preds) for g,m in groups.items()}
        classified = {}
        for g, table in gt.items():
            letter = g.replace("Group ","")
            if len(table)>=1: classified[f"1{letter}"]=table[0]
            if len(table)>=2: classified[f"2{letter}"]=table[1]
            if len(table)>=3: classified[f"3{letter}"]=table[2]
        bracket = {}
        for fid,hs,as_ in R32:
            bracket[fid] = {"home_team": classified.get(hs, _tbd_team(hs)), "away_team": classified.get(as_, _tbd_team(as_))}
        for rl in [R16,QF,SF]:
            for fid,hs,as_ in rl:
                hp,ap = int(hs.replace("W","")), int(as_.replace("W",""))
                bracket[fid] = {"home_team": _get_winner_from_prediction(hp,bracket,preds), "away_team": _get_winner_from_prediction(ap,bracket,preds)}

        bracket[10601] = {
            "home_team": _get_winner_from_prediction(10401, bracket, preds),
            "away_team": _get_winner_from_prediction(10402, bracket, preds),
        }

        final_match = bracket[10601]
        final_pred = preds.get(10601)

        home_code = final_match["home_team"].get("code")
        away_code = final_match["away_team"].get("code")
        home_name = final_match["home_team"].get("name")
        away_name = final_match["away_team"].get("name")

        pred_info = "sin predicción"
        if final_pred:
            hg, ag = final_pred.get("predicted_home"), final_pred.get("predicted_away")
            pred_info = f"{hg}-{ag}"

        out.append({
            "name": user.get("display_name",""),
            "final": f"{home_name}({home_code}) vs {away_name}({away_code})",
            "predicted_score": pred_info,
        })
    return {"users": out}

@router.get("/admin/debug-third-calc")
async def debug_third_calc(current_user: dict = Depends(require_admin)):
    from app.services.bracket_service import calculate_group_table, _get_winner_from_prediction, _get_loser_from_prediction, _tbd_team

    R32 = [
        (10101, "2A", "2B"), (10102, "1C", "2F"), (10103, "1E", "3D"),
        (10104, "1F", "2C"), (10105, "2E", "2I"), (10106, "1I", "3F"),
        (10107, "1A", "3E"), (10108, "1L", "3K"), (10109, "1G", "3I"),
        (10110, "1D", "3B"), (10111, "1H", "2J"), (10112, "2K", "2L"),
        (10113, "1B", "3J"), (10114, "2D", "2G"), (10115, "1J", "2H"),
        (10116, "1K", "3L"),
    ]
    R16 = [(10201,"W10101","W10104"),(10202,"W10103","W10106"),(10203,"W10102","W10105"),
           (10204,"W10107","W10108"),(10205,"W10112","W10111"),(10206,"W10110","W10109"),
           (10207,"W10115","W10114"),(10208,"W10113","W10116")]
    QF = [(10301,"W10201","W10202"),(10302,"W10203","W10204"),(10303,"W10205","W10206"),(10304,"W10207","W10208")]
    SF = [(10401,"W10301","W10302"),(10402,"W10303","W10304")]

    group_docs = db.collection("matches").where(filter=FieldFilter("phase","==","group")).stream()
    group_matches = [doc.to_dict() for doc in group_docs]
    groups = {}
    for m in group_matches:
        groups.setdefault(m.get("group",""), []).append(m)

    users = list(db.collection("users").where(filter=FieldFilter("role","==","player")).stream())
    out = []
    for user_doc in users:
        user = user_doc.to_dict()
        uid = user["uid"]
        preds = {p.to_dict()["fixture_id"]: p.to_dict() for p in db.collection("predictions").where(filter=FieldFilter("uid","==",uid)).stream()}
        gt = {g: calculate_group_table(m, preds) for g,m in groups.items()}
        classified = {}
        for g, table in gt.items():
            letter = g.replace("Group ","")
            if len(table)>=1: classified[f"1{letter}"]=table[0]
            if len(table)>=2: classified[f"2{letter}"]=table[1]
            if len(table)>=3: classified[f"3{letter}"]=table[2]
        bracket = {}
        for fid,hs,as_ in R32:
            bracket[fid] = {"home_team": classified.get(hs, _tbd_team(hs)), "away_team": classified.get(as_, _tbd_team(as_))}
        for rl in [R16,QF,SF]:
            for fid,hs,as_ in rl:
                hp,ap = int(hs.replace("W","")), int(as_.replace("W",""))
                bracket[fid] = {"home_team": _get_winner_from_prediction(hp,bracket,preds), "away_team": _get_winner_from_prediction(ap,bracket,preds)}

        bracket[10501] = {
            "home_team": _get_loser_from_prediction(10401, bracket, preds),
            "away_team": _get_loser_from_prediction(10402, bracket, preds),
        }

        third_match = bracket[10501]
        third_pred = preds.get(10501)

        home_code = third_match["home_team"].get("code")
        away_code = third_match["away_team"].get("code")
        home_name = third_match["home_team"].get("name")
        away_name = third_match["away_team"].get("name")

        pred_info = "sin predicción"
        if third_pred:
            hg, ag = third_pred.get("predicted_home"), third_pred.get("predicted_away")
            pred_info = f"{hg}-{ag}"

        out.append({
            "name": user.get("display_name",""),
            "third_place_match": f"{home_name}({home_code}) vs {away_name}({away_code})",
            "predicted_score": pred_info,
        })
    return {"users": out}

@router.get("/admin/preview-top-scorer")
async def preview_top_scorer(current_user: dict = Depends(require_admin)):
    docs = db.collection("special_predictions").stream()
    out = []
    for doc in docs:
        d = doc.to_dict()
        out.append({"uid": d.get("uid"), "player_name": d.get("player_name"), "team_name": d.get("team_name")})
    return {"total": len(out), "predictions": out}