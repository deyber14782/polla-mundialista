from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from app.services.matches_service import update_live_matches
from app.core.firebase import db
from google.cloud.firestore_v1.base_query import FieldFilter
import logging

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def sync_live_matches():
    try:
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        all_docs = db.collection("matches").stream()
        should_check = False

        for doc in all_docs:
            m = doc.to_dict()
            status = m.get("status", "NS")
            kickoff = m.get("kickoff", "")

            if status in ["1H", "HT", "2H"]:
                should_check = True
                break

            if status == "NS" and kickoff:
                try:
                    ko_time = datetime.fromisoformat(kickoff.replace("Z", "+00:00"))
                    if now > ko_time:
                        should_check = True
                        break
                except:
                    pass

        if should_check:
            # Usar la misma lógica de force-sync con mapeo de nombres
            from app.services.football_api import get_world_cup_fixtures
            from app.services.matches_service import parse_fixture, calculate_points_for_match
            from app.core import cache

            NAME_MAP = {
                "méxico": "mexico", "sudáfrica": "south africa",
                "corea del sur": "south korea", "chequia": "czech republic",
                "canadá": "canada", "bosnia-herzegovina": "bosnia & herzegovina",
                "catar": "qatar", "suiza": "switzerland", "brasil": "brazil",
                "haití": "haiti", "escocia": "scotland", "marruecos": "morocco",
                "estados unidos": "usa", "turquía": "turkey", "alemania": "germany",
                "curazao": "curacao", "costa de marfil": "ivory coast",
                "países bajos": "netherlands", "japón": "japan", "suecia": "sweden",
                "túnez": "tunisia", "bélgica": "belgium", "egipto": "egypt",
                "irán": "iran", "nueva zelanda": "new zealand", "españa": "spain",
                "cabo verde": "cape verde", "arabia saudita": "saudi arabia",
                "francia": "france", "senegal": "senegal", "irak": "iraq",
                "noruega": "norway", "argentina": "argentina", "argelia": "algeria",
                "austria": "austria", "jordania": "jordan", "portugal": "portugal",
                "rd congo": "dr congo", "uzbekistán": "uzbekistan",
                "colombia": "colombia", "inglaterra": "england", "croacia": "croatia",
                "ghana": "ghana", "panamá": "panama", "ecuador": "ecuador",
                "uruguay": "uruguay", "türkiye": "turkey",  "curaçao": "curacao", "cape verde islands": "cape verde", "rd congo": "dr congo", "congo dr": "dr congo",
                "czechia": "czech republic",
            }
            def normalize(name):
                return NAME_MAP.get(name.lower().strip(), name.lower().strip())

            fixtures = await get_world_cup_fixtures()
            if fixtures:
                api_lookup = {}
                for f in fixtures:
                    p = parse_fixture(f)
                    h = normalize(p["home_team"]["name"])
                    a = normalize(p["away_team"]["name"])
                    api_lookup[(h, a, p["kickoff"][:10])] = p

                for doc in db.collection("matches").stream():
                    m = doc.to_dict()
                    h = normalize(m["home_team"]["name"])
                    a = normalize(m["away_team"]["name"])
                    api_match = api_lookup.get((h, a, m["kickoff"][:10])) or api_lookup.get((a, h, m["kickoff"][:10]))
                    if not api_match:
                        continue
                    doc.reference.update({"status": api_match["status"], "score": api_match["score"]})
                    if api_match["status"] == "FT" and api_match["score"]["home"] is not None:
                        await calculate_points_for_match(int(m["fixture_id"]))

                cache.invalidate("all_matches", "matches_dict", "ranking")
                logger.info(f"Sync completado con {len(fixtures)} fixtures de la API")
        else:
            logger.info("Sync: no hay partidos por actualizar")

    except Exception as e:
        logger.error(f"Error en sync_live_matches: {e}")


async def lock_started_matches():
    """
    Bloquea todas las predicciones pendientes cuando
    arranca el primer partido del Mundial.
    """
    try:
        from datetime import datetime, timezone
        from app.services.predictions_service import WORLD_CUP_START

        now = datetime.now(timezone.utc)
        if now < WORLD_CUP_START:
            return  # Aún no es hora

        # Bloquear todas las predicciones que sigan en pending
        preds = db.collection("predictions")\
            .where(filter=FieldFilter("status", "==", "pending"))\
            .stream()

        count = 0
        for pred in preds:
            pred.reference.update({"status": "locked"})
            count += 1

        if count:
            logger.info(f"Lock total: {count} predicciones bloqueadas")

    except Exception as e:
        logger.error(f"Error en lock_started_matches: {e}")


def start_scheduler():

    scheduler.add_job(
            sync_live_matches,
            trigger=IntervalTrigger(minutes=5),
            id="sync_live_matches",
            name="Sincronizar partidos en vivo",
            replace_existing=True,
        )

    scheduler.add_job(
        lock_started_matches,
        trigger=IntervalTrigger(minutes=1),
        id="lock_started_matches",
        name="Bloquear predicciones de partidos iniciados",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("Scheduler iniciado correctamente")


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Scheduler detenido")