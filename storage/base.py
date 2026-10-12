"""
TanoBot Odds — socle de stockage.

Le bot doit pouvoir tourner **immédiatement**, même sans Supabase : c'est ce qui
permet de le tester avant d'avoir branché quoi que ce soit. Deux implémentations
partagent donc la même interface :

- `SupabaseDepot`  : utilisé dès que `SUPABASE_URL` et la clé sont fournies ;
- `SqliteDepot`    : utilisé sinon, dans un fichier local.

Le choix est automatique et **affiché au démarrage** : on ne doit jamais se
demander où les données ont été écrites.
"""
from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from typing import Any


def normaliser_pari(pari: dict[str, Any]) -> dict[str, Any]:
    """Traduit un pari du moteur vers les noms de colonnes du stockage.

    Le moteur nomme certains champs autrement que la base (`ligue`/`competition`,
    `ecart`/`ecart_points`, `issue`/`marche`). Centraliser la traduction ici évite
    qu'un des deux stockages diverge de l'autre sur un nom de champ — c'est
    exactement le genre d'écart qui produit une colonne vide et une analyse
    silencieusement fausse.
    """
    return {
        "match_libelle": str(pari.get("match") or pari.get("match_libelle") or "").strip(),
        "competition": str(pari.get("competition") or pari.get("ligue") or "").strip(),
        "equipe": str(pari.get("equipe") or pari.get("selection") or "").strip(),
        "marche": str(pari.get("marche") or pari.get("issue") or "vainqueur").strip(),
        "cote": float(pari.get("cote") or 0),
        "probabilite_modele": float(
            pari.get("probabilite") or pari.get("probabilite_modele") or 0),
        "probabilite_marche": pari.get("probabilite_marche"),
        "ecart_points": pari.get("ecart_points", pari.get("ecart")),
        "ev": float(pari.get("ev") or 0),
        "confiance": pari.get("confiance"),
        "mise_recommandee": pari.get("mise", pari.get("mise_recommandee")),
        "debut_utc": pari.get("debut_utc"),
        "devise": pari.get("devise"),
        "drapeaux": pari.get("drapeaux") or [],
        "empreinte": empreinte_pari(pari),
    }


def empreinte_pari(pari: dict[str, Any]) -> str:
    """Empreinte stable d'un pari, pour ne jamais l'enregistrer deux fois.

    Elle porte sur le match, le marché et l'équipe — **pas** sur l'EV ou la cote,
    qui varient d'un scan à l'autre pour un même pari. Un value bet redétecté
    le lendemain doit être reconnu comme le même, pas dupliqué.
    """
    morceaux = [
        str(pari.get("match") or pari.get("match_libelle") or "").strip().lower(),
        str(pari.get("marche") or pari.get("issue") or "vainqueur").strip().lower(),
        str(pari.get("equipe") or pari.get("selection") or "").strip().lower(),
    ]
    brut = "|".join(morceaux)
    return hashlib.sha256(brut.encode("utf-8")).hexdigest()[:32]


class Depot(ABC):
    """Interface commune aux deux modes de stockage."""

    nom = "mémoire"

    @abstractmethod
    def enregistrer_scan(self, rapport: dict[str, Any], *,
                         seuil_ev: float, seuil_confiance: int) -> int:
        """Enregistre une exécution et renvoie son identifiant."""

    @abstractmethod
    def enregistrer_value_bets(self, paris: list[dict[str, Any]],
                               scan_id: int | None = None) -> int:
        """Enregistre les paris détectés ; renvoie le nombre réellement écrits."""

    @abstractmethod
    def value_bets_recents(self, limite: int = 10) -> list[dict[str, Any]]:
        """Les derniers paris détectés, du plus récent au plus ancien."""

    @abstractmethod
    def statistiques(self) -> dict[str, Any]:
        """Chiffres de synthèse pour la commande /stats."""

    def fermer(self) -> None:                  # pragma: no cover - défaut vide
        """Libère les ressources si nécessaire."""

    def decrire(self) -> str:
        return self.nom


def construire_depot(configuration) -> Depot:
    """Choisit le stockage : Supabase si configuré, SQLite sinon.

    Le repli sur SQLite est volontaire : il permet de lancer le bot et de
    vérifier son comportement sans dépendre d'un service externe.
    """
    if configuration.supabase_configure:
        try:
            from .supabase_store import SupabaseDepot
            return SupabaseDepot(configuration.supabase_url, configuration.supabase_cle)
        except Exception as exc:
            # On ne masque pas l'échec : on le signale et on continue en local,
            # sinon le bot serait inutilisable pour une panne réseau passagère.
            print(f"  [!] Supabase indisponible ({type(exc).__name__}: {exc}) "
                  f"— repli sur le stockage local")
    from .sqlite_store import SqliteDepot
    return SqliteDepot()
