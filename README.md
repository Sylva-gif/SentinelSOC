# Sentinel SOC Lab

Laboratoire d’apprentissage avancé pour le triage d’alertes et la réponse aux incidents. Les données et actions sont synthétiques par défaut. Aucun playbook ne pilote un EDR, IAM, pare-feu ou service externe.

## Architecture

React 19 + TypeScript + Vite fournit la console SOC; le typage et l’interactivité conviennent mieux à cet outil qu’un frontend Python intégré. FastAPI/Pydantic porte les contrats REST; PostgreSQL conserve événements et incidents; Redis/Celery transporte les tâches; Nginx sert la console et agit comme gateway; Alembic versionne le schéma. SQLite reste disponible pour tests et démarrage simplifié.

La stack sépare trois services HTTP : `api` (identités, incidents, réponse, administration), `ingestion` (événements et scénarios) et `assistant` (analyse et procédures). Nginx route les requêtes vers le service concerné; Celery exécute la corrélation et la collecte en arrière-plan. Ils utilisent une image Python commune et un schéma PostgreSQL partagé pour garder le laboratoire accessible. Ce partage constitue un couplage assumé : les bases par domaine et une outbox durable restent des évolutions avant production. Le mode local `SERVICE_ROLE=all` regroupe les routes pour le développement sans Docker.

Par défaut l’IA est simulée, sans clé ni appel réseau. Le fournisseur compatible OpenAI est facultatif, timeout 12 secondes, sans outil d’action. Journaux et documents sont des données non fiables; les playbooks sensibles restent simulés après approbation humaine.

Documentation : [architecture et diagrammes](docs/architecture.md), [contrats REST/messages](docs/api-contracts.md), [parcours pédagogique](docs/learning-path.md), [rapport de vérification](docs/verification.md).

## Démarrage (Windows / PowerShell)

Prérequis : Docker Desktop avec moteur Linux et Compose v2, 4 cœurs recommandés, 6 Gio RAM disponibles et au moins 6 Gio libres (10 Gio recommandés pour les caches de construction). Seul le gateway écoute sur `127.0.0.1`.

```powershell
Copy-Item .env.example .env
docker compose up --build -d --wait
docker compose ps
Invoke-RestMethod http://localhost:8080/ready
```

Console : [http://localhost:8080](http://localhost:8080). Swagger : [http://localhost:8080/docs](http://localhost:8080/docs).

Comptes locaux (ne jamais réutiliser) : `analyst / DemoAnalyst!2026`, `manager / DemoManager!2026`, `admin / DemoAdmin!2026`.

Scénario HTTP complet, incluant la file Redis/Celery et rapport JSON sous `reports/` : `powershell -File scripts/run-scenario.ps1`.

Commandes de gestion : `powershell -File scripts/dev.ps1 install`, `start`, `test` ou `stop`. La commande `reset` demande la confirmation `RESET`, puis supprime les volumes PostgreSQL, Redis et preuves.

## Observabilité optionnelle

Prometheus et Jaeger ne sont pas requis. Définir `OTEL_ENABLED=true` dans `.env`, puis utiliser `docker compose --profile observability up --build -d`. Interfaces : Prometheus `http://localhost:9090`, Jaeger `http://localhost:16686`; métriques API sur `/metrics` dans Compose.

## Mode développeur sans Docker

Avec Python 3.12 et Node 22, créer un environnement avec `py -3.12 -m venv .venv`, installer `backend/requirements.txt`, puis `npm ci --prefix frontend`. Définir `DATABASE_URL=sqlite:///./sentinel-local.db`, `JWT_SECRET=local-only-change-before-deployment` et lancer `uvicorn app.main:app --app-dir backend --reload --port 8000`. Dans un autre terminal : `npm run dev --prefix frontend`. Vite relaie `/api` vers le backend. Après activation de l’environnement virtuel, tests : `python -m pytest backend/tests -q`.

## Services et limites

Indispensables sous Compose : PostgreSQL, Redis, API SOC, API ingestion, API assistant, worker et gateway. `ASYNC_MODE=celery` est le défaut Compose; `inline` simplifie le débogage. Prometheus, Jaeger et fournisseur IA externe sont facultatifs. L’adaptateur e-mail écrit un log structuré et ne contacte aucun SMTP.

Avant production, remplacer utilisateurs/secrets de démo; ajouter SSO/MFA, KMS/Vault, révocation JWT, quotas distribués, outbox durable, DLQ opérable/rejouable, TLS interne, antivirus et stockage immuable des preuves, rétention/purge, isolation tenant, sauvegardes et restaurations testées, HA, SLO, tests de charge et séparation des stockages par domaine. Ce dépôt est un laboratoire, pas un SOC prêt pour l’entreprise.

## Vérifier et utiliser le laboratoire

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests -q
.\.venv\Scripts\python.exe -m ruff check backend
npm run build --prefix frontend
npm audit --prefix frontend --audit-level=high
python scripts/scenario.py
```

Dans la console : lancer un scénario, créer un incident depuis l’alerte, ajouter une preuve, ajuster la sévérité et l’affectation, puis analyser le dossier. Les citations `RB-*` renvoient aux procédures versionnées de `backend/app/procedures.py`. La collecte passe par le worker; l’isolation et la désactivation de compte attendent un responsable SOC. Les actions sont toujours simulées. La clôture met aussi à jour l’alerte; une nouvelle attaque peut créer une nouvelle alerte après clôture.

Swagger décrit le service SOC sur `/docs`. Les schémas des autres services sont accessibles sur `/ingestion/openapi.json` et `/assistant/openapi.json`. Le contrat complet est documenté dans `docs/api-contracts.md`. En mode développeur, `SERVICE_ROLE=all` expose toutes les routes sur le même Swagger.

Pour Kubernetes : construire d’abord les images avec Compose, les charger dans le registre ou le cluster local, remplacer les valeurs `REPLACE_*`, puis appliquer `k8s/sentinel.yaml`. Le manifeste illustre un déploiement mono-réplique, avec volumes et restriction d’accès aux stockages; il ne configure pas de haute disponibilité. Accès local : `kubectl -n sentinel-soc port-forward svc/gateway 8080:8080`.
