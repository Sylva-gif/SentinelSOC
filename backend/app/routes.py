import hashlib
import json
import logging
import os
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError

from app.assistant import analyze_incident
from app.config import settings
from app.database import get_db
from app.detection import correlate_event
from app.models import Alert, AuditLog, DetectionRule, Incident, IncidentEntry, Integration, Notification, PlaybookRun, SecurityEvent, User, utcnow
from app.procedures import search_procedures
from app.schemas import AssistantInput, EntryInput, EventBatch, IncidentUpdate, IntegrationUpdate, PlaybookInput, RuleUpdate, UserInput
from app.security import create_access_token, current_user, hash_password, require_roles, verify_password

logger = logging.getLogger("sentinel")
router = APIRouter(prefix="/api")


def audit(db: Session, user: User, action: str, target: str, details: dict | None = None) -> None:
    db.add(AuditLog(actor=user.username, action=action, target=target, details=details or {}))


def serialize_alert(alert: Alert) -> dict:
    return {"id": alert.id, "title": alert.title, "severity": alert.severity, "status": alert.status,
            "event_count": alert.event_count, "context": alert.context, "created_at": alert.created_at.isoformat(),
            "incident_id": alert.incident.id if alert.incident else None}


def serialize_event(event: SecurityEvent) -> dict:
    return {"id": event.id, "source": event.source, "external_id": event.external_id, "event_type": event.event_type,
            "occurred_at": event.occurred_at.isoformat(), "source_ip": event.source_ip, "domain": event.domain,
            "username": event.username, "asset": event.asset, "outcome": event.outcome, "message": event.message}


def serialize_incident(incident: Incident, db: Session, full: bool = False) -> dict:
    result = {"id": incident.id, "alert_id": incident.alert_id, "title": incident.title, "severity": incident.severity,
              "status": incident.status, "assignee": incident.assignee, "created_at": incident.created_at.isoformat(),
              "updated_at": incident.updated_at.isoformat(), "closed_at": incident.closed_at.isoformat() if incident.closed_at else None,
              "context": incident.alert.context, "event_count": incident.alert.event_count}
    if full:
        result["timeline"] = [{"id": item.id, "kind": item.kind, "content": item.content, "author": item.author,
                               "created_at": item.created_at.isoformat()} for item in incident.entries]
        event_ids = incident.alert.context.get("event_ids", [])
        events = db.query(SecurityEvent).filter(SecurityEvent.id.in_(event_ids)).order_by(SecurityEvent.occurred_at).all() if event_ids else []
        result["events"] = [serialize_event(item) for item in events]
        runs = db.query(PlaybookRun).filter_by(incident_id=incident.id).order_by(PlaybookRun.created_at.desc()).all()
        result["playbook_runs"] = [{"id": run.id, "playbook_key": run.playbook_key, "status": run.status,
                                    "requested_by": run.requested_by, "approved_by": run.approved_by,
                                    "result": run.result, "created_at": run.created_at.isoformat()} for run in runs]
    return result


def finish_simulated_run(db: Session, run: PlaybookRun, actor: str) -> None:
    run.status = "completed_simulated"
    run.result = {"mode": "simulation", "action": run.playbook_key, "performed": False,
                  "message": "Aucune action externe exécutée; résultat de démonstration uniquement."}
    db.add(IncidentEntry(incident_id=run.incident_id, kind="playbook", content=f"Playbook {run.playbook_key}: simulation terminée.", author=actor))


@router.post("/auth/token", tags=["identity"])
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)) -> dict:
    user = db.query(User).filter_by(username=form.username, active=True).first()
    if not user or not verify_password(form.password, user.password_hash):
        db.add(AuditLog(actor=(form.username or "unknown")[:80], action="auth.login_failed", target="session"))
        db.commit()
        raise HTTPException(status_code=401, detail="Identifiants invalides", headers={"WWW-Authenticate": "Bearer"})
    audit(db, user, "auth.login_succeeded", "session")
    db.commit()
    return {"access_token": create_access_token(user.username), "token_type": "bearer", "username": user.username, "role": user.role}


