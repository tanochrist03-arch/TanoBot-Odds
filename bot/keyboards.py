"""
TanoBot Odds — claviers interactifs.

Les boutons reprennent les commandes : personne ne doit avoir à retenir une
syntaxe pour utiliser le bot.
"""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def menu_principal() -> InlineKeyboardMarkup:
    """Menu affiché au démarrage."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔄 Lancer une analyse", callback_data="action:scan"),
        ],
        [
            InlineKeyboardButton(text="🎯 Value bets", callback_data="action:valuebets"),
            InlineKeyboardButton(text="🏀 Matchs", callback_data="action:matches"),
        ],
        [
            InlineKeyboardButton(text="📈 Bilan", callback_data="action:stats"),
            InlineKeyboardButton(text="🩺 État", callback_data="action:sante"),
        ],
    ])


def apres_scan() -> InlineKeyboardMarkup:
    """Actions proposées juste après une analyse."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎯 Voir les value bets",
                                 callback_data="action:valuebets"),
            InlineKeyboardButton(text="🏀 Voir les matchs",
                                 callback_data="action:matches"),
        ],
        [
            InlineKeyboardButton(text="🔄 Relancer", callback_data="action:scan"),
        ],
    ])


def retour() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Menu", callback_data="action:menu")],
    ])
