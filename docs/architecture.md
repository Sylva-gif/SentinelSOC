# Architecture et exploitation

## Composants et responsabilités

| Composant | Responsabilité | Contrats principaux |
|---|---|---|
| Nginx gateway | Sert la console, relaie REST, applique limites de corps et timeouts | HTTP vers API |
| FastAPI SOC API | Identité/RBAC, ingestion, règles, enrichissement, alertes, incidents, assistant, notifications, réponse, audit | REST JSON, OpenAPI |
| Worker Celery | Corrèle les événements et joue les playbooks non sensibles simulés en arrière-plan | Tâches Redis `sentinel.events` |
| PostgreSQL | État métier, événements normalisés, audit et chronologie | SQLAlchemy / Alembic |
| Redis | Broker Celery, résultats temporaires et messages en échec | Redis protocol |
| Volume preuves | Fichiers reçus avec nom aléatoire et SHA-256 | Métadonnées JSON liées à l’incident |
| Providers hors ligne | Réputation IP/domaine et contexte utilisateur/actif synthétiques | fonctions déterministes |
| Prometheus / Jaeger | Métriques API et traces OTLP, profils optionnels | `/metrics`, OTLP HTTP |

Trois services HTTP sont déployés indépendamment avec `SERVICE_ROLE=core`, `ingestion` et `assistant`. Ils partagent une image et le schéma SQL du laboratoire; il s’agit de microservices à stockage partagé, sans prétendre à une isolation complète des données. La route de chaque service est filtrée au démarrage; chaque requête vérifie le JWT et le rôle dans le service destinataire. Le mode `all` sert aux tests et au développement local.

## Vue logique

```mermaid
flowchart LR
  Analyst[Analyste SOC] -->|REST local| Gateway[Nginx API Gateway]
  Gateway -->|incidents / identité / réponse| API[FastAPI SOC API]
  Gateway -->|events / demo| Ingestion[FastAPI ingestion]
  Gateway -->|assistant / procédures| Assistant[FastAPI assistant]
  Ingestion --> DB
  Ingestion --> Bus
  Assistant --> DB
  Assistant --> AI
  API -->|SQL| DB[(PostgreSQL)]
  API -->|Tâche Celery| Bus[(Redis broker)]
  Bus --> Worker[Celery worker]
  Worker -->|corrélation / réponse simulée| DB
  API --> Offline[Enrichissement hors ligne]
  AI[Provider mock ou compatible OpenAI]
  API --> Files[(Volume de preuves)]
  API --> Metrics[Prometheus /metrics]
  API -. OTLP optionnel .-> Trace[Jaeger]
```

## Flux d’événements

```mermaid
sequenceDiagram
  participant S as Source synthétique
  participant A as API ingestion
  participant P as PostgreSQL
  participant R as Règles et enrichissement
  participant Q as Redis Celery
  participant W as Worker
  participant C as Console SOC
  S->>A: POST /api/events/batch
  A->>A: Validation Pydantic + normalisation
  A->>P: INSERT unique (source, external_id)
  A->>P: COMMIT avant enqueue
  A->>Q: process_event_ids (mode celery)
  A-->>S: accepted / duplicates / queued
  Q->>W: process_event_ids (retries bornés)
  W->>P: Fenêtre temporelle et événements correspondants
  W->>R: Règle active, seuil et sujet
  R->>P: Upsert logique Alert par dedupe_key
  C->>A: GET /api/alerts
  A-->>C: Alerte et contexte enrichi
```

Le mode `ASYNC_MODE=inline` exécute la même corrélation avant la réponse. En mode Celery, les événements sont commités avant l’enqueue pour éviter une course worker. La contrainte unique événement et la `dedupe_key` protègent les rejeux au niveau métier. Le worker acquitte tardivement, limite les reprises à trois, puis dépose les erreurs dans Redis. Une outbox durable et un replay opérateur restent à construire en production.

## Déploiement local

