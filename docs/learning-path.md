# Parcours pratique avancé

Le fil rouge est une attaque de force brute synthétique depuis l’adresse de documentation `203.0.113.42` contre `jules` sur `prod-api-01`. Aucune source externe réelle n’est appelée.

## Étape 1 — Contrats et modèle de menace

**Objectif et notions.** Poser les frontières, identifier les données non fiables, distinguer un module métier d’un microservice indépendant et appliquer le moindre privilège.

**Fichiers.** `docs/architecture.md`, `docs/api-contracts.md`, `.env.example`, `docker-compose.yml`. Les API SOC, ingestion et assistant sont indépendantes, avec un worker et un schéma partagé.

**Commandes.** Copier `.env.example` vers `.env`; `docker compose config --quiet`; ouvrir `/docs` après démarrage.

**Attendu et vérification.** Le gateway est seul publié sur `127.0.0.1`; les réseaux de données n’exposent pas leurs ports. Les diagrammes décrivent les services Compose.

**Approfondissement.** Écrire un modèle STRIDE pour ingestion, preuve, jeton et playbook.

**Prompt agent.** « À partir de `docs/architecture.md` et `docker-compose.yml`, fais une revue STRIDE des frontières réseau. Donne les risques concrets avec composant, scénario, impact et mitigation; ne modifie pas le code. »

## Étape 2 — Identité, authentification et RBAC

**Objectif et notions.** Comprendre PBKDF2 salé, JWT, expiration, dépendances FastAPI et autorisation par route.

**Fichiers.** `backend/app/security.py`, `backend/app/routes.py`, `backend/app/models.py`. Les réponses utilisateur ne révèlent jamais le hash.

**Commandes.** `Invoke-RestMethod http://localhost:8080/ready`; ouvrir Swagger; lire `backend/tests/test_soc_flow.py`.

**Attendu et vérification.** Une requête anonyme reçoit 401; un analyste reçoit 403 sur les règles; seul le responsable SOC peut approuver un playbook sensible.

**Approfondissement.** Ajouter révocation JWT ou MFA par WebAuthn sans secret en clair.

**Prompt agent.** « Examine `security.py` et les routes protégées. Construis une matrice rôle-route, repère les IDOR ou décisions manquantes, puis propose des tests négatifs sans inventer d’endpoint. »

## Étape 3 — Ingestion et idempotence

**Objectif et notions.** Normaliser les événements, borner les charges, rejeter les clés inconnues, distinguer idempotence transport et métier.

**Fichiers.** `backend/app/schemas.py`, `backend/app/routes.py`, modèle `SecurityEvent`, `backend/tests/test_soc_flow.py`.

**Commandes.** `docker compose run --rm api pytest -q`; rejouer le même lot dans Swagger.

**Attendu et vérification.** Le scénario accepte trois événements; le rejeu incrémente les doublons sans ajouter de ligne. Un champ imprévu reçoit 422.

**Approfondissement.** Ajouter une clé d’idempotence au lot et tester deux requêtes concurrentes contre la contrainte unique.

**Prompt agent.** « Lis les schémas et la route d’ingestion. Identifie les courses concurrentes et limites de taille absentes; écris un test reproductible sans réduire les validations. »

## Étape 4 — Détection et enrichissement

**Objectif et notions.** Construire une fenêtre temporelle, une clé de regroupement stable et un provider hors ligne; traiter faux positifs et incertitude.

**Fichiers.** `backend/app/detection.py`, `backend/app/enrichment.py`, modèles `DetectionRule` et `Alert`.

**Commandes.** Cliquer « Lancer le scénario » sur le tableau de bord; consulter `GET /api/alerts`.

**Attendu et vérification.** `auth-failure-burst` crée une alerte high après trois échecs; chaque enrichissement simulé est marqué.

**Approfondissement.** Comparer une clé par IP à une clé par `(IP, user)` et mesurer le bruit.

**Prompt agent.** « Analyse `detection.py` comme une revue SOC : fenêtre, clé, coût requête, doublons, horloge et faux positifs. Propose des tests reproductibles en SQLite. »

## Étape 5 — Incident, timeline et preuves

**Objectif et notions.** Convertir une alerte, affecter, faire évoluer un état contrôlé, documenter et préserver l’intégrité d’une preuve.

**Fichiers.** `Incident`, `IncidentEntry`, `backend/app/routes.py`, `frontend/src/App.tsx`.

**Commandes.** Depuis la console, créer l’incident, changer le statut, ajouter une note et téléverser un fichier texte d’essai.

**Attendu et vérification.** Le journal consigne les étapes; le fichier porte SHA-256 et nom aléatoire. Une transition impossible retourne 409.

