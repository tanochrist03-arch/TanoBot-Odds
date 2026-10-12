"""
TanoBot Odds — contexte partagé.

Un objet unique porte la configuration, le stockage et le dernier rapport
d'analyse. Les gestionnaires de commandes y accèdent au lieu de recréer un
stockage à chaque message — et le verrou empêche deux analyses de tourner en
même temps, ce qui doublerait inutilement les requêtes vers la source.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .config import ConfigurationBot


@dataclass
class Contexte:
    """État partagé du bot."""

    configuration: ConfigurationBot
    depot: Any = None
    dernier_rapport: dict[str, Any] | None = None
    dernier_scan_le: str | None = None
    verrou: asyncio.Lock = field(default_factory=asyncio.Lock)

    # ------------------------------------------------------------------ #
    async def lancer_analyse(self, *, forcer_reseau: bool = False) -> dict:
        """Exécute l'analyse en série, puis enregistre le résultat.

        Le verrou garantit qu'une seule analyse tourne à la fois : deux scans
        simultanés solliciteraient deux fois la source, qui limite déjà le débit.
        """
        from . import engine_bridge as pont

        async with self.verrou:
            rapport = await asyncio.to_thread(
                pont.analyser, self._configuration_moteur(), forcer_reseau=forcer_reseau
            )
            self.dernier_rapport = rapport
            self.dernier_scan_le = datetime.now(timezone.utc).isoformat()

            if rapport.get("ok") and self.depot is not None:
                try:
                    scan_id = await asyncio.to_thread(
                        self.depot.enregistrer_scan, rapport,
                        seuil_ev=self.configuration.seuil_ev,
                        seuil_confiance=self.configuration.seuil_confiance,
                    )
                    ecrits = await asyncio.to_thread(
                        self.depot.enregistrer_value_bets,
                        rapport.get("value_bets") or [], scan_id,
                    )
                    rapport["_scan_id"] = scan_id
                    rapport["_value_bets_ecrits"] = ecrits
                except Exception as exc:
                    # L'échec d'écriture ne doit pas priver l'utilisateur de
                    # l'analyse : on le signale dans le rapport.
                    rapport.setdefault("avertissements", []).append(
                        f"enregistrement impossible : {type(exc).__name__} — {exc}")
            return rapport

    # ------------------------------------------------------------------ #
    def _configuration_moteur(self):
        """Configuration du moteur, ajustée sur les seuils du bot."""
        from . import engine_bridge as pont
        configuration = pont.charger_moteur()
        configuration.seuil_ev = self.configuration.seuil_ev
        configuration.confiance_minimum = float(self.configuration.seuil_confiance)
        return configuration


# Instance unique, remplie au démarrage par `main.py`.
CONTEXTE: Contexte | None = None


def installer(contexte: Contexte) -> None:
    global CONTEXTE
    CONTEXTE = contexte


def obtenir() -> Contexte:
    if CONTEXTE is None:
        raise RuntimeError("contexte non initialisé")
    return CONTEXTE