@router.get("/auth/me", tags=["identity"])
def whoami(user: User = Depends(current_user)) -> dict:
    return {"username": user.username, "role": user.role}


@router.get("/dashboard", tags=["soc"])
def dashboard(db: Session = Depends(get_db), _: User = Depends(current_user)) -> dict:
    recent = db.query(Alert).options(joinedload(Alert.incident)).order_by(Alert.created_at.desc()).limit(6).all()
    return {"open_alerts": db.query(Alert).filter(Alert.status != "closed").count(),
            "open_incidents": db.query(Incident).filter(Incident.status != "closed").count(),
            "critical_alerts": db.query(Alert).filter(Alert.severity == "critical", Alert.status != "closed").count(),
            "events_24h": db.query(SecurityEvent).filter(SecurityEvent.created_at >= utcnow() - timedelta(hours=24)).count(), "recent_alerts": [serialize_alert(item) for item in recent],
            "system": {"api": "operational", "worker_mode": os.getenv("ASYNC_MODE", "inline"), "ai_provider": settings.ai_provider}}


@router.get("/alerts", tags=["soc"])
def list_alerts(severity: str | None = None, status_filter: str | None = None, q: str | None = None, limit: int = 100,
                db: Session = Depends(get_db), _: User = Depends(current_user)) -> list[dict]:
    query = db.query(Alert).options(joinedload(Alert.incident)).order_by(Alert.created_at.desc())
    if severity in {"low", "medium", "high", "critical"}:
        query = query.filter(Alert.severity == severity)
    if status_filter:
        query = query.filter(Alert.status == status_filter)
    if q:
        query = query.filter(Alert.title.ilike(f"%{q[:100]}%"))
    return [serialize_alert(item) for item in query.limit(min(max(limit, 1), 200)).all()]


@router.post("/events/batch", tags=["ingestion"])
def ingest_events(payload: EventBatch, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "analyst", "soc_manager"))) -> dict:
    accepted: list[SecurityEvent] = []
    duplicates = 0
    disabled_sources = {item.key for item in db.query(Integration).filter_by(kind="event-source", enabled=False).all()}
    if any(item.source in disabled_sources for item in payload.events):
        raise HTTPException(status_code=409, detail="Source disabled by an administrator")
    for item in payload.events:
        exists = db.query(SecurityEvent.id).filter_by(source=item.source, external_id=item.external_id).first()
        if exists:
            duplicates += 1
            continue
        event = SecurityEvent(source=item.source.strip(), external_id=item.external_id.strip(), event_type=item.event_type.strip().lower(),
                              occurred_at=item.occurred_at or utcnow(), source_ip=item.source_ip, domain=item.domain.lower() if item.domain else None,
                              username=item.username, asset=item.asset, outcome=item.outcome, message=item.message, attributes=item.attributes)
        try:
            with db.begin_nested():
                db.add(event)
                db.flush()
        except IntegrityError:
            if not db.query(SecurityEvent.id).filter_by(source=item.source, external_id=item.external_id).first():
                raise
            duplicates += 1
            continue
        accepted.append(event)
    created_alerts: dict[int, Alert] = {}
    queued = os.getenv("ASYNC_MODE", "inline") == "celery" and bool(accepted)
    if queued:
        audit(db, user, "events.ingested", "event-batch", {"accepted": len(accepted), "duplicates": duplicates})
        db.commit()
        try:
            from app.worker import process_event_ids
            process_event_ids.delay([item.id for item in accepted])
        except Exception as exc:
            logger.warning(json.dumps({"event": "worker_enqueue_failed", "reason": type(exc).__name__}))
            queued = False
            for event in accepted:
                for alert in correlate_event(db, event):
                    created_alerts[alert.id] = alert
            db.commit()
    if not queued:
        if not (os.getenv("ASYNC_MODE", "inline") == "celery" and accepted):
            for event in accepted:
                for alert in correlate_event(db, event):
                    created_alerts[alert.id] = alert
            audit(db, user, "events.ingested", "event-batch", {"accepted": len(accepted), "duplicates": duplicates})
            db.commit()
    logger.info(json.dumps({"event": "ingestion_completed", "actor": user.username, "accepted": len(accepted), "duplicates": duplicates}))
    return {"accepted": len(accepted), "duplicates": duplicates, "alerts": [serialize_alert(item) for item in created_alerts.values()],
            "processing": "queued" if queued else "completed"}


