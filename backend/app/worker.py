import json
import logging

from celery import Celery
from redis import Redis
from sqlalchemy.orm import Session

from app.config import settings
from app.logging_config import configure_logging
from app.database import SessionLocal
from app.detection import correlate_event
from app.models import IncidentEntry, PlaybookRun, SecurityEvent

configure_logging()


logger = logging.getLogger("sentinel.worker")
celery_app = Celery("sentinel", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_time_limit=90,
    task_soft_time_limit=75,
    result_expires=3600,
    task_default_queue="sentinel.events",
    task_routes={"app.worker.*": {"queue": "sentinel.events"}},
)

if settings.otel_enabled:
    from opentelemetry.instrumentation.celery import CeleryInstrumentor

    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider(resource=Resource.create({"service.name": "sentinel-worker"}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint)))
    trace.set_tracer_provider(provider)
    CeleryInstrumentor().instrument()


def dead_letter(task_name: str, payload: dict, exc: Exception) -> None:
    client = Redis.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=2)
    client.rpush("sentinel:dead_letters", json.dumps({"task": task_name, "payload": payload,
                                                       "error": type(exc).__name__, "message": str(exc)[:500]}))
    logger.error(json.dumps({"event": "task_dead_lettered", "task": task_name, "error": type(exc).__name__}))


def retry_or_dead_letter(task, task_name: str, payload: dict, exc: Exception):
    if task.request.retries >= 3:
        dead_letter(task_name, payload, exc)
        raise exc
    raise task.retry(exc=exc, countdown=min(2 ** (task.request.retries + 1), 8))


@celery_app.task(bind=True, name="app.worker.process_event_ids", max_retries=3)
def process_event_ids(self, event_ids: list[int]) -> dict:
    db: Session = SessionLocal()
    try:
        created = 0
        for event_id in event_ids:
            event = db.query(SecurityEvent).filter_by(id=event_id).first()
            if event:
                created += len(correlate_event(db, event))
        db.commit()
        return {"processed": len(event_ids), "alerts_touched": created}
    except Exception as exc:
        db.rollback()
        retry_or_dead_letter(self, "process_event_ids", {"event_ids": event_ids}, exc)
    finally:
        db.close()


@celery_app.task(bind=True, name="app.worker.execute_playbook", max_retries=3)
def execute_playbook(self, run_id: int) -> dict:
    db: Session = SessionLocal()
    try:
        run = db.query(PlaybookRun).filter_by(id=run_id).with_for_update().first()
        if not run:
            return {"status": "missing"}
        if run.status == "completed_simulated":
            return {"run_id": run_id, "status": run.status}
        if run.playbook_key != "collect_evidence":
            raise ValueError("Le worker n’exécute que les playbooks non sensibles")
        run.status = "completed_simulated"
        run.result = {"mode": "simulation", "performed": False, "message": "Aucune action externe exécutée."}
        db.add(IncidentEntry(incident_id=run.incident_id, kind="playbook", content="Collecte de preuves simulée terminée.", author="worker"))
        db.commit()
        return {"run_id": run_id, "status": run.status}
    except Exception as exc:
        db.rollback()
        retry_or_dead_letter(self, "execute_playbook", {"run_id": run_id}, exc)
    finally:
        db.close()
