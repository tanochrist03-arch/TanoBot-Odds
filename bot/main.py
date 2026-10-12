"""
TanoBot Odds — point d'entrée.

    python -m bot.main               # démarre le bot
    python -m bot.main --verifier    # contrôle tout et s'arrête

Au démarrage, le bot dit **ce qu'il a trouvé** (moteur, stockage, alertes) et
**ce qui manque**, au lieu d'échouer sur une erreur d'import obscure. C'est la
différence entre « ça ne marche pas » et « il manque le jeton : voici où le
mettre ».
"""
from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from . import alerts, engine_bridge as pont
from .config import charger
from .contexte import Contexte, installer
from .handlers import routeur
from storage import construire_depot

logger = logging.getLogger("tanobot")


def configurer_journaux() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s  %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )
    # Les journaux d'HTTPX sont très bavards et masquent l'essentiel.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def afficher_etat(configuration, depot, etat_moteur) -> None:
    """Bandeau de démarrage : aucun secret, seulement leur présence."""
    print("=" * 70)
    print("  TanoBot Odds — détection de value bets")
    print("=" * 70)
    resume = configuration.resume_securise()
    for cle, valeur in resume.items():
        print(f"  {cle:<20} {valeur}")
    print()
    moteur = "OK" if etat_moteur.get("ok") else "INDISPONIBLE"
    print(f"  moteur               {moteur}")
    if not etat_moteur.get("ok"):
        print(f"    → {etat_moteur.get('erreur')}")
    else:
        print(f"    → modules : {', '.join(etat_moteur.get('modules', {}))}")
    print(f"  stockage             {depot.decrire()}")
    print("=" * 70)


async def principal(verifier_seulement: bool = False) -> int:
    configurer_journaux()
    configuration = charger()

    # --- contrôle des prérequis ------------------------------------------- #
    problemes = configuration.problemes()
    etat_moteur = pont.initialiser(configuration.chemin_moteur)
    depot = construire_depot(configuration)
    afficher_etat(configuration, depot, etat_moteur)

    if problemes:
        print("\n  Le bot ne peut pas démarrer. À corriger :\n")
        for probleme in problemes:
            print(f"    • {probleme}")
        print("\n  Copie .env.example en .env et remplis les valeurs manquantes.")
        return 1

    if not etat_moteur.get("ok"):
        print("\n  Le moteur d'analyse est introuvable : aucun calcul n'est "
              "possible.")
        return 2

    contexte = Contexte(configuration=configuration, depot=depot)
    installer(contexte)

    if verifier_seulement:
        print("\n  Vérification terminée : le bot est prêt à démarrer.")
        print("  Lance-le sans --verifier pour le mettre en service.")
        return 0

    # --- bot Telegram ------------------------------------------------------ #
    bot = Bot(configuration.jeton,
              default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dispatcher = Dispatcher()
    dispatcher.include_router(routeur)

    planificateur = alerts.construire_planificateur(bot, configuration)
    if planificateur:
        planificateur.start()

    try:
        moi = await bot.get_me()
        print(f"\n  Bot connecté : @{moi.username}")
        print(f"  Propriétaire(s) autorisé(s) : {configuration.administrateurs}")
        print("  En écoute… (Ctrl+C pour arrêter)\n")
        await dispatcher.start_polling(bot, allowed_updates=dispatcher.resolve_used_update_types())
    finally:
        if planificateur:
            planificateur.shutdown(wait=False)
        await bot.session.close()
        if depot is not None:
            depot.fermer()
    return 0


def main() -> int:
    verifier = "--verifier" in sys.argv
    try:
        return asyncio.run(principal(verifier_seulement=verifier))
    except KeyboardInterrupt:
        print("\n  Arrêt demandé.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
