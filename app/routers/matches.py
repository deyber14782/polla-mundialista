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

router = APIRouter(prefix="/matches", tags=["Matches"])


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
    """Resetea TODOS los puntos y recalcula, verificando timestamps."""
    from app.services.matches_service import calculate_points
    from datetime import datetime, timezone

    # 1. Resetear todos los usuarios a 0
    users = list(db.collection("users").stream())
    for u in users:
        u.reference.update({
            "total_score": 0,
            "exact_results": 0,
            "predictions_count": 0,
        })

    # 2. Cargar todos los matches en un dict
    matches_dict = {doc.to_dict()["fixture_id"]: doc.to_dict() 
                    for doc in db.collection("matches").stream()}

    # 3. Procesar cada predicción individualmente
    all_preds = list(db.collection("predictions").stream())
    processed_count = 0
    late_count = 0

    for pred_doc in all_preds:
        pred = pred_doc.to_dict()
        fixture_id = pred.get("fixture_id")
        match = matches_dict.get(fixture_id)

        if not match or match.get("status") != "FT":
            # Partido no terminado: resetear predicción
            pred_doc.reference.update({
                "points": None,
                "processed": False,
                "status": "pending",
            })
            continue

        # Verificar si la predicción se hizo DESPUÉS del kickoff
        kickoff_str = match.get("kickoff", "")
        pred_update_time = pred_doc.update_time  # Timestamp de Firestore
        
        try:
            kickoff_time = datetime.fromisoformat(kickoff_str.replace("Z", "+00:00"))
            if pred_update_time and pred_update_time.timestamp() > kickoff_time.timestamp():
                # Predicción tardía: 0 puntos
                pred_doc.reference.update({
                    "points": 0,
                    "processed": True,
                    "status": "processed",
                })
                late_count += 1
                continue
        except:
            pass

        # Calcular puntos normalmente
        real_home = match["score"]["home"]
        real_away = match["score"]["away"]

        if real_home is None or real_away is None:
            continue

        points = calculate_points(
            pred_home=pred.get("predicted_home", 0),
            pred_away=pred.get("predicted_away", 0),
            real_home=real_home,
            real_away=real_away,
        )

        pred_doc.reference.update({
            "points": points,
            "processed": True,
            "status": "processed",
        })

        # Actualizar usuario
        uid = pred.get("uid")
        if uid:
            user_ref = db.collection("users").document(uid)
            user_doc = user_ref.get()
            if user_doc.exists:
                user_data = user_doc.to_dict()
                exact = 1 if points == 3 else 0
                user_ref.update({
                    "total_score": user_data.get("total_score", 0) + points,
                    "exact_results": user_data.get("exact_results", 0) + exact,
                })

        processed_count += 1

    # 4. Actualizar predictions_count de cada usuario
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