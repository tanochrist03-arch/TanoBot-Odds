"""Verification d'integration : moteur -> stockage -> relecture.

Exerce la chaine complete du bot sans Telegram : configuration, chargement du
moteur, analyse reelle, ecriture, puis lecture des statistiques.
"""
from __future__ import annotations

import pathlib
import sys

RACINE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(RACINE))

from bot import config as config_bot
from bot import engine_bridge as pont
from storage import construire_depot

print("=" * 76)
print("1. CONFIGURATION DU BOT")
print("=" * 76)
configuration = config_bot.charger()
for cle, valeur in configuration.resume_securise().items():
    print(f"  {cle:<22} {valeur}")
print()
for souci in configuration.problemes():
    print(f"  [!] {souci}")

print()
print("=" * 76)
print("2. CHARGEMENT DU MOTEUR")
print("=" * 76)
etat = pont.initialiser(configuration.chemin_moteur)
print(f"  chargé : {etat['ok']}   modules : {list(etat['modules'])}")
if not etat["ok"]:
    print(f"  ERREUR : {etat['erreur']}")
    sys.exit(1)

print()
print("=" * 76)
print("3. STOCKAGE")
print("=" * 76)
depot = construire_depot(configuration)
print(f"  dépôt retenu : {depot.decrire()}")

print()
print("=" * 76)
print("4. ANALYSE RÉELLE (collecte des cotes + moteur EV)")
print("=" * 76)
configuration_moteur = pont.charger_moteur()
configuration_moteur.seuil_ev = configuration.seuil_ev
configuration_moteur.confiance_minimum = float(configuration.seuil_confiance)

rapport = pont.analyser(configuration_moteur, forcer_reseau=False, enregistrer=False)
print(f"  ok            : {rapport['ok']}")
if not rapport["ok"]:
    print(f"  erreur        : {rapport.get('erreur')}")
print(f"  source        : {rapport.get('source')}")
print(f"  depuis cache  : {rapport.get('depuis_cache')}")
compteurs = rapport.get("compteurs") or {}
for cle in ("matchs_total", "matchs_a_venir", "matchs_evalues", "ligues_reconnues",
            "profils_construits", "resultats_historique"):
    if cle in compteurs:
        print(f"  {cle:<22} {compteurs[cle]}")
print(f"  pronostics    : {len(rapport.get('pronostics') or [])}")
print(f"  value bets    : {len(rapport.get('value_bets') or [])}")
for avertissement in (rapport.get("avertissements") or [])[:4]:
    print(f"  avertissement : {avertissement}")

print()
print("=" * 76)
print("5. ÉCRITURE DANS LE DÉPÔT")
print("=" * 76)
if rapport["ok"]:
    scan_id = depot.enregistrer_scan(rapport, seuil_ev=configuration.seuil_ev,
                                     seuil_confiance=configuration.seuil_confiance)
    print(f"  scan enregistré      : id {scan_id}")
    ecrits = depot.enregistrer_value_bets(rapport.get("value_bets") or [], scan_id)
    print(f"  value bets écrits    : {ecrits}")
    # Deuxième écriture : l'empreinte doit empêcher le doublon.
    doublons = depot.enregistrer_value_bets(rapport.get("value_bets") or [], scan_id)
    print(f"  réécriture (doublon) : {doublons} (0 attendu — unicité par empreinte)")

print()
print("=" * 76)
print("6. RELECTURE ET STATISTIQUES")
print("=" * 76)
stats = depot.statistiques()
for cle, valeur in stats.items():
    print(f"  {cle:<22} {valeur}")

recents = depot.value_bets_recents(5)
print(f"\n  5 derniers paris stockés :")
for pari in recents:
    print(f"    • {pari['match_libelle'][:42]:<42} "
          f"cote {pari['cote']:<6} EV {float(pari['ev']) * 100:+.1f} %  "
          f"confiance {pari['confiance']}")

print()
print("=" * 76)
print("7. ISOLATION DU MOTEUR (aucune réécriture de formule)")
print("=" * 76)
print(f"  expected_value importé depuis : {pont.expected_value.__module__}")
print(f"  analyser importé depuis       : {pont.analyser.__module__}")
print(f"  formater_paris importé depuis : {pont.formater_paris.__module__}")
