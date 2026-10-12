"""
TanoBot Odds — stockage Supabase.

Activé automatiquement dès que `SUPABASE_URL` et la clé sont présentes. Le
schéma attendu est dans `sql/001_schema.sql`.

Deux principes :
- **Aucune valeur sensible n'est journalisée.** Les erreurs sont résumées, jamais
  la clé ni l'URL complète.
- **Une table absente est expliquée.** Si le schéma n'a pas été exécuté, le
  message dit précisément quoi faire, au lieu d'une erreur de base illisible.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from .base import Depot, normaliser_pari


class SupabaseDepot(Depot):
    """Stockage distant : historique consultable et interrogeable."""

    nom = "Supabase"

    def __init__(self, url: str, cle: str) -> None:
        from supabase import create_client
        self._client = create_client(url, cle)
        self._table_absente: set[str] = set()

    # ------------------------------------------------------------------ #
    def _inserer(self, table: str, donnees: dict[str, Any]) -> dict | None:
        """Insère une ligne ; renvoie la ligne créée ou None."""
        try:
            reponse = self._client.table(table).insert(donnees).execute()
            lignes = getattr(reponse, "data", None) or []
            return lignes[0] if lignes else None
        except Exception as exc:
            message = str(exc)
            if "does not exist" in message or "42P01" in message:
                self._table_absente.add(table)
                raise RuntimeError(
                    f"la table « {table} » n'existe pas dans Supabase — "
                    "exécute sql/001_schema.sql dans l'éditeur SQL du projet"
                ) from exc
            raise

    # ------------------------------------------------------------------ #
    def enregistrer_scan(self, rapport: dict[str, Any], *,
                         seuil_ev: float, seuil_confiance: int) -> int:
        compteurs = rapport.get("compteurs") or {}
        ligne = self._inserer("scan", {
            "horodatage": rapport.get("horodatage")
                          or datetime.now(timezone.utc).isoformat(),
            "source": str(rapport.get("source") or ""),
            "depuis_cache": bool(rapport.get("depuis_cache")),
            "seuil_ev": float(seuil_ev),
            "seuil_confiance": int(seuil_confiance),
            "matchs_observes": int(compteurs.get("matchs_a_venir")
                                   or compteurs.get("matchs_total") or 0),
            "matchs_evalues": int(compteurs.get("matchs_evalues") or 0),
            "nb_pronostics": len(rapport.get("pronostics") or []),
            "nb_value_bets": len(rapport.get("value_bets") or []),
            "avertissements": rapport.get("avertissements") or [],
            "erreur": rapport.get("erreur") or None,
        })
        return int((ligne or {}).get("id") or 0)

    # ------------------------------------------------------------------ #
    def enregistrer_value_bets(self, paris: list[dict[str, Any]],
                               scan_id: int | None = None) -> int:
        if not paris:
            return 0
        lignes: list[dict[str, Any]] = []
        for pari in paris:
            normalise = normaliser_pari(pari)
            lignes.append({
                "scan_id": scan_id or None,
                "horodatage": datetime.now(timezone.utc).isoformat(),
                "competition": normalise["competition"],
                "match_libelle": normalise["match_libelle"],
                "equipe": normalise["equipe"],
                "marche": normalise["marche"],
                "cote": normalise["cote"],
                "probabilite_modele": normalise["probabilite_modele"],
                "probabilite_marche": normalise["probabilite_marche"],
                "ecart_points": normalise["ecart_points"],
                "ev": normalise["ev"],
                "confiance": normalise["confiance"],
                "mise_recommandee": normalise["mise_recommandee"],
                "statut": "detecte",
                "empreinte": normalise["empreinte"],
            })

        ecrits = 0
        try:
            # `upsert` avec `ignore_duplicates` : un pari déjà présent n'est pas
            # réécrit. L'unicité est aussi garantie par la contrainte SQL, mais
            # on évite ainsi de faire échouer tout le lot pour un doublon.
            reponse = (self._client.table("value_bet")
                       .upsert(lignes, on_conflict="empreinte",
                               ignore_duplicates=True)
                       .execute())
            ecrits = len(getattr(reponse, "data", None) or [])
        except Exception as exc:
            message = str(exc)
            if "does not exist" in message or "42P01" in message:
                raise RuntimeError(
                    "la table « value_bet » n'existe pas dans Supabase — "
                    "exécute sql/001_schema.sql dans l'éditeur SQL du projet"
                ) from exc
            raise
        return ecrits

    # ------------------------------------------------------------------ #
    def value_bets_recents(self, limite: int = 10) -> list[dict[str, Any]]:
        try:
            reponse = (self._client.table("value_bet")
                       .select("*")
                       .order("id", desc=True)
                       .limit(int(limite))
                       .execute())
            return list(getattr(reponse, "data", None) or [])
        except Exception as exc:
            if "does not exist" in str(exc):
                return []
            raise

    # ------------------------------------------------------------------ #
    def statistiques(self) -> dict[str, Any]:
        """Chiffres de synthèse, calculés par la vue `bilan_value_bets`."""
        try:
            reponse = self._client.table("value_bet").select("*").limit(2000).execute()
            lignes = list(getattr(reponse, "data", None) or [])
        except Exception:
            lignes = []

        par_statut: dict[str, int] = {}
        ev_total = 0.0
        confiance_total = 0.0
        confiance_n = 0
        for ligne in lignes:
            statut = str(ligne.get("statut") or "detecte")
            par_statut[statut] = par_statut.get(statut, 0) + 1
            try:
                ev_total += float(ligne.get("ev") or 0)
            except (TypeError, ValueError):
                pass
            try:
                if ligne.get("confiance") is not None:
                    confiance_total += float(ligne["confiance"])
                    confiance_n += 1
            except (TypeError, ValueError):
                pass

        return {
            "total_value_bets": len(lignes),
            "par_statut": par_statut,
            "ev_moyenne": (ev_total / len(lignes)) if lignes else None,
            "confiance_moyenne": (confiance_total / confiance_n) if confiance_n else None,
            "nb_scans": None,          # compté sur la table scan si besoin
            "dernier_scan": None,
            "depot": self.nom,
        }

    # ------------------------------------------------------------------ #
    def mettre_a_jour_statut(self, pari_id: int, statut: str,
                             gain_reel: float | None = None) -> bool:
        """Met à jour le cycle de vie d'un pari (détecté → joué → réglé)."""
        donnees: dict[str, Any] = {"statut": statut}
        if gain_reel is not None:
            donnees["gain_reel"] = float(gain_reel)
        try:
            self._client.table("value_bet").update(donnees).eq("id", pari_id).execute()
            return True
        except Exception:
            return False
