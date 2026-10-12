"""
TanoBot Odds — commandes Telegram.

Le routeur est protégé par un filtre d'autorisation : seuls les identifiants
listés dans `BOT_ADMIN_IDS` sont servis. Un bot d'analyse laissé ouvert
exposerait l'historique, la méthode et la base à n'importe qui.

Chaque commande est protégée contre ses propres pannes : une exception dans un
gestionnaire ne doit jamais laisser l'utilisateur sans réponse.
"""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import BaseFilter, Command
from aiogram.types import CallbackQuery, Message

from . import engine_bridge as pont
from . import keyboards, rendu
from .contexte import obtenir

logger = logging.getLogger(__name__)
routeur = Router(name="tanobot")


class EstAutorise(BaseFilter):
    """N'accepte que les identifiants déclarés dans la configuration."""

    async def __call__(self, evenement) -> bool:
        utilisateur = getattr(evenement, "from_user", None)
        if utilisateur is None:
            return False
        autorises = obtenir().configuration.administrateurs
        if utilisateur.id in autorises:
            return True
        # On journalise le refus sans jamais répondre : inutile d'indiquer à un
        # inconnu que le bot existe et fonctionne.
        logger.warning("accès refusé à l'identifiant %s", utilisateur.id)
        return False


# Le filtre s'applique à tout le routeur : aucune commande n'y échappe.
routeur.message.filter(EstAutorise())
routeur.callback_query.filter(EstAutorise())


async def _repondre(message: Message, texte: str, clavier=None) -> None:
    """Envoie un message en absorbant les erreurs de formatage Telegram."""
    try:
        await message.answer(texte, reply_markup=clavier,
                             disable_web_page_preview=True)
    except Exception as exc:
        # Le HTML peut être refusé si un caractère a échappé à l'échappement.
        # On renvoie alors le texte brut plutôt que rien du tout.
        logger.error("envoi impossible (%s) — repli en texte brut", exc)
        brut = texte.replace("<b>", "").replace("</b>", "") \
                    .replace("<i>", "").replace("</i>", "") \
                    .replace("<code>", "").replace("</code>", "")
        await message.answer(brut[:4000])


# --------------------------------------------------------------------------- #
# Démarrage et aide
# --------------------------------------------------------------------------- #
@routeur.message(Command("start"))
async def commande_start(message: Message) -> None:
    contexte = obtenir()
    await _repondre(message, rendu.demarrage(contexte.configuration),
                    keyboards.menu_principal())


@routeur.message(Command("aide", "help"))
async def commande_aide(message: Message) -> None:
    await _repondre(message, rendu.aide(), keyboards.menu_principal())


# --------------------------------------------------------------------------- #
# Analyse
# --------------------------------------------------------------------------- #
@routeur.message(Command("scan"))
async def commande_scan(message: Message) -> None:
    contexte = obtenir()
    attente = await message.answer("⏳ Collecte des cotes et analyse en cours…")
    try:
        rapport = await contexte.lancer_analyse()
        await attente.edit_text(rendu.scan(rapport, contexte.configuration),
                                reply_markup=keyboards.apres_scan())
    except Exception as exc:
        logger.exception("échec de l'analyse")
        await attente.edit_text(
            f"<b>Analyse interrompue</b>\n\n<i>{type(exc).__name__}: {exc}</i>")


@routeur.message(Command("matches", "matchs"))
async def commande_matchs(message: Message) -> None:
    contexte = obtenir()
    rapport = contexte.dernier_rapport
    if rapport is None and contexte.depot is not None:
        rapport = {"ok": False}
    await _repondre(message, rendu.matchs(rapport or {}, limite=8), keyboards.retour())


@routeur.message(Command("valuebets", "paris"))
async def commande_valuebets(message: Message) -> None:
    contexte = obtenir()
    recents = []
    if contexte.depot is not None:
        try:
            recents = contexte.depot.value_bets_recents(5)
        except Exception:
            recents = []
    await _repondre(
        message,
        rendu.value_bets(contexte.dernier_rapport or {}, recents,
                         contexte.configuration, limite=5),
        keyboards.retour(),
    )


@routeur.message(Command("stats"))
async def commande_stats(message: Message) -> None:
    contexte = obtenir()
    await _repondre(message, rendu.stats(contexte.depot, contexte.configuration),
                    keyboards.retour())


@routeur.message(Command("sante", "etat"))
async def commande_sante(message: Message) -> None:
    contexte = obtenir()
    etat = pont.initialiser(contexte.configuration.chemin_moteur)
    await _repondre(message, rendu.sante(contexte.configuration, contexte.depot, etat),
                    keyboards.retour())


# --------------------------------------------------------------------------- #
# Boutons
# --------------------------------------------------------------------------- #
@routeur.callback_query(F.data == "action:menu")
async def bouton_menu(callback: CallbackQuery) -> None:
    await callback.message.edit_text(rendu.demarrage(obtenir().configuration),
                                     reply_markup=keyboards.menu_principal())
    await callback.answer()


@routeur.callback_query(F.data == "action:scan")
async def bouton_scan(callback: CallbackQuery) -> None:
    await callback.answer("Analyse lancée…")
    await callback.message.edit_text("⏳ Collecte des cotes et analyse en cours…")
    contexte = obtenir()
    try:
        rapport = await contexte.lancer_analyse()
        await callback.message.edit_text(rendu.scan(rapport, contexte.configuration),
                                         reply_markup=keyboards.apres_scan())
    except Exception as exc:
        logger.exception("échec de l'analyse (bouton)")
        await callback.message.edit_text(
            f"<b>Analyse interrompue</b>\n\n<i>{type(exc).__name__}: {exc}</i>")


@routeur.callback_query(F.data == "action:valuebets")
async def bouton_valuebets(callback: CallbackQuery) -> None:
    contexte = obtenir()
    recents = []
    try:
        recents = contexte.depot.value_bets_recents(5) if contexte.depot else []
    except Exception:
        recents = []
    await callback.message.edit_text(
        rendu.value_bets(contexte.dernier_rapport or {}, recents,
                         contexte.configuration, limite=5),
        reply_markup=keyboards.retour(),
    )
    await callback.answer()


@routeur.callback_query(F.data == "action:matches")
async def bouton_matchs(callback: CallbackQuery) -> None:
    contexte = obtenir()
    await callback.message.edit_text(
        rendu.matchs(contexte.dernier_rapport or {}, limite=8),
        reply_markup=keyboards.retour(),
    )
    await callback.answer()


@routeur.callback_query(F.data == "action:stats")
async def bouton_stats(callback: CallbackQuery) -> None:
    contexte = obtenir()
    await callback.message.edit_text(rendu.stats(contexte.depot, contexte.configuration),
                                     reply_markup=keyboards.retour())
    await callback.answer()


@routeur.callback_query(F.data == "action:sante")
async def bouton_sante(callback: CallbackQuery) -> None:
    contexte = obtenir()
    etat = pont.initialiser(contexte.configuration.chemin_moteur)
    await callback.message.edit_text(
        rendu.sante(contexte.configuration, contexte.depot, etat),
        reply_markup=keyboards.retour(),
    )
    await callback.answer()


# --------------------------------------------------------------------------- #
# Message non reconnu
# --------------------------------------------------------------------------- #
@routeur.message()
async def message_inconnu(message: Message) -> None:
    await _repondre(
        message,
        "Je ne comprends que les commandes. Utilise /aide pour les voir, ou "
        "les boutons ci-dessous.",
        keyboards.menu_principal(),
    )