@router.post("/demo/scenario", tags=["demo"])
def run_demo_scenario(db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "analyst", "soc_manager"))) -> dict:
    run_id = uuid4().hex[:10]
    events = []
    for index in range(3):
        event = SecurityEvent(source=f"scenario-{run_id}", external_id=f"auth-failure-{index + 1}", event_type="auth_failure",
                              source_ip="203.0.113.42", domain="login-example.invalid", username="jules",
                              asset="prod-api-01", outcome="denied",
                              message="Échec de connexion synthétique; contenu non fiable destiné au triage.",
                              attributes={"scenario": "credential-stuffing-simulation", "attempt": index + 1})
        db.add(event)
        db.flush()
        events.append(event)
    alerts: dict[int, Alert] = {}
    for event in events:
        for alert in correlate_event(db, event):
            alerts[alert.id] = alert
    audit(db, user, "demo.scenario_started", f"scenario:{run_id}", {"events": len(events)})
    db.commit()
    return {"scenario_id": run_id, "accepted": len(events), "alerts": [serialize_alert(item) for item in alerts.values()],
            "next_step": "Créer un incident depuis l’alerte, consulter l’assistant et demander un playbook."}


@router.post("/alerts/{alert_id}/incident", tags=["incidents"])
def create_incident(alert_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "analyst", "soc_manager"))) -> dict:
    alert = db.query(Alert).options(joinedload(Alert.incident)).filter_by(id=alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alerte introuvable")
    if db.query(Incident).filter_by(alert_id=alert_id).first():
        raise HTTPException(status_code=409, detail="Un incident existe déjà pour cette alerte")
    incident = Incident(alert_id=alert.id, title=alert.title, severity=alert.severity, status="triage", assignee=user.username)
    db.add(incident)
    db.flush()
    db.add(IncidentEntry(incident_id=incident.id, kind="system", content="Incident créé depuis une alerte corrélée.", author=user.username))
    alert.status = "incident"
    db.add(Notification(username=user.username, title="Nouvel incident", body=incident.title))
    audit(db, user, "incident.created", f"incident:{incident.id}", {"alert_id": alert.id})
    db.commit()
    logger.info(json.dumps({"event": "demo_email_notification", "recipient": user.username, "incident_id": incident.id}))
    return serialize_incident(incident, db)


@router.get("/incidents", tags=["incidents"])
def list_incidents(status_filter: str | None = None, q: str | None = None, db: Session = Depends(get_db), _: User = Depends(current_user)) -> list[dict]:
    query = db.query(Incident).options(joinedload(Incident.alert)).order_by(Incident.updated_at.desc())
    if status_filter:
        query = query.filter(Incident.status == status_filter)
    if q:
        query = query.filter(Incident.title.ilike(f"%{q[:100]}%"))
    return [serialize_incident(item, db) for item in query.limit(200).all()]


@router.get("/incidents/{incident_id}", tags=["incidents"])
def get_incident(incident_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)) -> dict:
    incident = db.query(Incident).options(joinedload(Incident.alert), joinedload(Incident.entries)).filter_by(id=incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident introuvable")
    return serialize_incident(incident, db, full=True)


@router.patch("/incidents/{incident_id}", tags=["incidents"])
def update_incident(incident_id: int, payload: IncidentUpdate, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "analyst", "soc_manager"))) -> dict:
    incident = db.query(Incident).options(joinedload(Incident.alert)).filter_by(id=incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident introuvable")
    previous = incident.status
    transitions = {"triage": {"investigating", "closed"}, "investigating": {"contained", "resolved", "closed"},
                   "contained": {"investigating", "resolved", "closed"}, "resolved": {"closed", "investigating"}, "closed": {"investigating"}}
    if payload.status and payload.status != previous and payload.status not in transitions[previous]:
        raise HTTPException(status_code=409, detail=f"Transition interdite: {previous} → {payload.status}")
    if payload.status:
        incident.status = payload.status
        incident.closed_at = utcnow() if payload.status == "closed" else None
        incident.alert.status = "closed" if payload.status == "closed" else "incident"
    if payload.severity is not None:
        incident.severity = payload.severity
    if payload.assignee is not None:
        assignee = db.query(User).filter_by(username=payload.assignee, active=True).first() if payload.assignee else None
        if payload.assignee and not assignee:
            raise HTTPException(status_code=422, detail="Analyste actif introuvable")
        incident.assignee = assignee.username if assignee else None
    incident.updated_at = utcnow()
    db.add(IncidentEntry(incident_id=incident.id, kind="status", content=f"Statut: {previous} → {incident.status}; affecté à {incident.assignee or 'personne'}.", author=user.username))
    audit(db, user, "incident.updated", f"incident:{incident.id}", {"status": incident.status, "assignee": incident.assignee, "severity": incident.severity})
    db.commit()
    return serialize_incident(incident, db)


@router.post("/incidents/{incident_id}/comments", tags=["incidents"])
def add_comment(incident_id: int, payload: EntryInput, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    if not db.query(Incident.id).filter_by(id=incident_id).first():
        raise HTTPException(status_code=404, detail="Incident introuvable")
    entry = IncidentEntry(incident_id=incident_id, kind="comment", content=payload.content, author=user.username)
    db.add(entry)
    audit(db, user, "incident.comment_added", f"incident:{incident_id}")
    db.commit()
    return {"id": entry.id, "kind": entry.kind, "content": entry.content, "author": entry.author, "created_at": entry.created_at.isoformat()}


@router.post("/incidents/{incident_id}/evidence", tags=["incidents"])
async def add_evidence(incident_id: int, file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    if not db.query(Incident.id).filter_by(id=incident_id).first():
        raise HTTPException(status_code=404, detail="Incident introuvable")
    contents = await file.read(4 * 1024 * 1024 + 1)
    if not contents or len(contents) > 4 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Preuve vide ou supérieure à 4 Mio")
    safe_name = Path(file.filename or "evidence.bin").name[:120]
    digest = hashlib.sha256(contents).hexdigest()
    directory = Path(settings.data_dir) / "evidence"
    directory.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid4().hex}.bin"
    (directory / stored_name).write_bytes(contents)
    metadata = json.dumps({"name": safe_name, "sha256": digest, "size": len(contents), "storage_key": stored_name})
    entry = IncidentEntry(incident_id=incident_id, kind="evidence", content=metadata, author=user.username)
    db.add(entry)
    audit(db, user, "incident.evidence_added", f"incident:{incident_id}", {"sha256": digest, "size": len(contents)})
    db.commit()
    return {"id": entry.id, "name": safe_name, "sha256": digest, "size": len(contents)}


@router.get("/incidents/{incident_id}/evidence/{entry_id}", tags=["incidents"])
def download_evidence(incident_id: int, entry_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)) -> FileResponse:
    entry = db.query(IncidentEntry).filter_by(id=entry_id, incident_id=incident_id, kind="evidence").first()
    if not entry:
        raise HTTPException(status_code=404, detail="Preuve introuvable")
    metadata = json.loads(entry.content)
    stored_name = metadata.get("storage_key", "")
    if Path(stored_name).name != stored_name or not stored_name.endswith(".bin"):
        raise HTTPException(status_code=410, detail="Référence de preuve invalide")
    path = Path(settings.data_dir) / "evidence" / stored_name
    if not path.is_file():
        raise HTTPException(status_code=410, detail="Fichier de preuve indisponible")
    return FileResponse(path, media_type="application/octet-stream", filename=metadata["name"])


@router.post("/incidents/{incident_id}/assistant", tags=["assistant"])
async def incident_assistant(incident_id: int, payload: AssistantInput, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    incident = db.query(Incident).options(joinedload(Incident.alert), joinedload(Incident.entries)).filter_by(id=incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident introuvable")
    answer = await analyze_incident(serialize_incident(incident, db, full=True), payload.question)
    audit(db, user, "assistant.analysis_requested", f"incident:{incident.id}", {"provider": answer["provider"]})
    db.commit()
    return answer


PLAYBOOKS = [{"key": "collect_evidence", "name": "Préserver les preuves", "sensitive": False, "description": "Simule la collecte des métadonnées d’investigation."},
             {"key": "isolate_host", "name": "Isoler un actif", "sensitive": True, "description": "Action simulée; approbation SOC requise."},
             {"key": "disable_account", "name": "Désactiver un compte", "sensitive": True, "description": "Action simulée; approbation SOC requise."}]


@router.get("/playbooks", tags=["response"])
def list_playbooks(_: User = Depends(current_user)) -> list[dict]:
    return PLAYBOOKS


@router.post("/incidents/{incident_id}/playbooks", tags=["response"])
def launch_playbook(incident_id: int, payload: PlaybookInput, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "analyst", "soc_manager"))) -> dict:
    incident = db.query(Incident.id).filter_by(id=incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident introuvable")
    definition = next(item for item in PLAYBOOKS if item["key"] == payload.playbook_key)
    run = PlaybookRun(incident_id=incident_id, playbook_key=payload.playbook_key,
                      status="awaiting_approval" if definition["sensitive"] else "queued", requested_by=user.username)
    db.add(run)
    db.add(IncidentEntry(incident_id=incident_id, kind="playbook", content=f"Playbook demandé: {definition['name']}.", author=user.username))
    audit(db, user, "playbook.requested", f"incident:{incident_id}", {"playbook": payload.playbook_key, "sensitive": definition["sensitive"]})
    db.flush()
    # Commit before publishing: the worker uses a separate database session.
    db.commit()
    if not definition["sensitive"]:
        if os.getenv("ASYNC_MODE", "inline") == "celery":
            try:
                from app.worker import execute_playbook
                execute_playbook.delay(run.id)
            except Exception:
                finish_simulated_run(db, run, user.username)
        else:
            finish_simulated_run(db, run, user.username)
    db.commit()
    return {"id": run.id, "playbook_key": run.playbook_key, "status": run.status, "result": run.result}


@router.post("/playbook-runs/{run_id}/approve", tags=["response"])
def approve_playbook(run_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "soc_manager"))) -> dict:
    run = db.query(PlaybookRun).filter_by(id=run_id).with_for_update().first()
    if not run:
        raise HTTPException(status_code=404, detail="Exécution introuvable")
    if run.status != "awaiting_approval":
        raise HTTPException(status_code=409, detail="Cette exécution n’attend pas d’approbation")
    run.approved_by = user.username
    finish_simulated_run(db, run, user.username)
    run.result["approved_by"] = user.username
    audit(db, user, "playbook.approved_simulated", f"run:{run.id}", {"playbook": run.playbook_key})
    db.commit()
    return {"id": run.id, "status": run.status, "result": run.result}


