# Rapport de vérification — 30 septembre 2026

## Implémenté

- Console React/TypeScript : tableau de bord, alertes, incidents, commentaires, preuves, affectation aux comptes actifs, sévérité, assistant, trois playbooks, notifications, utilisateurs, règles et intégrations.
- Services HTTP SOC, ingestion et assistant séparés par `SERVICE_ROLE`, routés par Nginx; worker Celery, PostgreSQL et Redis.
- Validation, normalisation, déduplication, corrélation, enrichissement synthétique, transitions d’incidents, RBAC et audit.
- Assistant simulé hors ligne, procédures versionnées avec citations; fournisseur compatible configurable, sans outil d’action.
- Collecte asynchrone, approbation humaine des actions sensibles, retries bornés, messages en échec et garde contre la relivraison d’une collecte terminée.
- Docker Compose, migrations Alembic, manifests Kubernetes, logs applicatifs JSON, métriques et traces optionnelles, CI et parcours pédagogique.

## Vérifications réellement exécutées

| Vérification | Résultat |
|---|---|
| Tests backend SQLite/FastAPI | 11 tests réussis lors de la dernière suite locale terminée |
| Ruff sur backend | Réussi |
| Compilation TypeScript + Vite | Réussie |
| Audit npm | 0 vulnérabilité signalée |
| Validation Docker Compose | Réussie |
| Construction des images API, ingestion, assistant, worker et gateway | Réussie |
| Démarrage des sept conteneurs essentiels | Tous `running` et `healthy` |
| Migrations et initialisation PostgreSQL | Réussies au démarrage Docker |
| Scénario HTTP via Nginx et services séparés | Réussi : `PASS`, incident 1, `processing=queued` |
| Corrélation Redis/Celery et collecte asynchrone | Observées dans le scénario HTTP |
| Permissions, transition interdite et double approbation | Refus attendus vérifiés dans le scénario |
| Preuve téléversée, empreinte SHA-256 et téléchargement | Concordance vérifiée |
| Clôture, état de l’alerte et export JSON | Vérifiés |
| Manifests Kubernetes | 20 objets YAML chargés; aucun déploiement sur cluster effectué |

Le scénario reproductible est `python scripts/scenario.py`. Il crée uniquement des données synthétiques et vérifie que les actions restent simulées. Les rapports d’incident sont générés sous `reports/` et exclus du dépôt.

## À vérifier ou à compléter avant une utilisation réelle

- Inspection visuelle navigateur ordinateur/mobile : pas encore effectuée dans cette session.
- Audit des dépendances Python : non exécuté; l’installation de l’outil supplémentaire n’a pas été autorisée. La CI contient la commande `pip-audit`; son succès n’est pas garanti.
- CI distante : à consulter après publication GitHub; l’exécution locale ne constitue pas une validation de la CI distante.
- Export réel des traces Jaeger, collecte Prometheus et fournisseur IA externe : non exercés.
- Kubernetes : déploiement, droits du stockage, politiques réseau et comportement sous charge non vérifiés sur cluster.
- Architecture à base partagée, outbox durable absente, DLQ sans console de rejeu, quotas en mémoire et comptes de démonstration : limites explicites de ce laboratoire.
- TLS/SSO/MFA, isolation des données, gestion des secrets, rétention, sauvegarde/restauration et haute disponibilité restent nécessaires avant production.

## Contexte d’exécution

Windows, Python 3.12, Node et Docker Desktop avec conteneurs Linux. Le premier build a rencontré un disque plein. Après retour d’espace disponible, les dépendances, images et tests de bout en bout ont pu être exécutés. Aucune suppression des fichiers personnels de l’utilisateur n’a été effectuée.
