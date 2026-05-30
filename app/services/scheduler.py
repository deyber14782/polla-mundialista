from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from app.services.matches_service import update_live_matches
from app.core.firebase import db
import logging

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def sync_live_matches():
    """
    Consulta la API de fútbol y actualiza los partidos en vivo.
    Solo ejecuta si hay partidos activos para no gastar requests.
    """
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
    Marca como bloqueadas las predicciones de partidos que ya comenzaron.
    Corre cada minuto para ser preciso con el horario de inicio.
    """
    try:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()

        # Partidos que aún están como NS pero ya deberían haber empezado
        matches_docs = db.collection("matches")\
            .where("status", "==", "NS")\
            .stream()

        count = 0
        for doc in matches_docs:
            match = doc.to_dict()
            kickoff = match.get("kickoff", "")
            if kickoff and kickoff <= now:
                # Actualizamos predicciones a locked
                preds = db.collection("predictions")\
                    .where("fixture_id", "==", match["fixture_id"])\
                    .where("status", "==", "pending")\
                    .stream()

                for pred in preds:
                    pred.reference.update({"status": "locked"})
                    count += 1

        if count:
            logger.info(f"Lock: {count} predicciones bloqueadas")

    except Exception as e:
        logger.error(f"Error en lock_started_matches: {e}")


def start_scheduler():
    """Registra todos los jobs y arranca el scheduler."""

    # Sync de partidos en vivo cada 5 minutos
    scheduler.add_job(
        sync_live_matches,
        trigger=IntervalTrigger(minutes=5),
        id="sync_live_matches",
        name="Sincronizar partidos en vivo",
        replace_existing=True,
    )

    # Bloqueo de predicciones cada minuto
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