@router.get("/rules", tags=["administration"])
def list_rules(db: Session = Depends(get_db), _: User = Depends(require_roles("admin", "soc_manager"))) -> list[dict]:
    return [{"key": item.key, "name": item.name, "event_type": item.event_type, "threshold": item.threshold,
             "window_minutes": item.window_minutes, "severity": item.severity, "enabled": item.enabled}
            for item in db.query(DetectionRule).order_by(DetectionRule.id).all()]


@router.patch("/rules/{rule_key}", tags=["administration"])
def update_rule(rule_key: str, payload: RuleUpdate, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "soc_manager"))) -> dict:
    rule = db.query(DetectionRule).filter_by(key=rule_key).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Règle introuvable")
    for field, value in payload.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(rule, field, value)
    audit(db, user, "rule.updated", f"rule:{rule.key}", payload.model_dump(exclude_unset=True, exclude_none=True))
    db.commit()
    return {"key": rule.key, "name": rule.name, "threshold": rule.threshold, "window_minutes": rule.window_minutes, "severity": rule.severity, "enabled": rule.enabled}


@router.get("/integrations", tags=["administration"])
def list_integrations(db: Session = Depends(get_db), _: User = Depends(require_roles("admin", "soc_manager"))) -> list[dict]:
    return [{"key": item.key, "name": item.name, "kind": item.kind, "mode": item.mode, "enabled": item.enabled}
            for item in db.query(Integration).order_by(Integration.id).all()]


