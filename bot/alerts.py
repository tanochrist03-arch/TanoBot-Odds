"""
TanoBot Odds — alertes automatiques.

Un scan programmé tourne à l'heure choisie et **n'alerte que s'il y a quelque
chose à dire**. Un bot qui envoie « rien de nouveau » chaque matin finit par
être mis en sourdine, et l'alerte qui compte passe inaperçue.

Deux cas méritent une notification :

1. une ou plusieurs opportunités franchissent tous les seuils ;
2. la source de cotes est indisponible **plusieurs fois de suite** — là, c'est
   le système qui a besoin d'attention, pas le marché.

La planification s'appuie sur APScheduler, dont le planificateur asynchrone
partage la boucle d'événements du bot.
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from . import rendu
from .contexte import obtenir

logger = logging.getLogger(__name__)


async def tache_scan(bot, forcer_reseau: bool = False) -> dict:
    """Exécute un scan et notifie le propriétaire si nécessaire."""
    contexte = obtenir()
    rapport = await contexte.lancer_analyse(forcer_reseau=forcer_reseau)

    destinations = contexte.configuration.administrateurs
    if not destinations:
        return rapport

    if not rapport.get("ok"):
        # Un échec isolé peut n'être qu'une lenteur passagère : on le journalise
        # sans déranger. C'est la répétition qui doit alerter.
        contexte._echecs_consecutifs = getattr(contexte, "_echecs_consecutifs", 0) + 1
        logger.warning("scan automatique en échec (%s) — %s consécutif(s)",
                       rapport.get("erreur"), contexte._echecs_consecutifs)
        if contexte._echecs_consecutifs >= 3:
            texte = (
                "<b>⚠️ La source de cotes ne répond plus</b>\n\n"
                f"{rendu._echapper(rapport.get('erreur'))}\n\n"
                f"<i>{contexte._echecs_consecutifs} tentatives consécutives. "
                "Le bot continue de fonctionner sur les données déjà collectées.</i>"
            )
            for destinataire in destinations:
                try:
                    await bot.send_message(destinataire, texte)
                except Exception as exc:
                    logger.error("notification impossible à %s : %s",
                                 destinataire, exc)
            contexte._echecs_consecutifs = 0
        return rapport

    contexte._echecs_consecutifs = 0
    paris = rapport.get("value_bets") or []
    if not paris:
        # Silence volontaire : rien à signaler est une information normale.
        logger.info("scan automatique : aucune opportunité, pas d'alerte")
        return rapport

    maximum = contexte.configuration.max_paris_alerte
    entete = (f"<b>🎯 {len(paris)} opportunité(s) détectée(s)</b>\n"
              f"<i>Scan automatique de {contexte.configuration.heure_scan}</i>\n")
    corps = rendu.value_bets(rapport, None, contexte.configuration, limite=maximum)
    texte = entete + "\n" + corps.split("\n", 1)[-1] if "\n" in corps else entete + corps

    for destinataire in destinations:
        try:
            await bot.send_message(destinataire, texte, disable_web_page_preview=True)
        except Exception as exc:
            logger.error("alerte non envoyée à %s : %s", destinataire, exc)
    return rapport


def construire_planificateur(bot, configuration) -> AsyncIOScheduler | None:
    """Prépare le scan quotidien, ou renvoie None si les alertes sont éteintes."""
    if not configuration.alertes_actives:
        return None
    if not configuration.administrateurs:
        logger.warning("alertes demandées mais aucun administrateur déclaré : "
                       "rien à notifier")
        return None

    try:
        heure, minute = (configuration.heure_scan.split(":") + ["0"])[:2]
        heure, minute = int(heure), int(minute)
    except ValueError:
        logger.error("heure de scan illisible (%s) — repli sur 07:00",
                     configuration.heure_scan)
        heure, minute = 7, 0

    planificateur = AsyncIOScheduler(timezone=configuration.fuseau)
    planificateur.add_job(
        tache_scan,
        trigger="cron",
        hour=heure,
        minute=minute,
        args=[bot],
        id="scan_quotidien",
        replace_existing=True,
        misfire_grace_time=600,      # tolère un réveil tardif de la machine
        coalesce=True,               # un seul rattrapage, pas plusieurs
    )
    logger.info("scan quotidien planifié à %02d:%02d (%s)",
                heure, minute, configuration.fuseau)
    return planificateur
