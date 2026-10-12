"""TanoBot Odds — tests du bot Telegram et de son socle."""

import sys
from pathlib import Path

# Le paquet `bot` vit à la racine du projet : on l'ajoute au chemin pour que
# `python -m unittest discover -s tests -t .` fonctionne depuis n'importe où.
RACINE = Path(__file__).resolve().parent.parent
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))