@router.patch("/integrations/{integration_key}", tags=["administration"])
def update_integration(integration_key: str, payload: IntegrationUpdate, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "soc_manager"))) -> dict:
    integration = db.query(Integration).filter_by(key=integration_key).first()
    if not integration:
        raise HTTPException(status_code=404, detail="Intégration introuvable")
    integration.enabled = payload.enabled
    audit(db, user, "integration.updated", f"integration:{integration.key}", {"enabled": integration.enabled})
    db.commit()
    return {"key": integration.key, "name": integration.name, "kind": integration.kind, "mode": integration.mode, "enabled": integration.enabled}


@router.get("/assignees", tags=["incidents"])
def list_assignees(db: Session = Depends(get_db), _: User = Depends(current_user)) -> list[dict]:
    return [{"username": item.username, "role": item.role, "active": item.active}
            for item in db.query(User).filter_by(active=True).order_by(User.username).all()]


@router.get("/users", tags=["administration"])
def list_users(db: Session = Depends(get_db), _: User = Depends(require_roles("admin", "soc_manager"))) -> list[dict]:
    return [{"username": item.username, "role": item.role, "active": item.active} for item in db.query(User).order_by(User.username).all()]


@router.post("/users", tags=["administration"])
def create_user(payload: UserInput, db: Session = Depends(get_db), user: User = Depends(require_roles("admin"))) -> dict:
    if db.query(User).filter_by(username=payload.username).first():
        raise HTTPException(status_code=409, detail="Utilisateur déjà existant")
    created = User(username=payload.username, password_hash=hash_password(payload.password), role=payload.role)
    db.add(created)
    audit(db, user, "user.created", f"user:{created.username}", {"role": created.role})
    db.commit()
    return {"username": created.username, "role": created.role, "active": created.active}


