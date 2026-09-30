# Contrats REST et tâches

Base locale : `http://localhost:8080`. Sauf login et health, les routes API attendent `Authorization: Bearer <JWT>`. Les erreurs sont `{ "detail": "..." }`; les événements refusent les champs inconnus.

## Routes HTTP

| Méthode et route | Rôle | Contrat / effet |
|---|---|---|
| `POST /api/auth/token` | public | formulaire OAuth2 `username`, `password`; JWT et rôle |
| `GET /api/auth/me` | authentifié | identité active |
| `GET /api/dashboard` | authentifié | compteurs, alertes récentes, mode worker/IA |
| `GET /api/alerts?q=&severity=&status_filter=&limit=` | authentifié | alertes filtrables, max 200 |
| `POST /api/events/batch` | analyst/admin/manager | lot de 1..200; déduplication `(source, external_id)` |
| `POST /api/demo/scenario` | analyst/admin/manager | trois événements synthétiques puis corrélation |
| `POST /api/alerts/{id}/incident` | analyst/admin/manager | création; 409 si l’alerte a déjà un incident |
| `GET /api/incidents[?status_filter=&q=]` | authentifié | dossiers et affectation |
| `GET /api/incidents/{id}` | authentifié | contexte, timeline, événements et exécutions |
| `PATCH /api/incidents/{id}` | analyst/admin/manager | statut/affectation/sévérité, transitions contrôlées; chaîne vide pour désaffecter |
| `POST /api/incidents/{id}/comments` | authentifié | `{ "content": "..." }`, max 4000 caractères |
| `POST /api/incidents/{id}/evidence` | authentifié | multipart `file`, max 4 Mio, SHA-256 |
| `POST /api/incidents/{id}/assistant` | authentifié | question; résumé, recommandations, faits et caveat |
| `GET /api/playbooks` | authentifié | définitions simulées |
| `POST /api/incidents/{id}/playbooks` | analyst/admin/manager | `collect_evidence`, `isolate_host`, `disable_account` |
| `POST /api/playbook-runs/{id}/approve` | admin/manager | approbation enregistrée; résultat reste simulé |
| `GET /api/rules`, `PATCH /api/rules/{key}` | admin/manager | règles de corrélation configurables |
| `GET /api/users` | admin/manager | utilisateurs sans hash de mot de passe |
| `POST /api/users` | admin | rôle contrôlé, mot de passe min 12 caractères |
| `GET /api/notifications` | authentifié | compte courant uniquement |
| `PATCH /api/notifications/{id}/read` | authentifié | destinataire uniquement |
| `GET /api/audit` | admin/manager | 100 opérations récentes |

## Événement d’entrée

```json
{
  "source": "edr-sim",
  "external_id": "auth-fail-001",
  "event_type": "auth_failure",
  "occurred_at": "2026-09-30T10:00:00Z",
  "source_ip": "203.0.113.42",
  "domain": "login-example.invalid",
  "username": "jules",
  "asset": "prod-api-01",
  "outcome": "denied",
  "message": "Échec de connexion synthétique",
  "attributes": { "attempt": 1 }
}
```

Les adresses utilisent des plages de documentation. `auth-failure-burst` démarre avec un seuil de trois événements `auth_failure` sur 15 minutes. Le sujet est l’IP source, sinon l’utilisateur ou la source. Un rejeu retourne `duplicates`, sans nouvelle ligne.

## Tâches et audit

| Tâche Celery | File | Données | Échecs |
|---|---|---|---|
| `app.worker.process_event_ids` | `sentinel.events` | IDs d’événements validés en base | 3 retries bornés, puis Redis `sentinel:dead_letters` |
| `app.worker.execute_playbook` | `sentinel.events` | ID de run | `collect_evidence` uniquement; autres actions rejetées |

La DLQ de démonstration est une liste Redis. En production, elle exige rétention, alerting, replay contrôlé et audit. L’idempotence métier repose sur les clés d’événement, l’alerte et le run.

Événements audités : `events.ingested`, `demo.scenario_started`, `incident.created/updated/comment_added/evidence_added`, `assistant.analysis_requested`, `playbook.requested/approved_simulated`, `rule.updated`, `user.created`, `notification.read`. L’adaptateur e-mail ne contacte pas SMTP et émet seulement un log `demo_email_notification`.

## Compléments de contrats

| Méthode et route | Rôle | Effet |
|---|---|---|
| `GET /api/assignees` | authentifié | comptes actifs disponibles pour l’affectation |
| `GET /api/procedures?q=` | authentifié | procédures hors ligne, ID et version, étapes |
| `GET /api/incidents/{id}/report` | authentifié | export JSON horodaté du dossier et journal d’export |
| `GET /api/incidents/{id}/evidence/{entry_id}` | authentifié | téléchargement de la preuve liée au dossier |
| `GET /api/integrations`, `PATCH /api/integrations/{key}` | admin/manager | statut des sources et providers simulés |

`source` et `external_id` sont normalisés avant déduplication. Une IP invalide ou une date sans fuseau est refusée avec 422. Les sources configurées désactivées retournent 409. Les filtres précèdent la limite SQL. Le compteur `events_24h` porte sur les événements reçus depuis 24 heures.

Routage : `/api/events/*` et `/api/demo/*` → ingestion; `/api/procedures` et `/api/incidents/{id}/assistant` → assistant; les autres routes → API SOC. Chaque service expose `/health`, `/ready`, `/metrics` sur son port interne.
