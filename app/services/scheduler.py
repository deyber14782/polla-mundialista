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

        # Buscar partidos que YA deberían haber empezado pero siguen en NS
        # O que están en vivo
        all_docs = db.collection("matches").stream()
        should_check = False

        for doc in all_docs:
            m = doc.to_dict()
            status = m.get("status", "NS")
            kickoff = m.get("kickoff", "")

            # Si hay partidos en vivo, obvio hay que actualizar
            if status in ["1H", "HT", "2H"]:
                should_check = True
                break

            # Si el kickoff ya pasó pero sigue en NS, hay que actualizar
            if status == "NS" and kickoff:
                try:
                    ko_time = datetime.fromisoformat(kickoff.replace("Z", "+00:00"))
                    if now > ko_time:
                        should_check = True
                        break
                except:
                    pass

        if should_check:
            result = await update_live_matches()
            logger.info(f"Sync: {result['updated']} partidos actualizados")
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