@router.get("/notifications", tags=["notifications"])
def list_notifications(db: Session = Depends(get_db), user: User = Depends(current_user)) -> list[dict]:
    return [{"id": item.id, "title": item.title, "body": item.body, "read": item.read, "created_at": item.created_at.isoformat()}
            for item in db.query(Notification).filter_by(username=user.username).order_by(Notification.created_at.desc()).limit(50).all()]


@router.patch("/notifications/{notification_id}/read", tags=["notifications"])
def mark_notification_read(notification_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    notification = db.query(Notification).filter_by(id=notification_id, username=user.username).first()
    if not notification:
        raise HTTPException(status_code=404, detail="Notification introuvable")
    notification.read = True
    audit(db, user, "notification.read", f"notification:{notification.id}")
    db.commit()
    return {"id": notification.id, "read": notification.read}


@router.get("/audit", tags=["audit"])
def list_audit(db: Session = Depends(get_db), _: User = Depends(require_roles("admin", "soc_manager"))) -> list[dict]:
    return [{"id": item.id, "actor": item.actor, "action": item.action, "target": item.target,
             "details": item.details, "created_at": item.created_at.isoformat()}
            for item in db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(100).all()]


@router.get("/procedures", tags=["assistant"])
def procedures(q: str = "authentification preuve clôture", _: User = Depends(current_user)) -> list[dict]:
    return search_procedures(q[:500])


@router.get("/incidents/{incident_id}/report", tags=["incidents"])
def incident_report(incident_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    incident = db.query(Incident).options(joinedload(Incident.alert), joinedload(Incident.entries)).filter_by(id=incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident introuvable")
    audit(db, user, "incident.report_exported", f"incident:{incident_id}")
    db.commit()
    return {"generated_at": utcnow().isoformat(), "mode": "simulation", "incident": serialize_incident(incident, db, full=True)}
