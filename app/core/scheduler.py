"""Scheduler de tareas programadas con APScheduler.

Registra jobs cron y permite ejecucion manual desde admin.
Cada ejecucion se registra en mkt_task_log.
"""

import logging
import traceback
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.database import async_session
from app.models.task_log import TaskLog

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="America/La_Paz")

# Registry of available jobs
JOB_REGISTRY: dict[str, dict] = {}


def _register(name: str, label: str, module_path: str, cron: str, description: str):
    """Registra un job en el registry y en el scheduler."""
    JOB_REGISTRY[name] = {
        "name": name,
        "label": label,
        "module_path": module_path,
        "cron": cron,
        "description": description,
    }

    async def wrapper():
        await execute_job(name)

    trigger = CronTrigger.from_crontab(cron)
    scheduler.add_job(wrapper, trigger, id=name, replace_existing=True, name=label)


def setup_jobs():
    """Registra todos los jobs programados."""
    _register(
        name="price_refresh",
        label="Recalcular Precios",
        module_path="app.tasks.price_refresh",
        cron="0 3 * * *",  # Diario 3AM
        description="Recalcula precios de referencia de insumos con datos de cotizaciones y pedidos completados.",
    )
    _register(
        name="material_curation",
        label="Curacion de Materiales",
        module_path="app.tasks.material_curation",
        cron="0 4 * * *",  # Diario 4AM
        description="Detecta duplicados en el catalogo y agrupa insumos similares automaticamente.",
    )
    _register(
        name="subscription_check",
        label="Revision de Suscripciones",
        module_path="app.tasks.subscription_check",
        cron="0 8 * * *",  # Diario 8AM
        description="Marca suscripciones expiradas y notifica a empresas cuya suscripcion esta por vencer.",
    )


async def execute_job(job_name: str) -> dict:
    """Ejecuta un job y registra el resultado en mkt_task_log."""
    import importlib

    job_info = JOB_REGISTRY.get(job_name)
    if not job_info:
        raise ValueError(f"Job no encontrado: {job_name}")

    start = datetime.now(timezone.utc)

    async with async_session() as db:
        log = TaskLog(
            job_name=job_name,
            state="running",
            started_at=start,
        )
        db.add(log)
        await db.commit()
        log_id = log.id

    try:
        module = importlib.import_module(job_info["module_path"])
        async with async_session() as db:
            result = await module.run(db)

        end = datetime.now(timezone.utc)
        duration = (end - start).total_seconds()

        async with async_session() as db:
            log = await db.get(TaskLog, log_id)
            if log:
                log.state = "success"
                log.finished_at = end
                log.duration_s = round(duration, 2)
                log.result_summary = _summarize(result)
                log.result_data = result if isinstance(result, dict) else {"result": str(result)}
                await db.commit()

        logger.info("Job %s completado en %.1fs: %s", job_name, duration, result)
        return {"state": "success", "duration_s": round(duration, 2), "result": result}

    except Exception as e:
        end = datetime.now(timezone.utc)
        duration = (end - start).total_seconds()
        error_msg = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"

        async with async_session() as db:
            log = await db.get(TaskLog, log_id)
            if log:
                log.state = "error"
                log.finished_at = end
                log.duration_s = round(duration, 2)
                log.error = error_msg
                await db.commit()

        logger.error("Job %s fallo en %.1fs: %s", job_name, duration, e)
        return {"state": "error", "duration_s": round(duration, 2), "error": str(e)}


def _summarize(result) -> str:
    """Genera un resumen legible del resultado."""
    if isinstance(result, dict):
        parts = []
        for k, v in result.items():
            parts.append(f"{k}: {v}")
        return ", ".join(parts)
    return str(result)


def start_scheduler():
    """Inicia el scheduler (llamar en lifespan startup)."""
    setup_jobs()
    scheduler.start()
    logger.info("Scheduler iniciado con %d jobs", len(JOB_REGISTRY))


def stop_scheduler():
    """Detiene el scheduler (llamar en lifespan shutdown)."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler detenido")
