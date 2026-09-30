from app.database import SessionLocal
from app.models import IncidentEntry, PlaybookRun
from app.worker import execute_playbook
from conftest import token
from test_soc_flow import suspicious_batch


def create_case(client, headers):
    alert = client.post("/api/events/batch", json=suspicious_batch(), headers=headers).json()["alerts"][0]
    return client.post(f"/api/alerts/{alert['id']}/incident", headers=headers).json()


def test_filters_closure_and_reopening(client, auth_headers):
    case = create_case(client, auth_headers)
    filtered = client.get("/api/alerts?severity=high&q=203.0.113&limit=1", headers=auth_headers)
    assert filtered.status_code == 200
    assert len(filtered.json()) == 1
    assert len(client.get("/api/incidents?status_filter=triage&q=203.0.113", headers=auth_headers).json()) == 1
    path = f"/api/incidents/{case['id']}"
    changed = client.patch(path, json={"severity": "critical", "assignee": ""}, headers=auth_headers)
    assert changed.json()["severity"] == "critical"
    assert changed.json()["assignee"] is None
    assert client.patch(path, json={"status": "closed"}, headers=auth_headers).status_code == 200
    assert client.get("/api/dashboard", headers=auth_headers).json()["open_alerts"] == 0
    assert client.patch(path, json={"status": "investigating"}, headers=auth_headers).status_code == 200
    assert client.get("/api/dashboard", headers=auth_headers).json()["open_alerts"] == 1


def test_normalized_duplicates_and_correlation_evidence(client, auth_headers):
    batch = suspicious_batch()
    client.post("/api/events/batch", json=batch, headers=auth_headers)
    for event in batch["events"]:
        event["source"] = " edr-sim "
        event["external_id"] = " " + event["external_id"] + " "
    response = client.post("/api/events/batch", json=batch, headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["duplicates"] == 3
    event = batch["events"][0]
    event["external_id"] = "fourth"
    result = client.post("/api/events/batch", json={"events": [event]}, headers=auth_headers).json()
    assert result["alerts"][0]["event_count"] == 4
    assert len(result["alerts"][0]["context"]["event_ids"]) == 4


def test_worker_redelivery_does_not_repeat_completed_action(client, auth_headers):
    case = create_case(client, auth_headers)
    run = client.post(f"/api/incidents/{case['id']}/playbooks", json={"playbook_key": "collect_evidence"}, headers=auth_headers).json()
    with SessionLocal() as db:
        before = db.query(IncidentEntry).count()
    assert execute_playbook.run(run["id"])["status"] == "completed_simulated"
    with SessionLocal() as db:
        assert db.query(IncidentEntry).count() == before


def test_publish_happens_after_commit(client, auth_headers, monkeypatch):
    case = create_case(client, auth_headers)
    monkeypatch.setenv("ASYNC_MODE", "celery")
    observed = []
    def observe(run_id):
        with SessionLocal() as db:
            observed.append(db.get(PlaybookRun, run_id).status)
    monkeypatch.setattr(execute_playbook, "delay", observe)
    response = client.post(f"/api/incidents/{case['id']}/playbooks", json={"playbook_key": "collect_evidence"}, headers=auth_headers)
    assert response.status_code == 200
    assert observed == ["queued"]


def test_closed_case_does_not_swallow_new_attack(client, auth_headers):
    case = create_case(client, auth_headers)
    client.patch(f"/api/incidents/{case['id']}", json={"status": "closed"}, headers=auth_headers)
    batch = suspicious_batch()
    for event in batch["events"]:
        event["external_id"] += "-new"
    result = client.post("/api/events/batch", json=batch, headers=auth_headers).json()
    assert result["alerts"][0]["id"] != case["alert_id"]
    assert result["alerts"][0]["event_count"] == 3


def test_demo_is_repeatable(client, auth_headers):
    first = client.post("/api/demo/scenario", headers=auth_headers).json()
    second = client.post("/api/demo/scenario", headers=auth_headers).json()
    assert first["alerts"][0]["id"] != second["alerts"][0]["id"]


def test_source_disable_and_input_validation(client, auth_headers):
    manager = {"Authorization": f"Bearer {token(client, 'manager', 'DemoManager!2026')}"}
    client.patch("/api/integrations/edr-sim", json={"enabled": False}, headers=manager)
    assert client.post("/api/events/batch", json=suspicious_batch(), headers=auth_headers).status_code == 409
    batch = suspicious_batch()
    batch["events"][0]["source_ip"] = "not-an-ip"
    assert client.post("/api/events/batch", json=batch, headers=auth_headers).status_code == 422
    assert client.patch("/api/rules/auth-failure-burst", json={"threshold": None}, headers=manager).status_code == 200


def test_procedures_report_and_rate_limit(client, auth_headers, monkeypatch):
    from app.config import settings
    from app.main import request_times
    case = create_case(client, auth_headers)
    procedures = client.get("/api/procedures?q=preuve", headers=auth_headers).json()
    assert procedures[0]["id"] == "RB-EVID-001"
    answer = client.post(f"/api/incidents/{case['id']}/assistant", json={"question": "preuve"}, headers=auth_headers).json()
    assert any(item.startswith("RB-") for item in answer["evidence"])
    assert client.get(f"/api/incidents/{case['id']}/report", headers=auth_headers).json()["incident"]["id"] == case["id"]
    monkeypatch.setattr(settings, "rate_limit_per_minute", 1)
    request_times.clear()
    assert client.get("/api/dashboard", headers=auth_headers).status_code == 200
    limited = client.get("/api/dashboard", headers=auth_headers)
    assert limited.status_code == 429
    assert limited.headers["Retry-After"] == "60"
