"""
TanoBot Odds — pont vers le moteur d'analyse vérifié.

Principe de conception
----------------------
Le bot **ne réimplémente aucun calcul**. Le moteur EV/Kelly, la collecte des
cotes, la construction des profils d'équipes et le formatage des messages
existent déjà dans le projet *TanoTech Basket Analytics*, où ils sont couverts
par des tests.

Recopier ce moteur aurait deux conséquences, toutes deux mauvaises :

1. **Divergence silencieuse** — une correction appliquée d'un côté ne l'est pas
   de l'autre, et le bot se met à publier des chiffres que le site ne reconnaît
   plus.
2. **Retour des défauts corrigés** — le moteur naïf annonçait 36 value bets à
   +495 % d'EV, puis +15,6 % d'EV imaginaire (marge du bookmaker comptée comme
   avantage). Ces défauts ont été mesurés puis corrigés ; les réintroduire
   coûterait une session entière.

Ce module importe donc le moteur existant tel quel. Si le projet n'est pas
trouvable, il le dit clairement au lieu de lever une erreur d'import obscure.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Résultat de la tentative de chargement, rempli une seule fois.
_ETAT: dict = {
    "ok": False,
    "chemin": "",
    "manquants": [],
    "erreur": "",
    "modules": {},
}

# Éléments exposés par le moteur, chargés dynamiquement.
analyser = None
charger_moteur = None
formater_pari = None
formater_paris = None
formater_recapitulatif = None
expected_value = None
fraction_kelly = None
etat_sources = None
aplatir_pronostic = None


def _charger(chemin_moteur: Path) -> dict:
    """Ajoute le projet moteur au chemin d'import et charge ses modules."""
    global analyser, charger_moteur, formater_pari, formater_paris
    global formater_recapitulatif, expected_value, fraction_kelly, etat_sources
    global aplatir_pronostic

    chemin = Path(chemin_moteur)
    # Réinitialisation : sans cela, un chargement réussi précédent laisserait
    # `ok` à True et masquerait un chemin invalide.
    _ETAT.update({"ok": False, "manquants": [], "erreur": "", "modules": {},
                  "chemin": str(chemin)})

    if not chemin.exists():
        _ETAT["erreur"] = (
            f"projet moteur introuvable : {chemin}. "
            "Indique son emplacement dans .env (TANOTECH_PATH=...)."
        )
        return _ETAT

    # Ajout en fin de liste : les modules du bot restent prioritaires, et rien
    # du moteur ne peut masquer un module du bot.
    if str(chemin) not in sys.path:
        sys.path.append(str(chemin))

    importances = (
        ("math_models", "engine.math_models",
         ("expected_value", "fraction_kelly", "Marche", "construire_profils")),
        ("analysis", "services.analysis",
         ("analyser", "etat_sources", "_pari_pour_publication")),
        ("telegram_formatter", "services.telegram_formatter",
         ("formater_pari", "formater_paris", "formater_recapitulatif")),
        ("config_moteur", "config", ("charger",)),
    )

    for etiquette, nom_module, attendus in importances:
        try:
            module = __import__(nom_module, fromlist=list(attendus))
        except Exception as exc:                       # module absent ou cassé
            _ETAT["manquants"].append(f"{etiquette} ({type(exc).__name__}: {exc})")
            continue
        absents = [n for n in attendus if not hasattr(module, n)]
        if absents:
            _ETAT["manquants"].append(f"{etiquette} → {', '.join(absents)}")
            continue
        _ETAT["modules"][etiquette] = True

        if etiquette == "math_models":
            expected_value = module.expected_value
            fraction_kelly = module.fraction_kelly
        elif etiquette == "analysis":
            analyser = module.analyser
            etat_sources = module.etat_sources
            aplatir_pronostic = module._pari_pour_publication
        elif etiquette == "telegram_formatter":
            formater_pari = module.formater_pari
            formater_paris = module.formater_paris
            formater_recapitulatif = module.formater_recapitulatif
        elif etiquette == "config_moteur":
            charger_moteur = module.charger

    _ETAT["ok"] = not _ETAT["manquants"]
    if not _ETAT["ok"]:
        _ETAT["erreur"] = ("moteur incomplet — éléments introuvables : "
                           + " ; ".join(_ETAT["manquants"]))
    return _ETAT


def initialiser(chemin_moteur: Path) -> dict:
    """Charge le moteur (idempotent) et renvoie son état."""
    if _ETAT["ok"]:
        return _ETAT
    return _charger(chemin_moteur)


def etat() -> dict:
    """État du chargement, pour le diagnostic et la commande /sante."""
    return dict(_ETAT)


def exiger() -> None:
    """Lève une erreur explicite si le moteur n'est pas disponible."""
    if not _ETAT["ok"]:
        raise RuntimeError(_ETAT.get("erreur") or "moteur non chargé")


# --------------------------------------------------------------------------- #
# Calculs de confort, adossés au moteur (aucune formule réécrite ici)
# --------------------------------------------------------------------------- #
def ev_pourcentage(probabilite: float, cote: float) -> float:
    """Expected Value en pourcentage : EV = (probabilité × cote) − 1.

    Le calcul est délégué au moteur ; cette fonction ne fait que le mettre en
    forme pour l'affichage.
    """
    exiger()
    return expected_value(probabilite, cote) * 100.0


def marge_marche(cotes: dict) -> float | None:
    """Marge du marché sur un match à deux issues, en pourcentage.

    Sert à rappeler dans l'interface que les cotes affichées contiennent la
    marge du bookmaker — ce n'est pas un avantage.
    """
    exiger()
    from engine.math_models import Marche
    try:
        marche = Marche(
            cote_domicile=float(cotes["domicile"]),
            cote_exterieur=float(cotes["exterieur"]),
            cote_domicile_max=float(cotes.get("cote_domicile_max") or 0),
            cote_exterieur_max=float(cotes.get("cote_exterieur_max") or 0),
        )
    except Exception:
        return None
    if not marche.valide:
        return None
    try:
        return marche.marge() * 100.0
    except Exception:
        return None