**Approfondissement.** Ajouter un stockage objet immuable et vérifier l’empreinte à la lecture.

**Prompt agent.** « Passe en revue l’upload pour traversal, gros fichier, fuite entre utilisateurs et incohérence disque/base. Propose une stratégie transactionnelle et les tests prioritaires. »

## Étape 6 — Assistant résistant aux injections

**Objectif et notions.** Séparer consignes et faits non fiables, citer la provenance, borner délai et sortie du fournisseur.

**Fichiers.** `backend/app/assistant.py`, `.env.example`, `frontend/src/App.tsx`.

**Commandes.** Interroger l’assistant sur un incident en conservant `AI_PROVIDER=mock`.

**Attendu et vérification.** Le mock cite des champs structurés, n’a aucun outil d’action, et un message hostile ne remplace pas les instructions système.

**Approfondissement.** Étendre le corpus de `backend/app/procedures.py` et comparer recherche lexicale et recherche vectorielle avec citations.

**Prompt agent.** « Menace le flux contre l’injection indirecte depuis event.message, commentaire et document. Vérifie qu’aucun contenu ne peut déclencher un outil ou approuver un playbook; propose tests rouges/verts. »

## Étape 7 — Worker, reprise et action contrôlée

**Objectif et notions.** Comprendre livraison au moins une fois, idempotence, commit avant enqueue, retry borné et DLQ.

**Fichiers.** `backend/app/worker.py`, `backend/app/routes.py`, `docker-compose.yml`, Redis.

**Commandes.** Examiner `docker compose logs -f worker`; demander `collect_evidence`; demander `isolate_host`; approuver avec le compte `manager`.

**Attendu et vérification.** Le worker corrèle les événements. `isolate_host` attend un manager. Après approbation, le résultat dit explicitement `performed: false`.

**Approfondissement.** Construire une outbox SQL et un replay DLQ protégé par rôle et audit.

**Prompt agent.** « Examine l’ordre commit/enqueue et les retries dans `routes.py`/`worker.py`. Décris fenêtres de perte/doublon et propose une outbox. Distingue code présent et proposition. »

## Étape 8 — Observabilité, CI et déploiement

**Objectif et notions.** Séparer liveness/readiness, métriques/traces/logs, scanner dépendances, considérer limites des manifests.

**Fichiers.** `.github/workflows/ci.yml`, `observability/prometheus.yml`, `backend/app/telemetry.py`, `k8s/`, `scripts/dev.ps1`.

**Commandes.** `docker compose config --quiet`; `npm audit --prefix frontend`; profil Compose observabilité; `kubectl apply -f k8s/` uniquement sur cluster de test.

**Attendu et vérification.** CI lance Ruff, pytest, pip-audit, build TS, npm audit et build d’images. Prometheus scrape l’API; OTLP reste optionnel.

**Approfondissement.** Définir SLO ingestion, générer une charge synthétique et écrire un exercice de restauration PostgreSQL.

**Prompt agent.** « Compare manifests Kubernetes et Compose. Repère secrets d’exemple, stockage, probes et migrations concurrentes; liste les adaptations nécessaires avant multi-réplicas. »

## Exécution complète

`scripts/run-scenario.ps1` enchaîne : login analyste → trois événements synthétiques → ingestion/corrélation/enrichissement → incident → investigation → analyse mock → collecte simulée → demande d’isolation → approbation manager → commentaire de rapport → containment → résolution → clôture → export JSON sous `reports/`. Aucune personne réelle ni source extérieure n’est utilisée.

## Étape 9 — Vérifier les services ensemble

**Objectif.** Distinguer un test en mémoire d’un parcours traversant Nginx, PostgreSQL, Redis et Celery.

**Fichiers.** `scripts/scenario.py`, `backend/tests/test_regressions.py`, `docs/verification.md`.

**Commandes.** `docker compose up --build -d --wait`; `python scripts/scenario.py`; `docker compose ps`; `docker compose logs --tail 30 worker`.

**Attendu.** Le script affiche `PASS`, avec `processing=queued`, une collecte terminée et un rapport JSON. Il échoue si le worker ne corrèle pas les événements, si un analyste peut approuver une action sensible ou si la preuve téléchargée diffère du fichier envoyé.

**Approfondissement.** Arrêter le worker, ingérer un lot, redémarrer le worker et observer le retard de traitement. Concevoir ensuite une outbox pour la fenêtre commit-publication.

**Prompt agent.** « Exécute le scénario HTTP sur un laboratoire local, identifie le rôle de chaque processus à partir des logs et du rapport; ne confonds pas les tests SQLite avec les validations PostgreSQL et Celery. »
