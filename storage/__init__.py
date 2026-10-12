"""
TanoBot Odds — stockage.

Point d'entrée unique : `construire_depot(configuration)` renvoie le stockage
adapté (Supabase si configuré, SQLite sinon). Le reste du bot ne connaît que
l'interface `Depot` et n'a donc pas à savoir où les données sont écrites.
"""
from .base import Depot, construire_depot, empreinte_pari, normaliser_pari
from .sqlite_store import SqliteDepot

__all__ = [
    "Depot",
    "SqliteDepot",
    "construire_depot",
    "empreinte_pari",
    "normaliser_pari",
]
