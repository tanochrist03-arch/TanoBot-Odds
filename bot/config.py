"""
TanoBot Odds — configuration.

Toutes les valeurs sensibles viennent d'un fichier `.env` (jamais du code, jamais
de GitHub). Ce module ne les affiche jamais : il ne communique qu'une présence,
un préfixe et une longueur, ce qui suffit à diagnostiquer sans rien divulguer.

Le bot est **verrouillé par identifiant** : sans liste d'identifiants autorisés,
il refuse de démarrer. Un bot Telegram qui répond à n'importe qui expose
l'analyse, l'historique et la base à l'internet entier.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
CHEMIN_ENV = RACINE / ".env"

# Chemin du projet contenant le moteur vérifié (TanoTech Basket Analytics).
PROJET_MOTEUR_DEFAUT = RACINE.parent / "TanoTech-Basket-Analytics"


def _charger_env() -> None:
    """Charge le .env sans écraser une variable déjà définie dans le système."""
    try:
        from dotenv import load_dotenv
    except ImportError:                     # le bot peut tourner sans dotenv
        return
    if CHEMIN_ENV.exists():
        load_dotenv(CHEMIN_ENV, override=False)


def _entier(valeur: str | None, defaut: int) -> int:
    try:
        return int(str(valeur).strip())
    except (TypeError, ValueError):
        return defaut


def _booleen(valeur: str | None, defaut: bool = False) -> bool:
    if valeur is None:
        return defaut
    return str(valeur).strip().lower() in ("1", "true", "vrai", "oui", "yes", "on")


def _liste_entiers(valeur: str | None) -> list[int]:
    if not valeur:
        return []
    identifiants: list[int] = []
    for morceau in str(valeur).replace(";", ",").split(","):
        morceau = morceau.strip()
        if morceau.lstrip("-").isdigit():
            identifiants.append(int(morceau))
    return identifiants


@dataclass
class ConfigurationBot:
    """Réglages du bot, une fois le fichier .env lu."""

    jeton: str = ""
    administrateurs: list[int] = field(default_factory=list)

    supabase_url: str = ""
    supabase_cle: str = ""

    chemin_moteur: Path = PROJET_MOTEUR_DEFAUT

    alertes_actives: bool = False
    heure_scan: str = "07:00"          # heure locale du scan automatique
    fuseau: str = "Africa/Abidjan"
    seuil_ev: float = 0.05             # EV minimum pour publier un value bet
    seuil_confiance: int = 45          # confiance minimum (sur 100)
    max_paris_alerte: int = 5

    # ---------------------------------------------------------------- #
    @property
    def supabase_configure(self) -> bool:
        """Vrai quand les deux identifiants Supabase sont présents."""
        return bool(self.supabase_url and self.supabase_cle)

    @property
    def jeton_configure(self) -> bool:
        return bool(self.jeton)

    def problemes(self) -> list[str]:
        """Liste précise de ce qui empêche le démarrage.

        Chaque message dit **quoi faire**, pas seulement ce qui manque.
        """
        soucis: list[str] = []
        if not self.jeton_configure:
            soucis.append(
                "BOT_TOKEN absent : crée un bot avec @BotFather sur Telegram, "
                "puis mets le jeton dans .env (BOT_TOKEN=...)"
            )
        if not self.administrateurs:
            soucis.append(
                "BOT_ADMIN_IDS absent : mets ton identifiant Telegram numérique "
                "dans .env (BOT_ADMIN_IDS=123456789). Sans lui, le bot refuserait "
                "tout le monde — y compris toi."
            )
        if not self.chemin_moteur.exists():
            soucis.append(
                f"moteur introuvable : {self.chemin_moteur} — indique le bon "
                "chemin dans .env (TANOTECH_PATH=...)"
            )
        return soucis

    # ---------------------------------------------------------------- #
    def resume_securise(self) -> dict:
        """Résumé affichable : aucun secret en clair, seulement sa forme."""
        def empreinte(valeur: str) -> str:
            if not valeur:
                return "absent"
            return f"{valeur[:4]}…{len(valeur)} caractères"

        return {
            "jeton": empreinte(self.jeton),
            "administrateurs": len(self.administrateurs),
            "supabase": "configuré" if self.supabase_configure else "absent (SQLite local)",
            "supabase_url": self.supabase_url or "—",
            "supabase_cle": empreinte(self.supabase_cle),
            "moteur": str(self.chemin_moteur),
            "moteur_present": self.chemin_moteur.exists(),
            "alertes": "activées" if self.alertes_actives else "désactivées",
            "heure_scan": self.heure_scan,
            "seuil_ev": self.seuil_ev,
            "seuil_confiance": self.seuil_confiance,
        }


def charger() -> ConfigurationBot:
    """Lit la configuration depuis l'environnement et le fichier .env."""
    _charger_env()

    chemin_moteur = os.environ.get("TANOTECH_PATH", "").strip()
    configuration = ConfigurationBot(
        jeton=os.environ.get("BOT_TOKEN", "").strip(),
        administrateurs=_liste_entiers(os.environ.get("BOT_ADMIN_IDS")),
        supabase_url=os.environ.get("SUPABASE_URL", "").strip(),
        supabase_cle=os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
                     or os.environ.get("SUPABASE_KEY", "").strip(),
        chemin_moteur=Path(chemin_moteur) if chemin_moteur else PROJET_MOTEUR_DEFAUT,
        alertes_actives=_booleen(os.environ.get("ALERTES_ACTIVES")),
        heure_scan=os.environ.get("HEURE_SCAN", "07:00").strip() or "07:00",
        fuseau=os.environ.get("FUSEAU", "Africa/Abidjan").strip() or "Africa/Abidjan",
        seuil_ev=float(os.environ.get("SEUIL_EV", "0.05") or 0.05),
        seuil_confiance=_entier(os.environ.get("SEUIL_CONFIANCE"), 45),
        max_paris_alerte=_entier(os.environ.get("MAX_PARIS_ALERTE"), 5),
    )
    return configuration
