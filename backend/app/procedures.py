"""Versioned offline runbooks. Retrieval never executes document content."""
import re

PROCEDURES = [
    {"id": "RB-AUTH-001", "version": 1, "title": "Échecs d’authentification répétés",
     "keywords": "auth_failure authentification connexion compte brute force triage",
     "steps": ["Vérifier les événements d’échec et leurs horodatages.",
               "Rechercher une connexion réussie du même compte depuis la source observée.",
               "Confirmer la légitimité de l’activité avec le propriétaire du compte.",
               "Demander une validation SOC avant toute mesure de confinement."]},
    {"id": "RB-EVID-001", "version": 1, "title": "Préservation des preuves",
     "keywords": "preuve evidence collecte investigation intégrité journal",
     "steps": ["Exporter les journaux synthétiques pertinents et documenter la provenance.",
               "Téléverser le fichier dans l’incident et conserver son empreinte SHA-256.",
               "Consigner l’auteur, la date et les limites de chaque observation."]},
    {"id": "RB-CLOSE-001", "version": 1, "title": "Clôture d’un incident",
     "keywords": "clôture fermeture closed rapport resolved résolution",
     "steps": ["Documenter les faits établis, les incertitudes et les preuves associées.",
               "Vérifier les résultats des tâches et l’approbation des actions sensibles.",
               "Passer le dossier en résolution puis clôture et exporter le rapport."]},
]


def search_procedures(query: str, limit: int = 3) -> list[dict]:
    terms = set(re.findall(r"[\w]+", query.casefold()))
    ranked = []
    for item in PROCEDURES:
        words = set(re.findall(r"[\w]+", (item["title"] + " " + item["keywords"]).casefold()))
        score = len(terms & words)
        if score:
            ranked.append((score, item))
    ranked.sort(key=lambda pair: (-pair[0], pair[1]["id"]))
    return [{key: value for key, value in item.items() if key != "keywords"} for _, item in ranked[:limit]]
