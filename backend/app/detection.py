from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.enrichment import enrich
from app.models import Alert, DetectionRule, Integration, SecurityEvent


def correlate_event(db: Session, event: SecurityEvent) -> list[Alert]:
    created_or_updated: list[Alert] = []
    rules = db.query(DetectionRule).filter_by(event_type=event.event_type, enabled=True).with_for_update().all()
    for rule in rules:
        now = datetime.now(timezone.utc)
        start = now - timedelta(minutes=rule.window_minutes)
        candidates = db.query(SecurityEvent).filter(
            SecurityEvent.event_type == rule.event_type,
            SecurityEvent.occurred_at >= start,
            SecurityEvent.occurred_at <= now,
        )
        if event.source.startswith("scenario-"):
            candidates = candidates.filter(SecurityEvent.source == event.source)
        if event.source_ip:
            candidates = candidates.filter(SecurityEvent.source_ip == event.source_ip)
        elif event.username:
            candidates = candidates.filter(SecurityEvent.username == event.username)
        else:
            candidates = candidates.filter(SecurityEvent.source == event.source)
        matches = candidates.order_by(SecurityEvent.occurred_at.desc()).limit(500).all()
        if len(matches) < rule.threshold:
            continue
        key_value = event.source_ip or event.username or event.source
        dedupe_key = f"{rule.key}:{key_value}"
        if event.source.startswith("scenario-"):
            dedupe_key += f":{event.source}"
        alert = db.query(Alert).filter_by(dedupe_key=dedupe_key).first()
        correlation_after = alert.context.get("correlation_after") if alert else None
        if correlation_after:
            cutoff = datetime.fromisoformat(correlation_after)
            matches = [item for item in matches if item.created_at.replace(tzinfo=timezone.utc) > cutoff]
            if len(matches) < rule.threshold:
                continue
        if alert and alert.status == "closed" and alert.incident and alert.incident.closed_at:
            cutoff = alert.incident.closed_at.replace(tzinfo=timezone.utc)
            correlation_after = cutoff.isoformat()
            matches = [item for item in matches if item.created_at.replace(tzinfo=timezone.utc) > cutoff]
            if len(matches) < rule.threshold:
                continue
            alert.dedupe_key = f"{dedupe_key}:closed:{alert.id}"
            db.flush()
            alert = None
        if alert is None:
            latest = matches[0]
            intel = db.query(Integration).filter_by(key="intel-offline").first()
            alert = Alert(
                dedupe_key=dedupe_key,
                title=f"{rule.name} · {key_value}",
                severity=rule.severity,
                status="new",
                context={
                    "source": event.source,
                    "rule_key": rule.key,
                    "correlation_after": correlation_after,
                    "source_ip": event.source_ip,
                    "domain": latest.domain,
                    "username": latest.username,
                    "asset": latest.asset,
                    "event_ids": [item.id for item in matches],
                    "enrichment": enrich(event.source_ip, latest.domain, latest.username, latest.asset) if intel is None or intel.enabled else {"status": "disabled"},
                },
            )
            db.add(alert)
        event_ids = sorted(set(alert.context.get("event_ids", [])) | {item.id for item in matches})
        alert.context = {**alert.context, "event_ids": event_ids}
        alert.event_count = len(event_ids)
        created_or_updated.append(alert)
    db.flush()
    return created_or_updated