```mermaid
flowchart TB
  Browser[Navigateur 127.0.0.1:8080] --> Gateway[Gateway Nginx]
  subgraph Edge[réseau edge]
    Browser
    Gateway
  end
  subgraph App[réseau application]
    Gateway --> API[API SOC :8000]
    Gateway --> Ingestion[Ingestion :8000]
    Gateway --> Assistant[Assistant :8000]
    Worker[Worker Celery]
    Prom[Prometheus optionnel]
    Jaeger[Jaeger optionnel]
  end
  subgraph Data[réseau données interne]
    API --> PG[(PostgreSQL)]
    Ingestion --> PG
    Ingestion --> Redis
    Assistant --> PG
    API --> Redis[(Redis)]
    Worker --> PG
    Worker --> Redis
  end
  API --> Evidence[(Volume preuves)]
```

Seul le gateway publie un port, lié à la boucle locale. PostgreSQL/Redis ne publient aucun port. Le réseau `data` est interne. Le worker est non-root et utilise la même image applicative.

## Cycle de vie d’un incident

```mermaid
stateDiagram-v2
  [*] --> Triage
  Triage --> Investigation
  Triage --> Cloture
  Investigation --> Contenu
  Investigation --> Resolu
  Investigation --> Cloture
  Contenu --> Investigation
  Contenu --> Resolu
  Contenu --> Cloture
  Resolu --> Cloture
  Resolu --> Investigation: réouverture
  Cloture --> Investigation: réouverture
  state "Qualification" as Triage
  state "Investigation" as Investigation
  state "Contenu" as Contenu
  state "Résolu" as Resolu
  state "Clôturé" as Cloture
```

## Sécurité et observabilité

- JWT HS256 à durée courte; PBKDF2-SHA256 salé; rôles vérifiés à chaque route sensible.
- Entrées Pydantic strictes; lot max 200; preuve max 4 Mio; nom de fichier non utilisé comme chemin; SHA-256 conservé.
- Limiteur par IP en mémoire, utile au labo uniquement, non partagé entre replicas.
- Les mutations sont auditées. Les notifications sont isolées par utilisateur. Les logs structurés excluent les secrets.
- Prometheus scrape `/metrics`. L’instrumentation FastAPI/SQLAlchemy/Celery et l’export OTLP vers Jaeger sont désactivés par défaut.
- L’IA n’a pas d’outil. Journaux et documents sont des données non fiables. Les playbooks sensibles n’ont qu’un résultat simulé.

Avant entreprise : SSO/MFA, Vault/KMS, TLS interne, isolation tenant, RBAC par ressource, limite distribuée, DLQ persistante, antivirus, stockage immuable, rétention/purge, sauvegardes/restauration, alerting SLO, HA, tests de charge/failover et dimensionnement par EPS.

## Comportements vérifiables et limites

- La publication de collecte intervient après le commit du run. Une relivraison Celery ne réexécute pas un run terminé; PostgreSQL verrouille le run pendant l’exécution et l’approbation.
- La corrélation verrouille les règles dans PostgreSQL pour sérialiser les mises à jour concurrentes. Les identifiants de preuves sont conservés dans le contexte. Après clôture, une nouvelle génération ignore les événements de la génération précédente.
- Le scénario HTTP passe par `/api/events/batch`, attend l’alerte puis la collecte, contrôle les refus RBAC, vérifie l’empreinte d’une preuve et exporte le dossier clôturé. Le bouton de démonstration utilise aussi des données synthétiques, avec corrélation immédiate pour l’interactivité.
- Les providers de contexte sont synthétiques. Désactiver une source configurée bloque son ingestion; les sources de laboratoire inconnues restent acceptées pour les scénarios.
- Le corpus de procédures est embarqué et versionné en code. La recherche lexicale fonctionne hors ligne; elle ne constitue pas une recherche vectorielle, et aucune procédure ne déclenche d’outil.
- Les paramètres de règles se règlent dans l’administration. Le limiteur mémoire est propre à chaque processus et peut regrouper des clients derrière un proxy : remplacer par des quotas distribués avant exposition publique.
- L’outbox SQL et le rejeu opérateur des messages morts restent à réaliser avant production. Une interruption entre commit et publication peut perdre un traitement; les contraintes SQL seules ne rendent pas cette fenêtre atomique.
