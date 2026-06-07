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
        live_statuses = ["1H", "HT", "2H"]
        live_docs = db.collection("matches").stream()
        has_live = any(
            doc.to_dict().get("status") in live_statuses
            for doc in live_docs
        )

        if has_live:
            result = await update_live_matches()
            logger.info(f"Sync live: {result['updated']} partidos actualizados")
        else:
            logger.info("Sync live: no hay partidos en vivo")

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